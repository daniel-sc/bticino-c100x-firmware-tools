import io
from pathlib import Path
import signal
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from classe100x.transport import run_usb


def child(lines, running=False):
    process = MagicMock()
    process.stdout = io.StringIO(lines)
    process.poll.return_value = None if running else 0
    return process


def ready(system, driver):
    return f"virtual interface pair ready: system side {system} <-> driver side {driver} (MTU 1500)\n"


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("classe100x.transport.os.geteuid", return_value=0).start()
        patch("classe100x.transport.Path.resolve", return_value=Path("/fixture/tetherkit")).start()
        patch("classe100x.transport.print").start()
        self.spawn = patch("classe100x.transport.subprocess.Popen").start()
        self.configure = patch("classe100x.transport.subprocess.run").start()
        self.sleep = patch("classe100x.transport.time.sleep").start()

    def test_reenumeration_and_restart_configure_each_system_side(self):
        first = child(ready("feth2", "feth3") + ready("feth4", "feth5"))
        second = child(ready("feth6", "feth7"))
        self.spawn.side_effect = [first, second]
        self.sleep.side_effect = [None, KeyboardInterrupt]
        with self.assertRaises(KeyboardInterrupt):
            run_usb(Path("unused"))
        self.assertEqual([c.args[0][1] for c in self.configure.call_args_list], ["feth2", "feth4", "feth6"])
        self.assertTrue(first.stdout.closed and second.stdout.closed)
        for call in self.spawn.call_args_list:
            self.assertTrue(call.kwargs["start_new_session"])
            self.assertIn("1da4", call.args[0])
            self.assertIn("0056", call.args[0])

    def test_configuration_failure_stops_child_without_restart(self):
        process = child(ready("feth8", "feth9"), running=True)
        self.spawn.return_value = process
        self.configure.side_effect = subprocess.CalledProcessError(1, "ifconfig")
        with self.assertRaises(subprocess.CalledProcessError):
            run_usb(Path("unused"))
        process.send_signal.assert_called_once_with(signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=10)
        self.spawn.assert_called_once()
        self.assertTrue(process.stdout.closed)

    def test_termination_signals_cleanup_and_restore_handlers(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig):
                previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
                process = child(ready("feth8", "feth9"), running=True)
                self.spawn.return_value = process
                self.configure.side_effect = lambda *a, **k: signal.getsignal(sig)(sig, None)
                with self.assertRaises(KeyboardInterrupt):
                    run_usb(Path("unused"))
                process.send_signal.assert_called_once_with(signal.SIGTERM)
                process.wait.assert_called_once_with(timeout=10)
                self.assertTrue(process.stdout.closed)
                self.assertEqual({s: signal.getsignal(s) for s in previous}, previous)

    def test_unresponsive_helper_is_reaped_after_grace_period(self):
        process = child(ready("feth8", "feth9"), running=True)
        process.wait.side_effect = [subprocess.TimeoutExpired("helper", 10), 0]
        self.spawn.return_value = process
        self.configure.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            run_usb(Path("unused"))
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_args_list[-1].kwargs, {"timeout": 5})
        self.assertTrue(process.stdout.closed)
