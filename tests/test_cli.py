"""Installer-free plan/flash integration with synthetic firmware and device I/O."""

import contextlib
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

    def invoke(self, command):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["classe100x", command, "fixture.fwz"]), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = cli.main()
        output = stdout.getvalue() + stderr.getvalue()
        for credentials in (C100X_PROFILE.normal, C100X_PROFILE.recovery):
            self.assertNotIn(credentials.username, output)
            self.assertNotIn(credentials.password, output)
        return status, stdout.getvalue()

    def test_plan_needs_only_firmware_and_never_starts_update(self):
        status, output = self.invoke("plan")
        self.assertEqual(status, 0)
        self.assertFalse(json.loads(output)["device_writes"])
        self.prepare.assert_called_once_with(Path("fixture.fwz"), temporary_parent=Path(".local"))
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
