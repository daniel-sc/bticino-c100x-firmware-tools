from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from classe100x.usb_session import Session, USBError, usb_session


class USBSessionTests(unittest.TestCase):
    def setUp(self):
        self.route = self.enterContext(patch("classe100x.usb_session.subprocess.run"))
        self.route.return_value.returncode = 0
        self.route.return_value.stdout = "   interface: feth42\n"

    def worker(self, code):
        process = subprocess.Popen([sys.executable, "-u", "-c", code], stdout=subprocess.PIPE, text=True)
        def cleanup():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
        self.addCleanup(cleanup)
        return process

    def test_route_cannot_fall_back_to_lan(self):
        process = self.worker('import time; print(\'{"interface":"feth42"}\'); time.sleep(30)')
        session = Session(process)
        session.check(timeout=5)
        self.route.return_value.stdout = "   interface: en0\n"
        with self.assertRaisesRegex(USBError, "managed USB"):
            session.check()

    def test_dead_or_malformed_supervisor_is_not_ready(self):
        for output in ('{"interface":"en0"}', 'not-json', '{"interface":null}'):
            with self.subTest(output=output):
                session = Session(self.worker(f"print({output!r})"))
                with self.assertRaisesRegex(USBError, "stopped"):
                    session.check(timeout=5)

    def test_no_device_has_bounded_wait(self):
        session = Session(self.worker('import time; print(\'{"interface":null}\'); time.sleep(30)'))
        with self.assertRaisesRegex(USBError, "not ready"):
            session.check(timeout=0.05)

    def test_route_timeout_stops_with_transport_error(self):
        session = Session(self.worker('import time; print(\'{"interface":"feth42"}\'); time.sleep(30)'))
        self.route.side_effect = subprocess.TimeoutExpired("route", 5)
        with self.assertRaisesRegex(USBError, "verification timed out"):
            session.check(timeout=5)

    def test_context_stops_worker_on_error_and_restores_signals(self):
        with tempfile.NamedTemporaryFile() as helper:
            command = [sys.executable, "-u", "-c",
                       'import time; print(\'{"interface":"feth42"}\'); time.sleep(30)']
            previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
            with patch("classe100x.usb_session.os.geteuid", return_value=0), \
                    patch("classe100x.usb_session.child_command", return_value=command), \
                    self.assertRaisesRegex(RuntimeError, "fixture"):
                with usb_session(Path(helper.name)) as check:
                    check()
                    raise RuntimeError("fixture")
            self.assertEqual({s: signal.getsignal(s) for s in previous}, previous)

    def test_non_root_never_launches_usb(self):
        with patch("classe100x.usb_session.os.geteuid", return_value=501), \
                patch("classe100x.usb_session.subprocess.Popen") as spawn:
            with self.assertRaises(PermissionError):
                with usb_session(Path("unused")):
                    self.fail("unexpected session")
            spawn.assert_not_called()
