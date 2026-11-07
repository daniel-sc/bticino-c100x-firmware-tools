"""Installer-free plan/flash integration with synthetic firmware and device I/O."""

import contextlib
import builtins
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from classe100x import __main__ as cli
from classe100x.firmware import FirmwareError, Payload, PreparedFirmware
from classe100x.vendor import C100X_PROFILE
from test_updater import SimulatedDevice, identity


class CliTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(contextlib.chdir(directory))
        old_umask = os.umask(0o077)
        self.addCleanup(os.umask, old_umask)
        self.enterContext(patch.dict(sys.modules, {"bitrock_unpacker": None}))
        self.prepared = PreparedFirmware(Path(directory), "synthetic", tuple(
            Payload(name, 100, "synthetic", 123) for name in (
                "btweb_only.ext4.gz", "btweb_only_recovery.ext4.gz", "uImage.zip",
            )
        ))
        self.prepare = self.enterContext(patch.object(cli, "prepare_firmware"))
        self.prepare.return_value.__enter__.return_value = self.prepared
        self.probe = self.enterContext(patch.object(cli, "ReadOnlyClient"))
        self.probe.return_value.__enter__.return_value.inspect.return_value = identity()
        self.device = SimulatedDevice()
        self.network = self.enterContext(patch.object(cli, "NetworkDevice", return_value=self.device))
        self.usb = self.enterContext(patch.object(cli, "usb_session"))
        self.check_transport = self.usb.return_value.__enter__.return_value

    def invoke(self, command, *options):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["classe100x", command, "fixture.fwz", *options]), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = cli.main()
        output = stdout.getvalue() + stderr.getvalue()
        self.last_output = output
        for credentials in (C100X_PROFILE.normal, C100X_PROFILE.recovery):
            self.assertNotIn(credentials.username, output)
            self.assertNotIn(credentials.password, output)
        return status, stdout.getvalue()

    def test_plan_needs_only_firmware_and_never_starts_update(self):
        status, output = self.invoke("plan")
        self.assertEqual(status, 0)
        self.assertFalse(json.loads(output)["device_writes"])
        self.prepare.assert_called_once_with(Path("fixture.fwz"))
        self.usb.assert_called_once()
        self.usb.return_value.__exit__.assert_called_once()
        self.check_transport.assert_called_once()
        self.network.assert_not_called()
        self.assertEqual(self.device.events, [])

    def test_wireless_plan_is_read_only_and_gate_is_mandatory(self):
        with patch("classe100x.wireless.Credentials"), patch("classe100x.wireless.Trust"), \
                patch("classe100x.wireless.Wireless") as transport, \
                patch("classe100x.wireless_image.admit") as admission, \
                patch("classe100x.recovery.RecoveryVerifier") as verifier:
            admission.return_value.__enter__.return_value.vendor_updates = False
            active = transport.return_value.__enter__.return_value
            active.endpoints.return_value = ("127.0.0.1", 23000, 23001, 23002)
            status, output = self.invoke("plan", "--transport", "ssh", "--host", "intercom.local")
            self.assertEqual(status, 0, self.last_output)
            result = json.loads(output)
            self.assertFalse(result["device_writes"])
            self.assertEqual(result["host"], "intercom.local")
            verifier.return_value.__enter__.return_value.preflight.assert_called_once()
            verifier.return_value.__enter__.return_value.verify.assert_not_called()
            active.verified.assert_not_called()
            self.network.assert_not_called()
            self.usb.assert_not_called()

    def test_wireless_flash_and_failed_admission_never_fall_back_to_usb(self):
        with patch("classe100x.wireless.Credentials"), patch("classe100x.wireless.Trust"), \
                patch("classe100x.wireless.awake"), patch("classe100x.wireless.Wireless") as transport, \
                patch("classe100x.wireless_image.admit") as admission, \
                patch("classe100x.recovery.RecoveryVerifier") as verifier:
            self.assertEqual(self.invoke("flash", "--transport", "ssh")[0], 0, self.last_output)
            gate = verifier.return_value.__enter__.return_value
            gate.preflight.assert_called_once()
            gate.verify.assert_called_once()
            transport.return_value.__enter__.return_value.verified.assert_called_once()
            active = transport.return_value.__enter__.return_value
            active.remember.assert_called_once()
            self.usb.assert_not_called()
            active.remember.reset_mock()
            active.verified.side_effect = OSError("final SSH unavailable")
            self.assertEqual(self.invoke("flash", "--transport", "ssh")[0], 1)
            self.assertNotIn("Update sequence completed", self.last_output)
            active.remember.assert_not_called()
            gate.update_result.assert_called_with("stopped", "final destination SSH verification")
            self.network.reset_mock()
            self.device.events.clear()
            admission.return_value.__enter__.side_effect = FirmwareError("invalid destination")
            self.assertEqual(self.invoke("flash", "--transport", "ssh")[0], 1)
            self.network.assert_not_called()
            self.usb.assert_not_called()
            self.assertEqual(self.device.events, [])

    def test_debug_and_unexpected_errors_include_tracebacks(self):
        for error, options, traceback_expected in (
                (FirmwareError("fixture invalid"), (), False),
                (FirmwareError("fixture invalid"), ("--debug",), True),
                (RuntimeError("fixture bug"), (), True)):
            self.prepare.side_effect = error
            self.assertEqual(self.invoke("inspect-fw", *options)[0], 1)
            self.assertEqual("Traceback (most recent call last)" in self.last_output, traceback_expected)
            self.assertIn(str(error), self.last_output)

    def test_worker_forwards_diagnostics_readiness_and_failure_as_json(self):
        for fail in (False, True):
            output = io.StringIO()

            def run_usb(binary, *, notify, diagnostic):
                diagnostic("USB fixture starting")
                notify("feth42")
                if fail:
                    raise OSError("USB fixture stopped")

            with patch.object(sys, "argv", ["classe100x", "_usb-worker", "fixture-helper"]), \
                    patch.object(cli, "run_usb", side_effect=run_usb), contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(), 1 if fail else 0)
            messages = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(messages[:2], [{"diagnostic": "USB fixture starting"}, {"interface": "feth42"}])
            if fail:
                self.assertIn("OSError: USB fixture stopped", messages[2]["diagnostic"])

    def test_recovery_plan_is_read_only_and_requires_idle_recovery(self):
        client = self.probe.return_value.__enter__.return_value
        client.inspect.return_value = identity(1)
        client.idle.return_value = True
        status, output = self.invoke("plan-recovery")
        self.assertEqual(status, 0)
        result = json.loads(output)
        self.assertFalse(result["device_writes"])
        self.assertTrue(result["worker_idle"])
        self.assertEqual(result["sequence"], ["main filesystem", "main kernel", "reboot to normal"])
        self.network.assert_not_called()
        self.usb.assert_called_once()
        client.idle.return_value = False
        self.assertEqual(self.invoke("plan-recovery")[0], 1)
        client.inspect.return_value = identity(4)
        self.assertEqual(self.invoke("plan-recovery")[0], 1)

    def test_recover_uses_recovery_credentials_and_only_main_payloads(self):
        self.device.initial = identity(1)
        with patch.object(self.device, "upload", wraps=self.device.upload) as upload:
            status, _ = self.invoke("recover")
        self.assertEqual(status, 0)
        self.assertEqual([call.args[0].name for call in upload.call_args_list],
                         ["btweb_only.ext4.gz", "uImage.zip"])
        self.assertTrue(all(call.args[1] is C100X_PROFILE.recovery for call in upload.call_args_list))
        self.assertEqual([e for e in self.device.events if e.startswith("reboot")], ["reboot-4"])
        self.assertNotIn("invalidate-main-kernel", self.device.events)
        self.usb.assert_called_once()
        self.usb.return_value.__exit__.assert_called_once()

    def test_flash_uses_bundled_settings_for_each_running_environment(self):
        with patch.object(self.device, "upload", wraps=self.device.upload) as upload:
            status, _ = self.invoke("flash")
        self.assertEqual(status, 0)
        self.assertIs(self.network.call_args.kwargs["before_reboot"], cli.unmount_usb_storage)
        expected = (C100X_PROFILE.normal, C100X_PROFILE.normal,
                    C100X_PROFILE.recovery, C100X_PROFILE.recovery)
        self.assertEqual(upload.call_count, 4)
        for call, credentials in zip(upload.call_args_list, expected):
            self.assertIs(call.args[1], credentials)
        self.assertEqual([e for e in self.device.events if e.startswith("reboot")],
                         ["reboot-4", "reboot-1", "reboot-4"])

    def test_wrong_device_is_still_rejected_without_transfers(self):
        info = identity()
        info["object_model"] = ("1", "0", "98")
        self.probe.return_value.__enter__.return_value.inspect.return_value = info
        self.device.initial = info
        for command in ("plan", "flash", "plan-recovery", "recover"):
            with self.subTest(command=command):
                self.assertEqual(self.invoke(command)[0], 1)
        self.assertEqual(self.device.events, ["connect", "close", "connect", "close"])

    def test_invalid_firmware_stops_before_any_device_connection(self):
        self.prepare.return_value.__enter__.side_effect = FirmwareError("Invalid fixture image")
        for command in ("plan", "flash", "plan-recovery", "recover"):
            with self.subTest(command=command):
                self.assertEqual(self.invoke(command)[0], 1)
        self.probe.assert_not_called()
        self.network.assert_not_called()
        self.usb.assert_not_called()

    def test_ssh_options_require_explicit_mode_account_and_managed_usb(self):
        invalid = [
            ("--verify-recovery-ssh",),
            ("--ssh-user", "admin"),
            ("--ssh-key", "fixture-key"),
            ("--ssh-password",),
            ("--verify-recovery-ssh", "--ssh-user", "admin", "--external-usb"),
        ]
        for command in ("plan", "flash"):
            for options in invalid:
                with self.subTest(command=command, options=options):
                    self.assertEqual(self.invoke(command, *options)[0], 1)
        self.prepare.assert_not_called()
        self.usb.assert_not_called()
        self.network.assert_not_called()

    def test_ssh_key_and_password_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit) as caught:
            self.invoke("flash", "--verify-recovery-ssh", "--ssh-user", "admin",
                        "--ssh-key", "fixture-key", "--ssh-password")
        self.assertEqual(caught.exception.code, 2)
        self.prepare.assert_not_called()
        self.usb.assert_not_called()

    def optional_verifier(self):
        connection = self.enterContext(patch("classe100x.ssh.SSHConnection"))
        factory = self.enterContext(patch("classe100x.recovery.RecoveryVerifier"))
        gate = factory.return_value.__enter__.return_value
        gate.directory = Path("private-evidence")
        return connection, factory, gate

    def test_optional_plan_checks_prerequisites_without_readback_or_writes(self):
        connection, factory, gate = self.optional_verifier()
        status, output = self.invoke("plan", "--verify-recovery-ssh", "--ssh-user", "admin")
        self.assertEqual(status, 0)
        result = json.loads(output)
        self.assertFalse(result["device_writes"])
        self.assertEqual(result["verification_report"], "private-evidence/report.json")
        self.assertEqual(result["sequence"][3], "SSH recovery integrity verification")
        gate.preflight.assert_called_once_with()
        gate.verify.assert_not_called()
        self.network.assert_not_called()
        self.assertEqual(self.device.events, [])
        self.assertIs(connection.call_args.kwargs["check_transport"], self.check_transport)
        self.assertIs(factory.call_args.args[0], self.prepared)

    def test_optional_plan_failure_never_starts_update(self):
        from classe100x.updater import UpdateError
        _, _, gate = self.optional_verifier()
        gate.preflight.side_effect = UpdateError("SSH prerequisites failed")
        self.assertEqual(self.invoke("plan", "--verify-recovery-ssh", "--ssh-user", "admin")[0], 1)
        gate.verify.assert_not_called()
        self.network.assert_not_called()
        self.assertEqual(self.device.events, [])

    def test_password_is_prompted_once_passed_in_memory_and_not_printed(self):
        secret = "synthetic-password-never-log-23"
        connection, _, gate = self.optional_verifier()
        with patch.object(sys.stdin, "isatty", return_value=True), \
                patch.object(cli.getpass, "getpass", return_value=secret) as prompt:
            status, _ = self.invoke("flash", "--verify-recovery-ssh", "--ssh-user", "admin",
                                    "--ssh-password")
        self.assertEqual(status, 0)
        prompt.assert_called_once()
        connection.assert_called_once()
        self.assertEqual(connection.call_args.kwargs["password"], secret)
        self.assertEqual(connection.call_args.args, ("admin",))
        self.assertNotIn(secret, self.last_output)
        self.assertNotIn(secret, repr(dict(os.environ)))
        gate.preflight.assert_called_once()
        gate.verify.assert_called_once()

    def test_password_requires_terminal_before_any_update(self):
        connection, _, gate = self.optional_verifier()
        with patch.object(sys.stdin, "isatty", return_value=False), \
                patch.object(cli.getpass, "getpass") as prompt:
            status, _ = self.invoke("flash", "--verify-recovery-ssh", "--ssh-user", "admin",
                                    "--ssh-password")
        self.assertEqual(status, 1)
        prompt.assert_not_called()
        connection.assert_not_called()
        gate.preflight.assert_not_called()
        self.assertEqual(self.device.events, [])

    def test_key_path_is_passed_without_password_prompt(self):
        connection, _, _ = self.optional_verifier()
        with patch.object(cli.getpass, "getpass") as prompt:
            status, _ = self.invoke("plan", "--verify-recovery-ssh", "--ssh-user", "admin",
                                    "--ssh-key", "fixture-key")
        self.assertEqual(status, 0)
        self.assertEqual(connection.call_args.kwargs["key"], Path("fixture-key"))
        self.assertIsNone(connection.call_args.kwargs["password"])
        prompt.assert_not_called()

    def test_ordinary_plan_and_flash_do_not_import_optional_or_builder_modules(self):
        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.split(".")[-1] in {"builder", "ext4", "host", "ssh", "recovery"}:
                raise AssertionError(f"Ordinary flashing imported optional module {name}")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            for command in ("plan", "flash"):
                with self.subTest(command=command):
                    self.assertEqual(self.invoke(command)[0], 0)
