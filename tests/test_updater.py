from pathlib import Path
import ftplib
import socket
import threading
import time
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from classe100x.firmware import Payload, PreparedFirmware, SELECTED_SHA256
from classe100x.protocol import ACK, FrameStream, ProtocolError
from classe100x.updater import NetworkDevice, UpdateClient, UpdateError, UncertainDelivery, check_identity, flash, uptime_seconds
from classe100x.vendor import Credentials, VendorProfile


def identity(status=4):
    return {"device_type": ("200",), "firmware": ("1", "5", "8"),
            "hardware": ("02", "06", "0"), "object_model": ("1", "0", "99"),
            "update_status": (str(status), "0")}


class SimulatedDevice:
    def __init__(self, fail=None, initial=None):
        self.client = self
        self.events = []
        self.fail = fail
        self.initial = identity() if initial is None else initial

    def event(self, name):
        self.events.append(name)
        if name == self.fail or len(self.events) - 1 == self.fail:
            raise ProtocolError("simulated disconnect")

    def connect(self):
        self.event("connect")
        return self.initial

    def close(self):
        self.events.append("close")

    def wait_idle(self):
        self.event("idle")

    def begin(self, recovery):
        self.event("begin-recovery" if recovery else "begin-main")

    def upload(self, path, credentials):
        self.event("upload-" + path.name)

    def commit(self, payload):
        self.event("commit-" + payload.name)

    def finish(self):
        self.event("finish")

    def settle(self):
        self.event("settle")

    def reboot_and_wait(self, status):
        self.event("reboot-" + str(status))
        return identity(status)

    def invalidate_main_kernel(self):
        self.event("invalidate-main-kernel")


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.firmware = PreparedFirmware(Path("unused"), SELECTED_SHA256, tuple(
            Payload(name, 100, "unused", 123) for name in (
                "btweb_only.ext4.gz", "btweb_only_recovery.ext4.gz", "uImage.zip",
            )
        ))
        self.profile = VendorProfile(Credentials("fixture-user", "fixture-value"), Credentials("fixture-user", "fixture-value"))

    def run_update(self, device):
        return flash(self.firmware, device, self.profile, report=lambda message: None)

    def test_complete_sequence_has_three_reboot_boundaries(self):
        device = SimulatedDevice()
        self.run_update(device)
        significant = [e for e in device.events if e.startswith(("begin", "commit", "reboot", "invalidate"))]
        self.assertEqual(significant, [
            "begin-recovery", "commit-btweb_only_recovery.ext4.gz", "commit-uImage.zip", "reboot-4",
            "invalidate-main-kernel", "reboot-1", "begin-main",
            "commit-btweb_only.ext4.gz", "commit-uImage.zip", "reboot-4",
        ])

    def test_disconnection_at_each_step_stops_all_subsequent_actions(self):
        complete = SimulatedDevice()
        self.run_update(complete)
        for index, event in enumerate(complete.events[:-1]):
            with self.subTest(index=index, event=event):
                device = SimulatedDevice(fail=index)
                with self.assertRaises(UpdateError):
                    self.run_update(device)
                self.assertEqual(device.events, complete.events[:index + 1] + ["close"])

    def test_wrong_device_cannot_start_a_transfer(self):
        for key, value in (("object_model", ("1", "0", "98")), ("hardware", ("2", "7", "0")),
                           ("firmware", ("1", "7", "0")), ("update_status", ("3", "0"))):
            with self.subTest(key=key):
                info = identity()
                info[key] = value
                device = SimulatedDevice(initial=info)
                with self.assertRaises(UpdateError):
                    self.run_update(device)
                self.assertEqual(device.events, ["connect", "close"])

    def test_corrupted_extra_status_cannot_be_treated_as_normal(self):
        info = identity()
        info["update_status"] = ("4", "47")
        with self.assertRaises(UpdateError):
            check_identity(info, 4)

    def test_credentials_have_no_printable_representation(self):
        self.assertNotIn("fixture-value", repr(self.profile))
        self.assertNotIn("fixture-user", repr(self.profile))

    def test_lost_commit_ack_is_never_retried(self):
        client_socket, peer = socket.socketpair()
        self.addCleanup(client_socket.close)
        self.addCleanup(peer.close)
        client = UpdateClient("unused", timeout=0.05)
        client.stream = FrameStream(client_socket)
        observed = []

        def server():
            stream = FrameStream(peer)
            observed.append(stream.receive(time.monotonic() + 1))
            # Simulate a delivered write command whose ACK never arrives.
            peer.settimeout(1)
            observed.append(peer.recv(4096))

        thread = threading.Thread(target=server)
        thread.start()
        with self.assertRaises(UncertainDelivery):
            client.commit(self.firmware.payload("uImage.zip"))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(observed, [b"*#13**#35*100*0*123##", b""])
        self.assertIsNone(client.stream)


class NetworkWaitTests(unittest.TestCase):
    def setUp(self):
        self.clock = 0
        self.device = NetworkDevice("unused", reboot_timeout=4, write_timeout=5)
        self.client = MagicMock()
        self.client.query.return_value = ("0", "0", "10", "0")
        self.device.client = self.client
        self.addCleanup(patch.stopall)
        patch("classe100x.updater.time.monotonic", side_effect=lambda: self.clock).start()
        patch("classe100x.updater.time.sleep", side_effect=self.sleep).start()

    def sleep(self, seconds):
        self.clock += seconds

    def test_busy_worker_timeout_does_not_reboot(self):
        self.client.idle.return_value = False
        with self.assertRaisesRegex(UpdateError, "still busy"):
            self.device.wait_idle()
        self.client.reboot.assert_not_called()
        self.client.finish.assert_not_called()

    def test_stale_normal_reply_is_not_a_completed_reboot(self):
        probe = patch("classe100x.updater.ReadOnlyClient").start().return_value.__enter__.return_value
        info = identity()
        info["uptime"] = ("0", "0", "10", "4")
        probe.inspect.return_value = info
        with self.assertRaisesRegex(UpdateError, "not verified"):
            self.device.reboot_and_wait(4)
        self.client.reboot.assert_called_once()

    def test_reconnect_requires_reset_uptime_and_expected_mode(self):
        probe = patch("classe100x.updater.ReadOnlyClient").start().return_value.__enter__.return_value
        info = identity(1)
        info["uptime"] = ("0", "0", "0", "1")
        probe.inspect.side_effect = [OSError("USB disconnected"), info]
        connect = patch.object(self.device, "connect", return_value=info).start()
        self.assertEqual(self.device.reboot_and_wait(1), info)
        connect.assert_called_once()
        self.client.reboot.assert_called_once()

    def test_wrong_mode_after_actual_reboot_stops(self):
        probe = patch("classe100x.updater.ReadOnlyClient").start().return_value.__enter__.return_value
        info = identity(4)
        info["uptime"] = ("0", "0", "0", "1")
        probe.inspect.return_value = info
        with self.assertRaisesRegex(UpdateError, "update_status"):
            self.device.reboot_and_wait(1)

    def test_uptime_ranges(self):
        self.assertEqual(uptime_seconds(("1", "2", "3", "4")), 93784)
        for values in (("0", "24", "0", "0"), ("0", "0", "0", "60"), ("1",), ("-1", "0", "0", "0")):
            with self.assertRaises(UpdateError):
                uptime_seconds(values)


class FTPTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "uImage.zip"
        self.path.write_bytes(b"fixture payload")
        self.device = NetworkDevice("unused")
        self.credentials = Credentials("fixture-user", "fixture-secret")
        factory = patch("classe100x.updater.ftplib.FTP")
        self.ftp = factory.start().return_value.__enter__.return_value
        self.addCleanup(factory.stop)
        self.ftp.nlst.side_effect = [[], [self.path.name]]
        self.ftp.size.return_value = self.path.stat().st_size

    def test_upload_checks_staging_and_remote_length(self):
        sent = []
        self.ftp.storbinary.side_effect = lambda command, source, **kw: sent.append((command, source.read()))
        self.device.upload(self.path, self.credentials)
        self.assertEqual(sent, [("STOR uImage.zip", b"fixture payload")])
        self.ftp.voidcmd.assert_called_once_with("TYPE I")
        self.ftp.size.assert_called_once_with("uImage.zip")

    def test_existing_file_prevents_upload(self):
        self.ftp.nlst.side_effect = [["previous-file"]]
        with self.assertRaisesRegex(UpdateError, "not empty"):
            self.device.upload(self.path, self.credentials)
        self.ftp.storbinary.assert_not_called()

    def test_incomplete_or_contaminated_upload_is_rejected(self):
        for size, listing in ((0, [self.path.name]), (len(b"fixture payload"), [self.path.name, "other"])):
            with self.subTest(size=size, listing=listing):
                self.ftp.size.return_value = size
                self.ftp.nlst.side_effect = [[], listing]
                with self.assertRaises(UpdateError):
                    self.device.upload(self.path, self.credentials)

    def test_ftp_failures_do_not_expose_server_text(self):
        for operation in ("connect", "login", "nlst", "storbinary", "voidcmd", "size"):
            with self.subTest(operation=operation):
                self.ftp.nlst.side_effect = [[], [self.path.name]]
                method = getattr(self.ftp, operation)
                method.side_effect = ftplib.error_perm("fixture-user fixture-secret")
                with self.assertRaisesRegex(UpdateError, "write was not requested") as caught:
                    self.device.upload(self.path, self.credentials)
                self.assertNotIn("fixture-", str(caught.exception))
                method.side_effect = None
