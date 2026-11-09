import base64
import io
import os
import sys
import unittest
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

from classe100x import __main__ as cli
from classe100x import recovery, source_profiles, updater, wireless, wireless_image
from classe100x.updater import UpdateError
from classe100x.wireless import HostIdentityError, SSHError, Wireless
from test_resume_recovery import FIRMWARE, PROFILE, V157, V158, Device, writes


def key(label):
    return "ssh-rsa " + base64.b64encode(label.encode()).decode()


TARGET, OTHER = key("key carried by the image"), key("some other key")


def recovery_device(**options):
    """An intercom that runs the recovery installed from the image (update state 1)."""
    device = Device(**options)
    device.cleared, device.version, device.status = True, options.get("version", V158), 1
    return device


class RecoveryEntryTests(unittest.TestCase):
    def make(self):
        w = object.__new__(Wireless)
        w.host, w.in_recovery = "intercom.example", True
        w.phase, w.reconnecting = 0, False
        w.old_key = w.previous_key = None
        w.image = SimpleNamespace(host_key=TARGET)
        w.connection = w.tunnel = None
        w.host_keys, w.source_candidates = [], ()
        w.accept_regenerated_key = w.rotation_accepted = False
        w.confirm, w.trust = Mock(), Mock()
        w.existing = SimpleNamespace(connection=Mock(), password="existing")
        w.destination = SimpleNamespace(connection=Mock(), password="destination")
        return w

    def enter(self, w, observed):
        with patch.object(wireless, "resolve", return_value="192.0.2.1"), \
                patch.object(wireless, "scan_keys", return_value=observed), \
                patch.object(wireless, "Tunnel") as tunnel, patch.object(w, "preflight") as preflight:
            tunnel.return_value.ports = [23000, 23001, 23002]
            return w.__enter__(), tunnel, preflight

    def test_the_recovery_of_the_image_is_entered_with_the_image_key_and_login(self):
        w = self.make()
        entered, tunnel, preflight = self.enter(w, {TARGET})
        self.assertIs(entered, w)
        self.assertEqual(w.phase, 2)
        tunnel.assert_called_once_with(w.destination, "192.0.2.1", TARGET)
        w.destination.connection.assert_called_once_with("192.0.2.1", TARGET)
        w.existing.connection.assert_not_called()
        preflight.assert_called_once()
        w.trust.enroll.assert_not_called()
        w.trust.save.assert_not_called()

    def test_a_system_that_does_not_carry_the_image_key_is_refused_before_connecting(self):
        w = self.make()
        with self.assertRaisesRegex(HostIdentityError, "does not present the SSH host key"):
            self.enter(w, {OTHER})
        self.assertEqual(w.phase, 0)
        w.trust.enroll.assert_not_called()
        w.trust.save.assert_not_called()

    def test_ordinary_updates_still_enroll_the_source_identity(self):
        w = self.make()
        w.in_recovery = False
        w.trust.enroll.return_value = OTHER
        with patch.object(wireless, "resolve", return_value="192.0.2.1"), patch.object(w, "_connect"), \
                patch.object(w, "preflight"):
            w.source_candidates = (source_profiles.SOURCE_PROFILES[(1, 5, 8)],)
            w.__enter__()
        w.trust.enroll.assert_called_once()
        self.assertEqual(w.phase, 0)

    def test_the_only_valid_reboot_is_the_one_that_follows_the_main_installation(self):
        w = self.make()
        self.enter(w, {TARGET})
        with self.assertRaisesRegex(SSHError, "Unexpected wireless reboot transition"):
            w.rebooting(1)
        self.assertEqual(w.phase, 2)
        with patch.object(wireless, "scan_keys", return_value={TARGET}), \
                patch.object(wireless, "resolve", return_value="192.0.2.1"), \
                patch.object(wireless, "Tunnel") as tunnel, patch.object(w, "preflight"):
            tunnel.return_value.ports = [23000, 23001, 23002]
            w.rebooting(4)
            self.assertEqual((w.phase, w.reconnecting, w.previous_key), (3, True, TARGET))
            w.endpoints()
            w.arrived(4)
            w.trust.save.assert_not_called()
            w.verified()
            w.trust.save.assert_not_called()
            w.remember()
        w.trust.save.assert_called_once_with(TARGET)
        self.assertEqual(tunnel.call_args.args[0], w.destination)


class FlashRecoveryTests(unittest.TestCase):
    def test_the_final_verification_runs_after_the_main_system_is_installed(self):
        device = recovery_device()
        seen = []
        updater.flash_recovery(FIRMWARE, device, PROFILE, report=lambda message: None,
                               final_verification=lambda: seen.append(list(device.events)))
        self.assertEqual(len(seen), 1)
        for event in ("commit-btweb_only.ext4.gz", "commit-uImage.zip", "reboot-4"):
            self.assertIn(event, seen[0])

    def test_without_a_final_verification_nothing_changes(self):
        device = recovery_device()
        updater.flash_recovery(FIRMWARE, device, PROFILE, report=lambda message: None)
        self.assertEqual([e for e in device.events if e.startswith("begin")], ["begin-main"])
        self.assertEqual(device.reboots, [(4, {})])

    def test_a_failing_final_verification_is_reported_as_stopped(self):
        device = recovery_device()

        def failing():
            raise UpdateError("login refused")

        with self.assertRaisesRegex(UpdateError, "Stopped at 'final destination SSH verification'.*login refused"):
            updater.flash_recovery(FIRMWARE, device, PROFILE, report=lambda message: None,
                                   final_verification=failing)

    def test_a_source_firmware_is_refused_before_any_write(self):
        device = recovery_device(version=V157)
        with self.assertRaises(UpdateError):
            updater.flash_recovery(FIRMWARE, device, PROFILE, report=lambda message: None)
        self.assertEqual(writes(device), [])


def firmware_with_report():
    return SimpleNamespace(directory=FIRMWARE.directory, payload=FIRMWARE.payload,
                           report=lambda: {"sha256": "image"})


class RecoveryOverSshTests(unittest.TestCase):
    def run_command(self, command, device, transport=None):
        transport = Mock() if transport is None else transport
        out = io.StringIO()
        with patch.object(cli, "NetworkDevice", return_value=device), patch.object(cli, "C100X_PROFILE", PROFILE), \
                patch.object(wireless, "awake", nullcontext), redirect_stdout(out):
            cli.recovery_over_ssh(SimpleNamespace(command=command), firmware_with_report(), transport,
                                  lambda message: None)
        return transport, out.getvalue()

    def test_the_plan_only_reads(self):
        device = recovery_device()
        transport, output = self.run_command("plan-recovery", device)
        self.assertEqual(writes(device), [])
        self.assertEqual(device.events[-1], "close")
        self.assertIn('"device_writes": false', output)
        transport.remember.assert_not_called()
        transport.verified.assert_not_called()

    def test_the_plan_refuses_a_running_main_system(self):
        device = Device(version=V158)  # the target firmware, but the normal MAIN: update state 4
        with self.assertRaises(UpdateError):
            self.run_command("plan-recovery", device)
        self.assertEqual(writes(device), [])
        self.assertEqual(device.events[-1], "close")

    def test_the_plan_refuses_a_source_firmware_and_a_busy_worker(self):
        for label, device in (("source firmware", recovery_device(version=V157)),
                              ("busy worker", recovery_device(busy=True))):
            with self.subTest(label), self.assertRaises(UpdateError):
                self.run_command("plan-recovery", device)
            self.assertEqual(writes(device), [])

    def test_recover_installs_only_the_main_system(self):
        device = recovery_device()
        transport, output = self.run_command("recover", device)
        events = device.events
        self.assertEqual([e for e in events if e.startswith("begin")], ["begin-main"])
        self.assertEqual([e for e in events if e.startswith(("upload", "commit"))],
                         ["upload-btweb_only.ext4.gz", "commit-btweb_only.ext4.gz",
                          "upload-uImage.zip", "commit-uImage.zip"])
        self.assertNotIn("invalidate", events)
        self.assertNotIn("begin-recovery", events)
        self.assertEqual(device.reboots, [(4, {})])
        self.assertEqual(output, "")

    def test_recover_verifies_the_installed_system_before_remembering_it(self):
        device = recovery_device()
        order = []
        transport = Mock()
        transport.verified.side_effect = lambda: order.append("verified")
        transport.remember.side_effect = lambda: order.append("remembered")
        self.run_command("recover", device, transport)
        self.assertEqual(order, ["verified", "remembered"])
        self.assertLess(device.events.index("reboot-4"), device.events.index("close"))

    def test_recover_does_not_remember_anything_when_the_verification_fails(self):
        device = recovery_device()
        transport = Mock()
        transport.verified.side_effect = SSHError("final verification failed")
        with self.assertRaises(Exception):
            self.run_command("recover", device, transport)
        transport.remember.assert_not_called()

    def test_recover_refuses_a_running_main_system_before_any_write(self):
        device = Device(version=V158)
        with self.assertRaises(UpdateError):
            self.run_command("recover", device)
        self.assertEqual(writes(device), [])


class WirelessCommandTests(unittest.TestCase):
    """wireless_command() with everything that touches the intercom replaced."""

    def run_command(self, command):
        args = SimpleNamespace(command=command, host="intercom.example", ssh_user="root2", ssh_key=Path("key"),
                               ssh_password=False, destination_ssh_user=None, destination_ssh_key=None,
                               destination_ssh_password=False, accept_regenerated_host_key=False)
        transport, firmware = Mock(), firmware_with_report()
        transport.source_candidates = ()
        with ExitStack() as stack:
            for name in ("Credentials", "Trust"):
                stack.enter_context(patch.object(wireless, name))
            stack.enter_context(patch.object(wireless, "interruptible", nullcontext))
            stack.enter_context(patch.object(wireless, "awake", nullcontext))
            constructed = stack.enter_context(patch.object(wireless, "Wireless"))
            constructed.return_value.__enter__.return_value = transport
            stack.enter_context(patch.object(wireless_image, "admit", return_value=nullcontext(Mock())))
            verifier = stack.enter_context(patch.object(recovery, "RecoveryVerifier"))
            over_ssh = stack.enter_context(patch.object(cli, "recovery_over_ssh"))
            stack.enter_context(patch.object(cli, "NetworkDevice"))
            ordinary = stack.enter_context(patch.object(cli, "flash"))
            cli.wireless_command(args, firmware)
        return SimpleNamespace(args=args, firmware=firmware, transport=transport, constructed=constructed,
                               verifier=verifier, over_ssh=over_ssh, ordinary=ordinary)

    def test_the_recovery_commands_run_the_recovery_flow_without_the_verifier(self):
        for command in ("plan-recovery", "recover"):
            with self.subTest(command=command):
                run = self.run_command(command)
                self.assertIs(run.constructed.call_args.kwargs["in_recovery"], True)
                run.over_ssh.assert_called_once_with(run.args, run.firmware, run.transport, ANY)
                run.verifier.assert_not_called()  # it reads the partitions of a MAIN: not applicable here
                run.ordinary.assert_not_called()

    def test_the_other_commands_keep_the_ordinary_flow(self):
        run = self.run_command("flash")
        self.assertNotIn("in_recovery", run.constructed.call_args.kwargs)
        run.over_ssh.assert_not_called()
        run.verifier.assert_called_once()
        run.ordinary.assert_called_once()


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        previous = os.umask(0)
        os.umask(previous)
        self.addCleanup(os.umask, previous)

    def run_main(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["classe100x", *arguments]), redirect_stdout(out), redirect_stderr(err):
            try:
                status = cli.main()
            except SystemExit as stop:
                status = stop.code
        return status, out.getvalue(), err.getvalue()

    def test_the_commands_offer_the_ssh_options_and_keep_usb(self):
        for command in ("plan-recovery", "recover"):
            with self.subTest(command=command):
                status, out, err = self.run_main(command, "--help")
                self.assertEqual(status, 0)
                for option in ("--transport", "--host", "--ssh-user", "--ssh-password", "--ssh-key", "--tetherkit"):
                    self.assertIn(option, out)
                for option in ("--destination-ssh-user", "--accept-regenerated-host-key"):
                    self.assertNotIn(option, out)

    def test_the_ssh_options_need_the_ssh_transport(self):
        for command in ("plan-recovery", "recover"):
            for option in (["--host", "intercom.example"], ["--ssh-user", "root2"], ["--ssh-password"],
                           ["--ssh-key", "k"]):
                with self.subTest(command=command, option=option):
                    status, out, err = self.run_main(command, *option, "unused.fwz")
                    self.assertNotEqual(status, 0)
                    self.assertIn("--transport ssh", out + err)

    def test_the_ssh_transport_needs_a_login_method(self):
        for command in ("plan-recovery", "recover"):
            with self.subTest(command=command):
                status, out, err = self.run_main(command, "--transport", "ssh", "unused.fwz")
                self.assertNotEqual(status, 0)
                self.assertIn("--ssh-password or --ssh-key", out + err)

    def test_a_password_and_a_key_are_mutually_exclusive(self):
        status, out, err = self.run_main("recover", "--transport", "ssh", "--ssh-password", "--ssh-key", "k", "x.fwz")
        self.assertNotEqual(status, 0)

    def test_the_ssh_transport_runs_the_wireless_command(self):
        for command, message in (("plan-recovery", True), ("recover", False)):
            with self.subTest(command=command):
                with patch.object(cli, "prepare_firmware",
                                  return_value=nullcontext(SimpleNamespace(report=lambda: {}))), \
                        patch.object(cli, "wireless_command") as wireless_command:
                    status, out, err = self.run_main(command, "--transport", "ssh", "--ssh-key", "k", "fw.fwz")
                self.assertEqual(status, 0)
                wireless_command.assert_called_once()
                args = wireless_command.call_args.args[0]
                self.assertEqual((args.command, args.transport, args.destination_ssh_user,
                                  args.destination_ssh_key, args.destination_ssh_password),
                                 (command, "ssh", None, None, False))
                self.assertEqual("No firmware was written" in err, message)


if __name__ == "__main__":
    unittest.main()
