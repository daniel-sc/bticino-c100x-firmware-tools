import base64
import hashlib
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from classe100x.ssh import SSHConnection, SSHError, STDERR_LIMIT, STDOUT_LIMIT


ALGORITHM = b"ecdsa-sha2-nistp256"
KEY = len(ALGORITHM).to_bytes(4, "big") + ALGORITHM + b"synthetic-key"
KEY_LINE = "192.168.129.1 " + ALGORITHM.decode() + " " + base64.b64encode(KEY).decode() + "\n"


class SSHTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.account = pwd.getpwuid(os.getuid())
        # The suite is offline and never needs privilege changes, including when
        # invoked by a root CI runner.
        self.enterContext(patch("classe100x.ssh.os.geteuid", return_value=self.account.pw_uid or 501))
        self.enterContext(patch("classe100x.ssh._invoking_user", return_value=self.account))
        self.real_popen = subprocess.Popen
        self.children = []
        self.calls = []
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for process in self.children:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)

    def fake_ssh(self, body="os.write(1, b'0\\n')", key_line=KEY_LINE):
        script = self.directory / "fake_ssh.py"
        script.write_text(
            "import os, sys, time, subprocess\nfrom pathlib import Path\n"
            "hosts = next(a.split('=', 1)[1].strip(chr(34)) for a in sys.argv if a.startswith('UserKnownHostsFile='))\n"
            # Prove that each subprocess gets a freshly empty known_hosts file.
            "assert Path(hosts).read_bytes() == b''\n"
            f"Path(hosts).write_text({key_line!r})\n" + body + "\n")

        def spawn(args, **kwargs):
            self.calls.append((args, kwargs))
            process = self.real_popen([sys.executable, "-I", "-B", str(script), *args[1:]], **kwargs)
            self.children.append(process)
            return process

        return patch("classe100x.ssh.subprocess.Popen", side_effect=spawn)

    def test_fixed_route_config_key_and_fingerprints(self):
        checks, warnings = Mock(), []
        key = self.directory / "private key"
        key.touch()
        with self.fake_ssh(), SSHConnection("root2", key=key, check_transport=checks,
                                            warn=warnings.append) as connection:
            workspace = connection._directory
            self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)
            self.assertEqual(connection.run("id -u"), b"0\n")
            self.assertEqual(connection.run("id -u"), b"0\n")
            self.assertEqual(checks.call_count, 2)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(connection.host_keys, [{
                "algorithm": ALGORITHM.decode(), "status": "first_seen",
                "fingerprint": "SHA256:" + base64.b64encode(hashlib.sha256(KEY).digest()).decode().rstrip("="),
            }])
            args, kwargs = self.calls[0]
            self.assertEqual(args[:5], ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-n"])
            self.assertEqual(args[-4:], ["-l", "root2", "192.168.129.1", "id -u"])
            for option in ("BatchMode=yes", "ProxyCommand=none", "ProxyJump=none",
                           "ControlPath=none", "ForwardAgent=no", "ClearAllForwardings=yes",
                           "PubkeyAcceptedAlgorithms=+ssh-rsa", "IdentitiesOnly=yes", "Port=22"):
                self.assertIn(option, args)
            self.assertIn(str(key), args)
            self.assertTrue(kwargs["start_new_session"])
            self.assertEqual(kwargs["env"]["HOME"], self.account.pw_dir)
        self.assertFalse(workspace.exists())
        connection.close()
        connection.close()
        self.assertEqual(len(connection.host_keys), 1)
        with self.assertRaisesRegex(SSHError, "closed"):
            connection.run("id -u")

    def test_changed_key_warns_and_password_is_sent_via_real_helper_only(self):
        secret = "private-password-\N{SNOWMAN}"
        body = (
            "helper = subprocess.run([os.environ['SSH_ASKPASS'], 'untrusted prompt'], capture_output=True)\n"
            "assert helper.returncode == 0\n"
            "os.write(1, helper.stdout)\n"
            "again = subprocess.run([os.environ['SSH_ASKPASS']], capture_output=True)\n"
            "assert again.returncode == 1 and again.stdout == b'' and again.stderr == b''\n"
        )
        warnings = []
        with SSHConnection("root2", password=secret, warn=warnings.append) as connection:
            for key_line in (KEY_LINE, KEY_LINE.replace(base64.b64encode(KEY).decode(),
                                                       base64.b64encode(KEY + b"changed").decode()), KEY_LINE):
                with self.fake_ssh(body, key_line):
                    self.assertEqual(connection.run("id -u"), (secret + "\n").encode())
            self.assertEqual([item["status"] for item in connection.host_keys], ["first_seen", "changed"])
            self.assertEqual(len(warnings), 2)
            self.assertEqual((connection._directory / "p").stat().st_mode & 0o777, 0o600)
            for args, kwargs in self.calls:
                self.assertNotIn(secret, repr(args) + repr(kwargs["env"]) + repr(warnings))
                self.assertIn("NumberOfPasswordPrompts=1", args)
                self.assertIn("PreferredAuthentications=password", args)
                self.assertIn("PubkeyAuthentication=no", args)
            for path in connection._directory.iterdir():
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes())
        self.assertIsNone(connection._password)

    def test_streams_exact_private_output_without_clobber(self):
        output = self.directory / "readback"
        with self.fake_ssh("os.write(1, b'x' * 300000)"), SSHConnection("root2", warn=lambda _: None) as connection:
            self.assertEqual(connection.run("read", output=output, expected_size=300000), b"")
            self.assertEqual(output.read_bytes(), b"x" * 300000)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(SSHError):
                connection.run("read", output=output, expected_size=300000)
            self.assertEqual(output.read_bytes(), b"x" * 300000)
            self.assertEqual(len(self.calls), 1)

    def test_bounds_truncation_and_nonzero_remove_partial_output(self):
        cases = [
            ("os.write(1, b'x' * 20)", 21, "truncated"),
            ("os.write(1, b'x' * 20)", 19, "byte limit"),
            ("os.write(1, b'x' * 20); os.write(2, b'private server diagnostic'); sys.exit(7)", 20, "exit 7"),
            (f"os.write(2, b'x' * {STDERR_LIMIT + 1}); time.sleep(30)", 0, "byte limit"),
            ("os.write(1, b'x'); time.sleep(30)", 20, "timed out"),
        ]
        for body, size, message in cases:
            with self.subTest(message=message), self.fake_ssh(body), SSHConnection("root2", warn=lambda _: None) as connection:
                output = self.directory / "partial"
                with self.assertRaisesRegex(SSHError, message) as error:
                    connection.run("read", output=output, expected_size=size, timeout=0.5)
                self.assertNotIn("private server diagnostic", str(error.exception))
                self.assertFalse(output.exists())
                self.assertIsNotNone(self.children[-1].poll())

    def test_capture_limit_and_no_raw_diagnostics(self):
        with self.fake_ssh(f"os.write(1, b'x' * {STDOUT_LIMIT + 1}); time.sleep(30)"), \
                SSHConnection("root2", warn=lambda _: None) as connection:
            with self.assertRaisesRegex(SSHError, "stdout exceeded"):
                connection.run("read")
        with self.fake_ssh("os.write(2, b'credential server diagnostic'); sys.exit(255)"), \
                SSHConnection("root2", warn=lambda _: None) as connection:
            with self.assertRaisesRegex(SSHError, "exit 255") as error:
                connection.run("read")
            self.assertNotIn("credential", str(error.exception))
            self.assertEqual(len(connection.host_keys), 1)

    def test_missing_or_invalid_host_key_evidence_fails(self):
        for evidence in ("", "private diagnostic", "192.168.129.1 ssh-rsa !!!\n"):
            with self.subTest(evidence=evidence), self.fake_ssh(key_line=evidence), \
                    SSHConnection("root2", warn=lambda _: None) as connection:
                with self.assertRaises(SSHError) as error:
                    connection.run("id -u")
                self.assertNotIn("private diagnostic", str(error.exception))

    def test_transport_failure_stops_before_process_or_output(self):
        check = Mock(side_effect=RuntimeError("USB route failed"))
        with self.fake_ssh(), SSHConnection("root2", check_transport=check) as connection:
            output = self.directory / "not-created"
            with self.assertRaisesRegex(RuntimeError, "USB route"):
                connection.run("read", output=output, expected_size=1)
            self.assertFalse(self.calls)
            self.assertFalse(output.exists())

    def test_cancellation_kills_process_group_and_cleans_partial(self):
        output = self.directory / "partial"
        with self.fake_ssh("time.sleep(30)"), SSHConnection("root2") as connection:
            with patch("classe100x.ssh.selectors.DefaultSelector.select", side_effect=KeyboardInterrupt), \
                    patch("classe100x.ssh.os.killpg", wraps=os.killpg) as kill:
                with self.assertRaises(KeyboardInterrupt):
                    connection.run("read", output=output, expected_size=20)
                kill.assert_called_once_with(self.children[-1].pid, signal.SIGKILL)
            self.assertFalse(output.exists())
            self.assertIsNotNone(self.children[-1].poll())

    def test_timeout_kills_descendant_holding_pipe_after_parent_exit(self):
        pidfile = self.directory / "descendant"
        body = ("child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                f"Path({str(pidfile)!r}).write_text(str(child.pid))\n")
        with self.fake_ssh(body), SSHConnection("root2", warn=lambda _: None) as connection:
            with patch("classe100x.ssh.os.killpg", wraps=os.killpg) as kill:
                with self.assertRaisesRegex(SSHError, "timed out"):
                    connection.run("read", timeout=0.5)
                kill.assert_called_once_with(self.children[-1].pid, signal.SIGKILL)
            self.assertTrue(pidfile.exists())
            self.assertEqual(len(connection.host_keys), 1)
            # The leader has exited, but killpg must still be issued. A new
            # process waiting on these same inherited pipes sees EOF promptly.
            for stream in (self.children[-1].stdout, self.children[-1].stderr):
                self.assertTrue(stream.closed)

    def test_invalid_inputs_and_agent_environment(self):
        for user in ("", "-oProxyCommand=evil", "root user", "root\n", "x@y"):
            with self.subTest(user=user), self.assertRaises(SSHError):
                SSHConnection(user)
        for secret in ("line\nbreak", "null\0byte", "x" * 4097):
            with self.assertRaises(SSHError):
                SSHConnection("root2", password=secret)
        with self.assertRaises(SSHError):
            SSHConnection("root2", key=Path("key"), password="password")
        with patch.dict(os.environ, {"SSH_AUTH_SOCK": "/private/agent", "SSH_ASKPASS": "bad", "HOME": "/root"}):
            connection = SSHConnection("root2", key=Path("~/.ssh/key"))
            self.assertEqual(connection.key, Path(self.account.pw_dir) / ".ssh/key")
            env = connection._environment()
            self.assertEqual(env["SSH_AUTH_SOCK"], "/private/agent")
            self.assertNotIn("SSH_ASKPASS", env)
            self.assertEqual(env["HOME"], self.account.pw_dir)
        with SSHConnection("root2") as connection:
            for timeout in (0, -1, float("nan"), float("inf")):
                with self.assertRaises(SSHError):
                    connection.run("read", timeout=timeout)
            with self.assertRaises(SSHError):
                connection.run("read", output=self.directory / "image")

    def test_system_openssh_accepts_options_offline(self):
        # -G prints the resolved config without contacting any destination.
        with SSHConnection("root2") as connection:
            args = connection._command("id -u", connection._directory / "known_hosts", 1)
            result = subprocess.run([args[0], "-G", *args[1:]], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn(b"hostname 192.168.129.1\n", result.stdout)
            self.assertIn(b"port 22\n", result.stdout)
            self.assertIn(f"userknownhostsfile {connection._directory}/known_hosts\n".encode(), result.stdout)


class SSHPrivilegeTests(unittest.TestCase):
    def test_sudo_identity_is_validated_against_account_database(self):
        from classe100x.ssh import _invoking_user
        account = pwd.struct_passwd(("ordinary", "x", 501, 20, "", "/Users/ordinary", "/bin/sh"))
        with patch("classe100x.ssh.os.geteuid", return_value=0), \
                patch("classe100x.ssh.pwd.getpwuid", return_value=account), \
                patch("classe100x.ssh.pwd.getpwnam", return_value=account):
            for env in ({}, {"SUDO_UID": "0", "SUDO_USER": "root"},
                        {"SUDO_UID": "501", "SUDO_USER": "wrong"}, {"SUDO_UID": "bad"}):
                with patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(SSHError, "ordinary invoking user"):
                    _invoking_user()
            with patch.dict(os.environ, {"SUDO_UID": "501", "SUDO_USER": "ordinary", "SUDO_GID": "0"}, clear=True):
                connection = SSHConnection("root2")
                self.assertEqual((connection.uid, connection.gid), (501, 20))

    def test_spawn_drops_uid_gid_and_supplementary_groups(self):
        account = pwd.struct_passwd(("ordinary", "x", 501, 20, "", "/Users/ordinary", "/bin/sh"))
        with tempfile.TemporaryDirectory() as directory, \
                patch("classe100x.ssh._invoking_user", return_value=account), \
                patch("classe100x.ssh.os.geteuid", return_value=0), \
                patch("classe100x.ssh.os.chown") as chown, \
                patch("classe100x.ssh.os.fchown") as fchown, \
                patch("classe100x.ssh.os.getgrouplist", return_value=[20, 12]) as groups, \
                patch("classe100x.ssh.subprocess.Popen", side_effect=OSError("private error")) as spawn:
            with SSHConnection("root2") as connection:
                with self.assertRaises(SSHError) as error:
                    connection.run("read", output=Path(directory) / "image", expected_size=1)
                self.assertIsInstance(error.exception, OSError)
                self.assertNotIn("private error", str(error.exception))
                self.assertEqual(spawn.call_args.kwargs["user"], 501)
                self.assertEqual(spawn.call_args.kwargs["group"], 20)
                self.assertEqual(spawn.call_args.kwargs["extra_groups"], [20, 12])
                groups.assert_called_once_with("ordinary", 20)
                self.assertTrue(chown.called)
                self.assertEqual(fchown.call_args.args[1:], (501, 20))
