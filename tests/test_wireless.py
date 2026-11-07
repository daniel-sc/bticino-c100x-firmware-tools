"""Offline transport/identity contracts; never resolve or connect a real device."""

from contextlib import ExitStack
import base64
import ftplib
import json
import os
from pathlib import Path
import pwd
import shlex
import struct
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from classe100x import wireless
from classe100x.firmware import FirmwareError
from classe100x.ssh import SSHConnection, SSHError, HostIdentityError
from classe100x.updater import ForwardedFTP, NetworkDevice, UpdateError, UncertainDelivery
from classe100x.wireless_image import Destination, check_password


def key(marker):
    fields = (b"ecdsa-sha2-nistp256", b"nistp256", b"\x04" + bytes([marker]) * 64)
    blob = b"".join(struct.pack(">I", len(x)) + x for x in fields)
    return fields[0].decode() + " " + base64.b64encode(blob).decode()


OLD, NEW, UNKNOWN = key(1), key(2), key(3)


class WirelessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.account = pwd.getpwuid(os.getuid())
        self.enterContext(patch("classe100x.ssh._invoking_user", return_value=self.account))
        self.enterContext(patch("classe100x.wireless._invoking_user", return_value=self.account))
        self.enterContext(patch("classe100x.ssh.os.geteuid", return_value=self.account.pw_uid or 501))

    def transport(self):
        trust = Mock()
        trust.enroll.return_value = OLD
        w = wireless.Wireless("intercom.local", wireless.Credentials("root2", password="old-password"),
                              wireless.Credentials("root2", password="new-password"),
                              Destination(NEW, False), trust, confirm=Mock(return_value=True))
        w.old_key, w.ip = OLD, "192.0.2.1"
        return w

    def test_all_identity_and_credential_transitions(self):
        w = self.transport()
        connections = []
        def connection(credentials, host, public, **kwargs):
            c = Mock()
            connections.append((credentials.password, host, public))
            return c
        with patch.object(wireless.Credentials, "connection", autospec=True, side_effect=connection), \
                patch.object(wireless, "Tunnel") as tunnel, \
                patch.object(wireless, "scan_keys", side_effect=[{OLD}, {OLD}, {NEW}, {NEW}]), \
                patch.object(wireless, "resolve", side_effect=["192.0.2.2", "192.0.2.3", "192.0.2.4"]), \
                patch.object(w, "preflight"):
            tunnel.return_value.ports = [23000, 23001, 23002]
            w._connect()
            for status in (4, 1, 4):
                w.rebooting(status)
                self.assertTrue(w.reconnecting)
                self.assertEqual(w.endpoints(), ("127.0.0.1", 23000, 23001, 23002))
                w.arrived(status)
                self.assertFalse(w.reconnecting)
            w.trust.save.assert_not_called()
            w.verified()
            w.trust.save.assert_not_called()
            w.remember()
            w.trust.save.assert_called_once_with(NEW)
            w.close()
        self.assertEqual(connections, [("old-password", "192.0.2.1", OLD),
                                       ("old-password", "192.0.2.2", OLD),
                                       ("new-password", "192.0.2.3", NEW),
                                       ("new-password", "192.0.2.4", NEW)])

    def test_known_previous_identity_is_not_ready_but_unknown_is_fatal(self):
        w = self.transport()
        w.phase, w.reconnecting, w.previous_key = 2, True, OLD
        with patch.object(wireless, "scan_keys", return_value={OLD}), patch.object(wireless, "Tunnel") as tunnel:
            with self.assertRaises(SSHError) as result:
                w._connect()
            self.assertNotIsInstance(result.exception, HostIdentityError)
            tunnel.assert_not_called()
        with patch.object(wireless, "scan_keys", return_value={UNKNOWN}):
            with self.assertRaises(HostIdentityError):
                w._connect()
        with self.assertRaises(SSHError):
            w.verified()
        with self.assertRaises(SSHError):
            w.remember()
        w.trust.save.assert_not_called()

    def test_existing_ssh_eligibility_uses_access_and_reboot_identity(self):
        w = self.transport()
        connection = Mock()
        pins = wireless.facts("no-ota")["UNCHANGED"]
        paths = ["/home/bticino/bin/" + name for name in ("bt_device", "bt_daemon", "fw_manager", "dedrifupdater")]
        def read(command, **kwargs):
            if command == 'test "$(id -u)" = 0':
                return b""
            if command == wireless.installer_check():
                return b"READY\n"
            if command == "sha256sum " + " ".join(paths):
                return "".join(f"{pins[path][0]}  {path}\n" for path in paths).encode()
            self.fail("Preflight required a particular SSH startup implementation: " + command)
        connection.run.side_effect = read
        with patch.object(wireless, "resolve", return_value="192.0.2.1"), \
                patch.object(wireless, "scan_keys", return_value={OLD}) as scan, \
                patch.object(wireless.Credentials, "connection", return_value=connection), \
                patch.object(wireless, "Tunnel") as tunnel:
            tunnel.return_value.ports = [23000, 23001, 23002]
            with w:
                w.rebooting(4)
                w.endpoints()
                w.arrived(4)
                self.assertEqual(w.phase, 1)
                self.assertFalse(w.reconnecting)
                connection.run.assert_any_call('test "$(id -u)" = 0', timeout=10)

                # A regenerated identity on old main still stops reconnection;
                # relaxing startup spelling does not relax continuity.
                w.close()
                w.reconnecting = True
                scan.return_value = {UNKNOWN}
                tunnel.reset_mock()
                with self.assertRaises(HostIdentityError):
                    w.endpoints()
                tunnel.assert_not_called()

    def test_dead_reconnect_tunnel_is_reaped_without_retrying_writes(self):
        w = self.transport()
        w.reconnecting = True
        w.tunnel = Mock()
        w.tunnel.check.side_effect = SSHError("disconnected")
        tunnel = w.tunnel
        with self.assertRaises(SSHError):
            w.endpoints()
        tunnel.close.assert_called_once()
        self.assertIsNone(w.tunnel)

    def test_active_tunnel_loss_does_not_trigger_automatic_reconnect(self):
        w = self.transport()
        w.tunnel = Mock()
        w.tunnel.check.side_effect = SSHError("disconnected")
        with patch.object(w, "_connect") as connect, self.assertRaises(SSHError):
            w.endpoints()
        connect.assert_not_called()

    def test_cleanup_failure_still_closes_tunnel_and_discards_passwords(self):
        for tunnel_error in (None, SSHError("tunnel cleanup failed")):
            w = self.transport()
            connection, tunnel = Mock(), Mock()
            w.connection, w.tunnel = connection, tunnel
            first_error = SSHError("reader cleanup failed")
            connection.close.side_effect = first_error
            tunnel.close.side_effect = tunnel_error
            with self.assertRaises(SSHError) as result:
                w.__exit__(None, None, None)
            self.assertIs(result.exception, first_error)
            tunnel.close.assert_called_once()
            self.assertIsNone(w.connection)
            self.assertIsNone(w.tunnel)
            self.assertIsNone(w.existing.password)
            self.assertIsNone(w.destination.password)

        w = self.transport()
        w.connection, w.tunnel = Mock(), Mock()
        w.connection.close.side_effect = SSHError("reader cleanup failed")
        original = SSHError("write outcome uncertain")
        tunnel = w.tunnel
        with self.assertRaises(SSHError) as result:
            try:
                raise original
            except SSHError as error:
                w.__exit__(type(error), error, error.__traceback__)
                raise
        self.assertIs(result.exception, original)
        self.assertTrue(any("reader cleanup failed" in note for note in original.__notes__))
        tunnel.close.assert_called_once()
        self.assertIsNone(w.existing.password)
        self.assertIsNone(w.destination.password)

    def test_passive_ftp_uses_local_mapping_and_rejects_other_ports(self):
        ftp = ForwardedFTP()
        ftp.data_port = 23002
        with patch.object(ftplib.FTP, "makepasv", return_value=("203.0.113.99", 11111)):
            self.assertEqual(ftp.makepasv(), ("127.0.0.1", 23002))
        with patch.object(ftplib.FTP, "makepasv", return_value=("203.0.113.99", 22)):
            with self.assertRaises(UpdateError):
                ftp.makepasv()

    def test_recovery_verifier_borrows_connection_without_closing_transport(self):
        owner = Mock(uid=123, gid=456, host_keys=[])
        reader = wireless.VerificationReader(owner)
        reader.__enter__()
        reader.run("read-only", timeout=10)
        reader.close()
        owner.run.assert_called_once_with("read-only", timeout=10)
        owner.close.assert_not_called()
        self.assertTrue(reader.strict)

    def test_strict_host_key_options_and_forward_lifecycle_options(self):
        c = SSHConnection("root2", host="192.0.2.1", host_key=OLD)
        args = c._command("true", self.root / "hosts", 10)
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("Hostname=192.0.2.1", args)
        t = wireless.Tunnel(wireless.Credentials("root2"), "192.0.2.1", NEW)
        t._directory, t.ports = self.root, [23000, 23001, 23002]
        args = t._command("", self.root / "hosts", 10)
        self.assertLess(args.index("ControlMaster=yes"), args.index("ControlMaster=no"))
        self.assertLess(args.index("ClearAllForwardings=no"), args.index("ClearAllForwardings=yes"))
        for local, remote in zip(t.ports, (20000, 21, 11111)):
            self.assertIn(f"127.0.0.1:{local}:127.0.0.1:{remote}", args)
        self.assertIn("-N", args)

    def test_trust_enrollment_and_changed_key_rejection(self):
        with wireless.Trust("intercom.local", parent=self.root / "trust") as trust:
            with patch.object(trust, "known", return_value=set()), patch.object(wireless, "scan_keys", return_value={OLD}):
                confirm = Mock(return_value=True)
                self.assertEqual(trust.enroll("192.0.2.1", confirm), OLD)
                confirm.assert_called_once_with("intercom.local", wireless.fingerprint(OLD))
            self.assertFalse(trust.path.exists())
            trust.save(OLD)
            self.assertEqual(trust.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(trust.known("192.0.2.2"), {OLD})
            with patch.object(wireless, "scan_keys", return_value={UNKNOWN}):
                confirm = Mock()
                with self.assertRaises(HostIdentityError):
                    trust.enroll("192.0.2.2", confirm)
                confirm.assert_not_called()
            self.assertEqual(json.loads(trust.path.read_text())["key"], OLD)

    def test_unconfirmed_identity_and_concurrent_target_are_rejected(self):
        with wireless.Trust("intercom.local", parent=self.root / "trust") as trust:
            with patch.object(trust, "known", return_value=set()), patch.object(wireless, "scan_keys", return_value={OLD}):
                with self.assertRaises(HostIdentityError):
                    trust.enroll("192.0.2.1", Mock(return_value=False))
            with self.assertRaises(SSHError):
                with wireless.Trust("intercom.local", parent=self.root / "trust"):
                    self.fail("second owner")
            self.assertFalse(trust.path.exists())

    def test_named_trust_cannot_be_overridden_by_reassigned_address(self):
        known = self.root / ".ssh/known_hosts"
        known.parent.mkdir()
        known.touch()
        with wireless.Trust("intercom.local", parent=self.root / "trust") as trust:
            trust.account = SimpleNamespace(pw_dir=str(self.root))
            entries = {"intercom.local": OLD, "192.0.2.1": UNKNOWN}
            def lookup(args, **kwargs):
                host = args[2]
                return 0, (f"{host} {entries[host]}\n".encode() if host in entries else b""), b""
            confirm = Mock()
            with patch.object(wireless, "run_tool", side_effect=lookup), \
                    patch.object(wireless, "scan_keys", return_value={UNKNOWN}) as scan:
                with self.assertRaises(HostIdentityError):
                    trust.enroll("192.0.2.1", confirm)
                confirm.assert_not_called()
                scan.return_value = {OLD}
                self.assertEqual(trust.enroll("192.0.2.1", confirm), OLD)
                del entries["intercom.local"]
                scan.return_value = {UNKNOWN}
                self.assertEqual(trust.enroll("192.0.2.1", confirm), UNKNOWN)

    def test_identity_failure_is_not_swallowed_by_reboot_poll(self):
        transport = Mock()
        transport.endpoints.side_effect = HostIdentityError("changed")
        device = NetworkDevice("127.0.0.1", transport=transport)
        client = Mock()
        client.query.return_value = ("0", "0", "2", "0")
        device.client = client
        with patch("classe100x.updater.time.sleep"), self.assertRaises(HostIdentityError):
            device.reboot_and_wait(1)
        client.reboot.assert_called_once()
        transport.rebooting.assert_called_once_with(1)
        transport.arrived.assert_not_called()

    def test_uncertain_reboot_does_not_advance_identity_phase(self):
        transport = Mock()
        device = NetworkDevice("127.0.0.1", transport=transport)
        client = Mock()
        client.query.return_value = ("0", "0", "2", "0")
        client.reboot.side_effect = UncertainDelivery("lost acknowledgement")
        device.client = client
        with self.assertRaises(UncertainDelivery):
            device.reboot_and_wait(1)
        client.reboot.assert_called_once()
        transport.rebooting.assert_not_called()

    def test_system_openssh_accepts_forwarding_configuration_offline(self):
        t = wireless.Tunnel(wireless.Credentials("root2"), "192.0.2.1", OLD)
        t._directory, t.ports = self.root / "with spaces", [23000, 23001, 23002]
        args = t._command("", self.root / "hosts", 10)
        result = subprocess.run([args[0], "-G", *args[1:]], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("controlmaster true", result.stdout)
        self.assertIn("clearallforwardings no", result.stdout)
        self.assertIn("stricthostkeychecking true", result.stdout)

    def test_resolution_ambiguity_is_not_first_address_wins(self):
        with patch.object(wireless, "pipe_tool", return_value=b"192.0.2.1\n192.0.2.2\n"):
            with self.assertRaises(HostIdentityError):
                wireless.resolve("intercom.local")

    def test_destination_key_checks_private_key_sidecar_and_agent(self):
        credentials = wireless.Credentials("root2", key=self.root / "login")
        sidecar = self.root / "login.pub"
        sidecar.write_text(OLD)
        with patch.object(wireless, "pipe_tool", return_value=NEW.encode()):
            with self.assertRaisesRegex(FirmwareError, "sidecar differs"):
                credentials.public_keys()
        with patch.object(wireless, "pipe_tool", side_effect=[FirmwareError("encrypted"), NEW.encode()]):
            with self.assertRaisesRegex(FirmwareError, "not unlocked"):
                credentials.public_keys()
        with patch.object(wireless, "pipe_tool", side_effect=[FirmwareError("encrypted"), OLD.encode()]):
            self.assertEqual(credentials.public_keys(), {OLD})

    def test_installer_snapshot_rejects_staged_packages_flags_and_active_process(self):
        extra, proc = self.root / "extra", self.root / "proc"
        (extra / "FW").mkdir(parents=True)
        (extra / "update_flags").mkdir()
        (proc / "1").mkdir(parents=True)
        comm = proc / "1/comm"
        comm.write_text("fw_manager\n")
        command = wireless.installer_check().replace('test "$(id -u)" = 0', ':')
        command = command.replace("/home/bticino/cfg/extra", shlex.quote(str(extra))).replace("/proc/", shlex.quote(str(proc)) + "/")
        def check(expected):
            result = subprocess.run(["/bin/sh", "-c", command], capture_output=True, timeout=5)
            self.assertEqual(result.returncode == 0, expected, result.stderr)
        check(True)
        for path in (extra / "UPGRADE.fwz", extra / "FW/UPGRADE.fwz", extra / "update_flags/DEDRIFU_RUNNING"):
            path.touch()
            check(False)
            path.unlink()
        comm.write_text("dedrifupdater\n")
        check(False)

    def test_password_check_uses_stdin_not_argv_or_files(self):
        encoded = b"$6$salt$" + b"a" * 86
        with patch("classe100x.wireless_image.pipe_tool", return_value=encoded + b"\n") as run:
            check_password("secret", encoded, "/trusted/openssl")
            self.assertNotIn("secret", repr(run.call_args.args))
            self.assertEqual(run.call_args.kwargs["secret"], "secret")
        with patch("classe100x.wireless_image.pipe_tool", return_value=b"wrong"):
            with self.assertRaises(FirmwareError):
                check_password("secret", encoded, "/trusted/openssl")

    def test_memory_only_pipe_helper_and_output_bound(self):
        from classe100x.wireless_image import pipe_tool
        import sys
        self.assertEqual(pipe_tool([sys.executable, "-c", "import sys; print(sys.stdin.readline().strip())"], secret="private"), b"private\n")
        with self.assertRaisesRegex(FirmwareError, "output exceeded"):
            pipe_tool([sys.executable, "-c", "print('x'*100000)"])

    def test_supervised_tunnel_uses_password_broker_and_reaps_process(self):
        import sys
        real_popen = subprocess.Popen
        script = self.root / "fake-master.py"
        script.write_text("""import os,sys,time,subprocess
from pathlib import Path
args=sys.argv[1:]
known=next(a.split('=',1)[1].strip(chr(34)) for a in args if a.startswith('UserKnownHostsFile='))
assert 'ecdsa-sha2-nistp256' in Path(known).read_text()
assert 'StrictHostKeyChecking=yes' in args
answer=subprocess.run([os.environ['SSH_ASKPASS']],capture_output=True)
assert answer.stdout==b'private-password\\n' and answer.returncode==0
control=next(a.split('=',1)[1].strip(chr(34)) for a in args if a.startswith('ControlPath='))
Path(control).touch()
while True: time.sleep(1)
""")
        children = []
        def spawn(args, **kwargs):
            process = real_popen([sys.executable, str(script), *args[1:]], **kwargs)
            children.append(process)
            return process
        t = wireless.Tunnel(wireless.Credentials("root2", password="private-password"), "192.0.2.1", OLD)
        with patch("classe100x.ssh.subprocess.Popen", side_effect=spawn), \
                patch("classe100x.wireless.subprocess.run", return_value=Mock(returncode=0)):
            try:
                t.start()
                directory = t._directory
                self.assertTrue(t.thread.is_alive())
            finally:
                t.close()
        self.assertTrue(all(p.poll() is not None for p in children))
        self.assertFalse(directory.exists())

    def test_sleep_assertion_released_on_error(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(wireless.subprocess, "Popen", return_value=process), patch.object(wireless.time, "sleep"):
            with self.assertRaises(RuntimeError):
                with wireless.awake():
                    raise RuntimeError("stop")
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)
