"""Optional, fixed-profile USB SSH reads through the system OpenSSH client.

The caller supplies trusted read-only commands and the USB route check. Passwords
stay in memory; neither the builder subprocess helpers nor SSH configuration are
used here. This object is sequential, with one independent SSH process per read.
"""

import base64
import binascii
import hashlib
import math
import os
from pathlib import Path
import pwd
import re
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time


STDOUT_LIMIT = 128 * 1024
STDERR_LIMIT = 64 * 1024
PASSWORD_LIMIT = 4096


class SSHError(OSError):
    pass


def _invoking_user():
    try:
        if os.geteuid() == 0:
            uid = os.environ.get("SUDO_UID", "")
            if not uid.isdecimal() or int(uid) == 0:
                raise ValueError
            account = pwd.getpwuid(int(uid))
            if (account.pw_uid != int(uid) or os.environ.get("SUDO_USER") != account.pw_name
                    or pwd.getpwnam(account.pw_name).pw_uid != account.pw_uid):
                raise ValueError
        else:
            account = pwd.getpwuid(os.geteuid())
        if not Path(account.pw_dir).is_absolute():
            raise ValueError
        return account
    except (KeyError, ValueError, OverflowError):
        raise SSHError("Optional SSH verification needs an ordinary invoking user; use sudo from that account") from None


class SSHConnection:
    def __init__(self, user: str, *, key: Path | None = None,
                 password: str | None = None, check_transport=lambda: None, warn=print):
        if not isinstance(user, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", user):
            raise SSHError("Invalid SSH account name")
        if password is not None and key is not None:
            raise SSHError("Choose SSH key authentication or password authentication")
        if password is not None:
            if (not isinstance(password, str) or any(c in password for c in "\x00\r\n")
                    or len(password.encode("utf-8")) > PASSWORD_LIMIT):
                raise SSHError("SSH password is not supported by the askpass transport")
        account = _invoking_user()
        self.uid, self.gid = account.pw_uid, account.pw_gid
        self._account = account
        self.user = user
        if key is not None:
            # expanduser() would otherwise consult root's HOME under sudo.
            text = str(key)
            if text == "~" or text.startswith("~/"):
                key = Path(account.pw_dir) / text[2:]
            elif text.startswith("~"):
                raise SSHError("SSH key paths may use only the invoking user's home")
            key = Path(key).absolute()
        self.key = key
        self._password = password
        self.check_transport = check_transport
        self.warn = warn
        self.host_keys: list[dict[str, str]] = []
        self._directory: Path | None = None
        self._broker = None
        self._closed = False

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def open(self):
        if self._closed:
            raise SSHError("SSH connection is closed")
        if self._directory is not None:
            return self
        try:
            if not os.access("/usr/bin/ssh", os.X_OK):
                raise SSHError("System OpenSSH is unavailable")
            if self.key is not None and not self.key.is_file():
                raise SSHError("SSH private key is unavailable")
            if self._password is not None:
                wrapper = Path(__file__).with_name("ssh-askpass")
                if not os.access(wrapper, os.X_OK) or not wrapper.with_name("ssh_askpass.py").is_file():
                    raise SSHError("The packaged SSH askpass helper is unavailable")
            # A short, publicly traversable parent is required by sockaddr_un and
            # by privilege dropping (sudo's per-user TMPDIR may be root-only).
            self._directory = Path(tempfile.mkdtemp(prefix="c100x-ssh-", dir="/tmp"))
            self._own(self._directory)
            if self._password is not None:
                self._broker = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._broker.bind(str(self._directory / "p"))
                os.chmod(self._directory / "p", 0o600)
                self._own(self._directory / "p")
                self._broker.listen(1)
                self._broker.setblocking(False)
            return self
        except BaseException as error:
            self.close()
            if isinstance(error, OSError) and not isinstance(error, SSHError):
                raise SSHError("Cannot prepare the private SSH transport") from None
            raise

    def close(self):
        self._password = None
        self._closed = True
        if self._broker is not None:
            self._broker.close()
            self._broker = None
        if self._directory is not None:
            directory, self._directory = self._directory, None
            try:
                shutil.rmtree(directory)
            except OSError:
                raise SSHError("Cannot remove the private SSH workspace") from None

    def _own(self, path):
        if os.geteuid() == 0:
            os.chown(path, self.uid, self.gid)

    def _environment(self):
        env = {"PATH": "/usr/bin:/bin", "HOME": self._account.pw_dir,
               "USER": self._account.pw_name, "LOGNAME": self._account.pw_name,
               "LC_ALL": "C"}
        if "SSH_AUTH_SOCK" in os.environ:
            env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
        if self._password is not None:
            env.update(SSH_ASKPASS=str(Path(__file__).with_name("ssh-askpass").resolve()),
                       SSH_ASKPASS_REQUIRE="force", DISPLAY="c100x:0",
                       C100X_ASKPASS_PYTHON=sys.executable,
                       C100X_ASKPASS_HELPER=str(Path(__file__).with_name("ssh_askpass.py").resolve()),
                       C100X_ASKPASS_SOCKET=str(self._directory / "p"))
        else:
            env["SSH_ASKPASS_REQUIRE"] = "never"
        return env

    def _command(self, command, known_hosts, timeout):
        options = [
            "Hostname=192.168.129.1", "Port=22", "AddressFamily=inet",
            "ProxyCommand=none", "ProxyJump=none", "ControlMaster=no", "ControlPath=none",
            "ClearAllForwardings=yes", "ForwardAgent=no", "ForwardX11=no", "Tunnel=no",
            "PermitLocalCommand=no", "RequestTTY=no", "StrictHostKeyChecking=no",
            f'UserKnownHostsFile="{known_hosts}"', "GlobalKnownHostsFile=/dev/null",
            "HashKnownHosts=no", "UpdateHostKeys=no", "VerifyHostKeyDNS=no",
            "CheckHostIP=no", "LogLevel=ERROR", "ConnectionAttempts=1",
            f"ConnectTimeout={max(1, math.ceil(timeout))}", "NumberOfPasswordPrompts=1",
            "KbdInteractiveAuthentication=no", "GSSAPIAuthentication=no",
            "HostbasedAuthentication=no", "PubkeyAcceptedAlgorithms=+ssh-rsa",
            "HostKeyAlgorithms=+ssh-rsa",
        ]
        if self._password is None:
            options += ["BatchMode=yes", "PreferredAuthentications=publickey", "PasswordAuthentication=no"]
        else:
            options += ["BatchMode=no", "PreferredAuthentications=password", "PubkeyAuthentication=no",
                        "PasswordAuthentication=yes"]
        args = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-n"]
        for option in options:
            args += ["-o", option]
        if self.key is not None:
            args += ["-o", "IdentitiesOnly=yes", "-i", str(self.key)]
        return [*args, "-l", self.user, "192.168.129.1", command]

    def _observe_host_key(self, path):
        with path.open("rb") as stream:
            data = stream.read(16385)
        if len(data) > 16384:
            raise SSHError("Invalid SSH host-key evidence")
        found = False
        for line in data.splitlines():
            fields = line.split()
            if len(fields) != 3 or fields[0] != b"192.168.129.1":
                raise SSHError("Invalid SSH host-key evidence")
            if not re.fullmatch(rb"[a-zA-Z0-9@._+-]{1,80}", fields[1]):
                raise SSHError("Invalid SSH host-key evidence")
            try:
                blob = base64.b64decode(fields[2], validate=True)
            except binascii.Error:
                raise SSHError("Invalid SSH host-key evidence") from None
            # SSH public keys begin with their length-prefixed algorithm name.
            if len(blob) < 4 or blob[4:4 + int.from_bytes(blob[:4], "big")] != fields[1]:
                raise SSHError("Invalid SSH host-key evidence")
            fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
            found = True
            if self.host_keys and self.host_keys[-1]["fingerprint"] == fingerprint:
                continue
            status = "changed" if self.host_keys else "first_seen"
            self.host_keys.append({"algorithm": fields[1].decode(), "fingerprint": fingerprint, "status": status})
            self.warn(f"SSH host key {'changed' if status == 'changed' else 'first seen'}: {fingerprint}; identity continuity is not verified")
        return found

    def run(self, command: str, *, timeout: float = 30, output: Path | None = None,
            expected_size: int | None = None) -> bytes:
        if not math.isfinite(timeout) or timeout <= 0:
            raise SSHError("SSH timeout must be positive and finite")
        if (output is not None and (type(expected_size) is not int or expected_size < 0)
                or output is None and expected_size is not None):
            raise SSHError("SSH file acquisition requires an exact nonnegative size")
        self.open()
        self.check_transport()
        deadline = time.monotonic() + timeout
        process = None
        target = None
        created = False
        known_hosts = self._directory / "known_hosts"
        try:
            # Fresh each time: OpenSSH disables password auth for changed keys in
            # an existing known_hosts file even with StrictHostKeyChecking=no.
            known_hosts.unlink(missing_ok=True)
            with known_hosts.open("xb"):
                pass
            os.chmod(known_hosts, 0o600)
            self._own(known_hosts)
            if output is not None:
                target = os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb")
                created = True
                if os.geteuid() == 0:
                    os.fchown(target.fileno(), self.uid, self.gid)
            privileges = {}
            if os.geteuid() == 0:
                privileges = dict(user=self.uid, group=self.gid,
                                  extra_groups=os.getgrouplist(self._account.pw_name, self.gid))
            process = subprocess.Popen(self._command(command, known_hosts, timeout),
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, env=self._environment(),
                                       cwd=self._directory, start_new_session=True, **privileges)
            result = self._receive(process, target, expected_size, deadline)
            observed = self._observe_host_key(known_hosts)
            if process.returncode:
                raise SSHError(f"SSH command failed (exit {process.returncode}); check authentication and USB readiness")
            if not observed:
                raise SSHError("SSH connection did not provide host-key evidence")
            if target is not None:
                target.close()
                target = None
            return result
        except BaseException as error:
            if process is not None:
                # Kill the whole isolated group, including a blocked askpass or
                # descendant holding a pipe open after the SSH process exits.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                # Authentication failures, cancellation and bounded-output
                # failures can all happen after OpenSSH accepted the host key.
                try:
                    self._observe_host_key(known_hosts)
                except (OSError, SSHError):
                    pass
            if target is not None:
                target.close()
                target = None
            if created:
                Path(output).unlink(missing_ok=True)
            if isinstance(error, OSError) and not isinstance(error, SSHError):
                raise SSHError("SSH transport or local acquisition I/O failed") from None
            raise
        finally:
            if process is not None:
                process.stdout.close()
                process.stderr.close()

    def _receive(self, process, target, expected_size, deadline):
        captured = bytearray()
        sizes = {"stdout": 0, "stderr": 0}
        password_sent = False
        with selectors.DefaultSelector() as selector:
            for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            if self._broker is not None:
                selector.register(self._broker, selectors.EVENT_READ, "password")
            pipes = 2
            while pipes or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SSHError("SSH command timed out")
                for key, _ in selector.select(min(remaining, 0.1)):
                    name = key.data
                    if name == "password":
                        peer, _ = self._broker.accept()
                        with peer:
                            peer.settimeout(min(remaining, 0.5))
                            if not password_sent:
                                peer.sendall(self._password.encode("utf-8") + b"\n")
                                password_sent = True
                        continue
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        pipes -= 1
                        continue
                    sizes[name] += len(chunk)
                    limit = STDERR_LIMIT if name == "stderr" else (expected_size if target is not None else STDOUT_LIMIT)
                    if sizes[name] > limit:
                        raise SSHError(f"SSH {name} exceeded its byte limit")
                    if name == "stdout":
                        if target is None:
                            captured.extend(chunk)
                        else:
                            target.write(chunk)
            process.wait()
        if target is not None and sizes["stdout"] != expected_size:
            raise SSHError("SSH acquisition was truncated")
        return bytes(captured)
