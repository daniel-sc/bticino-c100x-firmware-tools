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

    def test_flash_uses_bundled_settings_for_each_running_environment(self):
        with patch.object(self.device, "upload", wraps=self.device.upload) as upload:
            status, _ = self.invoke("flash")
        self.assertEqual(status, 0)
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
        for command in ("plan", "flash"):
            with self.subTest(command=command):
                self.assertEqual(self.invoke(command)[0], 1)
        self.assertEqual(self.device.events, ["connect", "close"])

    def test_invalid_firmware_stops_before_any_device_connection(self):
        self.prepare.return_value.__enter__.side_effect = FirmwareError("Invalid fixture image")
        for command in ("plan", "flash"):
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
