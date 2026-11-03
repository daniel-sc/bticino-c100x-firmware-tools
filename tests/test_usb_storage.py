import plistlib
import subprocess
import unittest
from unittest.mock import patch

from classe100x.usb_storage import unmount_usb_storage


def device(disk="disk7", *, vendor=0x1da4, media_id=101):
    return {"idVendor": vendor, "idProduct": 0x0056, "IORegistryEntryID": 100,
            "IORegistryEntryChildren": [{"IOObjectClass": "IOMedia", "Whole": True,
                                         "BSD Name": disk, "IORegistryEntryID": media_id}]}


def listing(disk="disk7", mounted=True):
    volume = {"DeviceIdentifier": disk + "s1"}
    if mounted:
        volume["MountPoint"] = "/Volumes/fixture"
    return {"AllDisksAndPartitions": [{"DeviceIdentifier": disk, "Partitions": [volume]}]}


class USBStorageTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("classe100x.usb_storage.sys.platform", "darwin"))
        self.run = self.enterContext(patch("classe100x.usb_storage.subprocess.run"))
        self.warnings = []

    def responses(self, *values):
        self.run.side_effect = [subprocess.CompletedProcess([], 0, plistlib.dumps(value))
                                if not isinstance(value, BaseException) else value for value in values]

    def unmount(self):
        unmount_usb_storage(warn=self.warnings.append)

    def test_usb_ancestry_not_volume_name_and_normal_unmount(self):
        self.responses([device(vendor=123), device()], listing(), [device()], {})
        self.unmount()
        self.assertEqual(self.run.call_args_list[-1].args[0],
                         ["/usr/sbin/diskutil", "unmountDisk", "/dev/disk7"])
        self.assertEqual(self.warnings, [])
        self.assertTrue(all(0 < call.kwargs["timeout"] <= 5 for call in self.run.call_args_list))

    def test_rediscover_changed_disk_number_on_each_reboot(self):
        for disk in ("disk7", "disk8", "disk12"):
            self.responses([device(disk)], listing(disk), [device(disk)], {})
            self.unmount()
            self.assertEqual(self.run.call_args.args[0][-1], "/dev/" + disk)

    def test_absent_unrelated_and_ambiguous_devices_do_not_unmount(self):
        for devices in ([], [device(vendor=123)], [device(), device("disk8")]):
            self.responses(devices)
            self.run.reset_mock()
            self.unmount()
            self.assertEqual(self.run.call_count, 1)
        self.run.side_effect = None
        self.run.return_value = subprocess.CompletedProcess([], 0, b"")
        self.unmount()

    def test_ambiguous_missing_or_invalid_media_is_skipped(self):
        two_disks = device()
        two_disks["IORegistryEntryChildren"] += device("disk8")["IORegistryEntryChildren"]
        no_disk = device()
        no_disk["IORegistryEntryChildren"] = []
        for node in (two_disks, no_disk, device("disk7s1"), device(media_id="unknown")):
            self.responses([node])
            self.run.reset_mock()
            self.unmount()
            self.assertEqual(self.run.call_count, 1)

    def test_unmounted_storage_needs_no_unmount(self):
        self.responses([device()], listing(mounted=False))
        self.unmount()
        self.assertEqual(self.run.call_count, 2)
        self.assertEqual(self.warnings, [])

    def test_disk_replacement_or_wrong_listing_is_skipped(self):
        self.responses([device()], listing(), [device(media_id=202)])
        self.unmount()
        self.assertEqual(self.run.call_count, 3)
        self.assertTrue(self.warnings)
        self.responses([device()], listing("disk8"))
        self.run.reset_mock()
        self.unmount()
        self.assertEqual(self.run.call_count, 2)

    def test_command_failures_timeouts_and_malformed_data_warn_only(self):
        for index in range(4):
            for error in (OSError("private diagnostic"), subprocess.TimeoutExpired("fixture", 5)):
                values = [[device()], listing(), [device()], {}]
                values[index] = error
                self.responses(*values)
                self.run.reset_mock()
                self.unmount()
                self.assertEqual(self.run.call_count, index + 1)
                self.assertNotIn("private diagnostic", self.warnings[-1])
        self.run.side_effect = None
        for result in (subprocess.CompletedProcess([], 1, b"private diagnostic"),
                       subprocess.CompletedProcess([], 0, b"malformed")):
            self.run.return_value = result
            self.unmount()
            self.assertTrue(self.warnings)

    def test_total_budget_stays_below_command_idle_timeout(self):
        clock = [0]
        values = iter(([device()], listing(), [device()], {}))

        def run(*args, **kwargs):
            clock[0] += 3
            return subprocess.CompletedProcess([], 0, plistlib.dumps(next(values)))

        self.run.side_effect = run
        with patch("classe100x.usb_storage.time.monotonic", side_effect=lambda: clock[0]):
            self.unmount()
        self.assertEqual([call.kwargs["timeout"] for call in self.run.call_args_list], [5, 5, 4, 1])

    def test_cancellation_and_non_macos(self):
        self.run.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.unmount()
        self.run.reset_mock()
        with patch("classe100x.usb_storage.sys.platform", "linux"):
            self.unmount()
        self.run.assert_not_called()
