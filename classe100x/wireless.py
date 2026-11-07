"""Phase-owned SSH forwarding and trust for the existing update sequence."""

from contextlib import contextmanager
from dataclasses import dataclass, field
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import time

from .firmware import FirmwareError, regular_file
from .host import run_tool
from .ssh import SSHConnection, SSHError, HostIdentityError, _invoking_user
from .wireless_image import facts, pipe_tool, public_identity


DEFAULT_HOST = "Bticino-Classe100X.local"


@dataclass
class Credentials:
    user: str
    key: Path | None = None
    password: str | None = field(default=None, repr=False)

    def __post_init__(self):
        connection = SSHConnection(self.user, key=self.key, password=self.password)
        self.key = connection.key

    def connection(self, host, key, **kwargs):
        return SSHConnection(self.user, key=self.key, password=self.password,
                             host=host, host_key=key, **kwargs)

    def public_keys(self):
        c = self.connection("127.0.0.1", None)
        privileges = {}
        if os.geteuid() == 0:
            privileges = dict(user=c.uid, group=c.gid, extra_groups=os.getgrouplist(c._account.pw_name, c.gid))
        expected = None
        if self.key is not None:
            sidecar = Path(str(self.key) + ".pub")
            if sidecar.is_file():
                with regular_file(sidecar) as stream:
                    expected = public_identity(stream.read(16385))
            try:
                data = pipe_tool(["/usr/bin/ssh-keygen", "-y", "-P", "", "-f", str(self.key)],
                                 env=c._environment(), **privileges)
            except FirmwareError:
                if expected is None:
                    raise FirmwareError("Encrypted destination keys need their matching .pub file and an unlocked agent") from None
            else:
                actual = public_identity(data)
                if expected is not None and expected != actual:
                    raise FirmwareError("SSH public sidecar differs from the selected private key")
                return {actual}
        data = pipe_tool(["/usr/bin/ssh-add", "-L"], env=c._environment(), **privileges)
        result = set()
        for line in data.splitlines():
            if line.startswith((b"ssh-rsa ", b"ecdsa-sha2-nistp256 ")):
                result.add(public_identity(line))
        if self.key is not None:
            if expected not in result:
                raise FirmwareError("Destination key is not unlocked in the SSH agent")
            return {expected}
        return result


def resolve(host):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,252}", host):
        raise SSHError("--host requires a DNS/mDNS hostname or IPv4 address")
    # Bound OS DNS/mDNS resolution too, not only the subsequent TCP connection.
    code = "import socket,sys; print('\\n'.join(sorted({x[4][0] for x in socket.getaddrinfo(sys.argv[1],22,socket.AF_INET,socket.SOCK_STREAM)})))"
    try:
        addresses = pipe_tool([sys.executable, "-I", "-c", code, host]).decode().splitlines()
    except FirmwareError as exc:
        raise SSHError("Wireless hostname resolution failed") from exc
    if len(addresses) != 1:
        raise HostIdentityError("Wireless target must resolve to one unambiguous IPv4 address")
    socket.inet_aton(addresses[0])
    return addresses[0]


def scan_keys(address):
    try:
        _, out, _ = run_tool(["/usr/bin/ssh-keyscan", "-T", "3", "-t", "ecdsa,rsa", address], timeout=5, limit=16384)
    except FirmwareError as exc:
        raise SSHError("SSH server key scan did not complete") from exc
    keys = set()
    for line in out.splitlines():
        fields = line.split()
        if len(fields) == 3 and not line.startswith(b"#"):
            keys.add(public_identity(b" ".join(fields[1:])))
    if not keys:
        raise SSHError("SSH server is not ready")
    return keys


def fingerprint(key):
    return "SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(key.split()[1])).digest()).decode().rstrip("=")


class Trust:
    """One owner-selected endpoint, locked throughout preflight/flash."""
    def __init__(self, host, *, parent=None):
        self.account = _invoking_user()
        self.host = host.lower().rstrip(".")
        self.parent = Path(parent) if parent else Path(self.account.pw_dir) / "Library/Application Support/C100X/trust"
        self.name = hashlib.sha256(self.host.encode()).hexdigest()
        self.path = self.parent / (self.name + ".json")
        self.lock = None

    def __enter__(self):
        missing = []
        directory = self.parent
        while not directory.exists():
            missing.append(directory)
            directory = directory.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o700)
            if os.geteuid() == 0:
                os.chown(directory, self.account.pw_uid, self.account.pw_gid)
        if self.parent.is_symlink() or self.path.is_symlink():
            raise SSHError("SSH trust paths must not be symlinks")
        if os.geteuid() == 0:
            os.chown(self.parent, self.account.pw_uid, self.account.pw_gid)
        os.chmod(self.parent, 0o700)
        fd = os.open(self.parent / (self.name + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(fd, "r+")
        if os.geteuid() == 0:
            os.fchown(fd, self.account.pw_uid, self.account.pw_gid)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise SSHError("Another operation owns this wireless target") from None
        return self

    def __exit__(self, *exc):
        if self.lock:
            self.lock.close()

    def known(self, address):
        if self.path.exists():
            with regular_file(self.path) as stream:
                record = json.loads(stream.read(16385))
            if record.get("host") != self.host:
                raise HostIdentityError("Invalid saved target identity")
            return {public_identity(record["key"].encode())}
        known = Path(self.account.pw_dir) / ".ssh/known_hosts"
        result = set()
        if known.is_file():
            # A locator's established identity wins over incidental IP trust.
            # DHCP can assign an address previously used by another trusted host.
            for host in dict.fromkeys((self.host, address)):
                _, out, _ = run_tool(["/usr/bin/ssh-keygen", "-F", host, "-f", str(known)], timeout=5, limit=65536)
                for line in out.splitlines():
                    fields = line.split()
                    if line.startswith(b"@"):
                        raise HostIdentityError("Marked SSH trust entries require explicit investigation")
                    if len(fields) >= 3 and not line.startswith(b"#"):
                        result.add(public_identity(b" ".join(fields[1:3])))
                if result:
                    return result
        return result

    def enroll(self, address, confirm):
        known, observed = self.known(address), scan_keys(address)
        if known:
            matches = known & observed
            if not matches:
                raise HostIdentityError("SSH identity changed; saved trust was not replaced")
            key = sorted(matches)[0]
        else:
            key = sorted(observed)[0]
            if not confirm(self.host, fingerprint(key)):
                raise HostIdentityError("Initial SSH fingerprint was not approved")
        return key

    def save(self, key):
        key = public_identity(key.encode())
        temporary = self.path.with_suffix(".new")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                if os.geteuid() == 0:
                    os.fchown(stream.fileno(), self.account.pw_uid, self.account.pw_gid)
                json.dump({"host": self.host, "key": key}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)


class Tunnel(SSHConnection):
    def __init__(self, credentials, host, key):
        super().__init__(credentials.user, key=credentials.key, password=credentials.password, host=host, host_key=key)
        self.process = None
        self.thread = None
        self.error = None
        self.ports = []
        self.stopping = threading.Event()

    def _command(self, command, known_hosts, timeout):
        args = super()._command(command, known_hosts, min(timeout, 10))[:-1]
        extra = ["-N", "-o", "ControlMaster=yes", "-o", f'ControlPath="{self._directory / "m"}"',
                 "-o", "ClearAllForwardings=no", "-o", "ExitOnForwardFailure=yes",
                 "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3"]
        for local, remote in zip(self.ports, (20000, 21, 11111)):
            extra += ["-L", f"127.0.0.1:{local}:127.0.0.1:{remote}"]
        return [args[0], *extra, *args[1:]]

    def _started(self, process):
        self.process = process
        if self.stopping.is_set():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def start(self):
        self.open()
        sockets = []
        try:
            for _ in range(3):
                s = socket.socket()
                sockets.append(s)
                s.bind(("127.0.0.1", 0))
                self.ports.append(s.getsockname()[1])
        finally:
            for s in sockets:
                s.close()
        def worker():
            try:
                self.run("", timeout=86400)
            except BaseException as exc:
                self.error = exc
        self.thread = threading.Thread(target=worker, name="c100x-ssh-forward", daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            self.check()
            if (self._directory / "m").exists():
                result = subprocess.run(["/usr/bin/ssh", "-F", "/dev/null", "-S", str(self._directory / "m"),
                                         "-O", "check", self.host], capture_output=True, timeout=2)
                if result.returncode == 0:
                    return
            time.sleep(0.05)
        raise SSHError("Authenticated SSH forwarding did not become ready")

    def check(self):
        if self.error is not None:
            raise self.error
        if self.thread is not None and not self.thread.is_alive():
            raise SSHError("SSH forward exited")

    def close(self):
        self.stopping.set()
        if self.process is not None and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.thread is not None:
            self.thread.join(5)
            if self.thread.is_alive():
                raise SSHError("SSH forward did not terminate")
        super().close()


def installer_check():
    # Constant read-only program. Manager presence alone is not an active install.
    return """set -eu
test "$(id -u)" = 0
for f in /home/bticino/cfg/extra/UPGRADE.fwz /home/bticino/cfg/extra/FW/UPGRADE.fwz; do
    if test -e "$f"; then echo 'Staged manufacturer package exists' >&2; exit 1; fi
done
if test -e /home/bticino/cfg/extra/update_flags; then
    test -d /home/bticino/cfg/extra/update_flags
    test -z "$(ls -A /home/bticino/cfg/extra/update_flags)" || {
        echo 'Manufacturer update metadata requires investigation' >&2; exit 1;
    }
fi
for p in /proc/[0-9]*/comm; do
    test -r "$p" || continue
    name=$(cat "$p" 2>/dev/null) || continue
    case "$name" in dedrifupdater*|dedrifu.sh*) echo 'Manufacturer installer is active' >&2; exit 1;; esac
done
echo READY
"""


@contextmanager
def interruptible():
    def stop(signum, frame):
        raise KeyboardInterrupt
    previous = {}
    try:
        for sig in (signal.SIGHUP, signal.SIGTERM):
            previous[sig] = signal.signal(sig, stop)
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


class Wireless:
    strict = True

    def __init__(self, host, existing, destination, image, trust, *, confirm):
        self.host, self.existing, self.destination = host, existing, destination
        self.image, self.trust, self.confirm = image, trust, confirm
        self.phase = 0
        self.tunnel = None
        self.connection = None
        self.old_key = None
        self.previous_key = None
        self.ip = None
        self.reconnecting = False
        self.final_verified = False
        self.host_keys = []
        account = _invoking_user()
        self.uid, self.gid = account.pw_uid, account.pw_gid

    def __enter__(self):
        try:
            self.ip = resolve(self.host)
            self.old_key = self.trust.enroll(self.ip, self.confirm)
            self._connect()
            self.preflight()
            self.trust.save(self.old_key)
            return self
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise

    def __exit__(self, exc_type, error, traceback):
        try:
            self.close(error=error)
        finally:
            self.existing.password = self.destination.password = None

    def _connect(self):
        key = self.old_key if self.phase < 2 else self.image.host_key
        credentials = self.existing if self.phase < 2 else self.destination
        observed = scan_keys(self.ip)
        if key not in observed:
            if self.reconnecting and self.previous_key in observed:
                raise SSHError("Previous environment still responds; waiting for the planned reboot")
            raise HostIdentityError("Unexpected SSH identity during phase transition")
        self.tunnel = Tunnel(credentials, self.ip, key)
        try:
            self.tunnel.start()
            self.connection = credentials.connection(self.ip, key)
            self.connection.open()
            self.run("test \"$(id -u)\" = 0", timeout=10)
        except BaseException as error:
            self.close(error=error)
            raise
        self.host_keys.append({"phase": self.phase, "fingerprint": fingerprint(key), "status": "verified"})

    def endpoints(self):
        if self.tunnel is None:
            if not self.reconnecting:
                raise SSHError("No authenticated SSH tunnel")
            self.ip = resolve(self.host)
            self._connect()
        try:
            self.tunnel.check()
        except HostIdentityError:
            raise
        except SSHError:
            if self.reconnecting:
                self.close()
            raise
        return ("127.0.0.1", *self.tunnel.ports)

    def run(self, command, **kwargs):
        if self.connection is None:
            raise SSHError("Administrative SSH is not connected")
        return self.connection.run(command, **kwargs)

    def preflight(self):
        if self.run(installer_check()) != b"READY\n":
            raise SSHError("Manufacturer installation check failed")
        pins = facts("no-ota")["UNCHANGED"]
        paths = ["/home/bticino/bin/" + name for name in ("bt_device", "bt_daemon", "fw_manager", "dedrifupdater")]
        result = self.run("sha256sum " + " ".join(paths)).decode().splitlines()
        if [line.split()[0] for line in result] != [pins[path][0] for path in paths]:
            raise SSHError("Installed update executables differ from the researched profile")
        # Existing-main SSH eligibility is demonstrated by administrative access
        # and reconnecting with the same key after the planned normal reboot.
        # Its init script, configuration formatting and key pathname may differ.

    def rebooting(self, status):
        expected = (4, 1, 4)
        if self.phase >= 3 or status != expected[self.phase]:
            raise SSHError("Unexpected wireless reboot transition")
        self.previous_key = self.old_key if self.phase < 2 else self.image.host_key
        self.close()
        self.phase += 1
        self.reconnecting = True

    def arrived(self, status):
        self.preflight()
        self.reconnecting = False

    def verified(self):
        if self.phase != 3 or self.reconnecting:
            raise SSHError("Final normal reboot and SSH verification are incomplete")
        self.run("test \"$(id -u)\" = 0", timeout=10)
        self.final_verified = True

    def remember(self):
        if not self.final_verified:
            raise SSHError("Destination identity cannot be remembered before final verification")
        self.trust.save(self.image.host_key)

    def close(self, *, error=None):
        connection, tunnel = self.connection, self.tunnel
        self.connection = self.tunnel = None
        failure = error
        for resource in (connection, tunnel):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as exc:
                    if failure is None:
                        failure = exc
                    else:
                        failure.add_note(f"Additional SSH cleanup failure: {exc}")
        if error is None and failure is not None:
            raise failure


class VerificationReader:
    """Borrow the transport's reads; verifier cleanup must not close its owner."""
    strict = True

    def __init__(self, transport):
        self.transport = transport
        self.uid, self.gid = transport.uid, transport.gid

    @property
    def host_keys(self):
        return self.transport.host_keys

    def __enter__(self):
        return self

    def run(self, *args, **kwargs):
        return self.transport.run(*args, **kwargs)

    def close(self):
        pass


@contextmanager
def awake():
    process = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        time.sleep(0.05)
        if process.poll() is not None:
            raise SSHError("Unable to establish macOS idle-sleep assertion")
        yield
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stderr.close()
