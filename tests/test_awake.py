import io
import signal
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from classe100x import wireless
from classe100x.wireless import SSHError


def running_process():
    process = Mock()
    process.poll.return_value = None
    process.stdout.readline.return_value = b"READY\n"
    return process


class AwakeTests(unittest.TestCase):
    def run_awake(self, popen, body=lambda: None, *, platform="darwin"):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(wireless.subprocess, "Popen", popen), patch.object(wireless.time, "sleep"), \
                patch.object(wireless.sys, "platform", platform), redirect_stdout(out), redirect_stderr(err):
            try:
                with wireless.awake():
                    body()
            except BaseException as error:
                self.error = error
            else:
                self.error = None
        return out.getvalue(), err.getvalue()

    def run_linux(self, popen, body=lambda: None, *, readable=True):
        with patch.object(wireless.select, "select", return_value=([object()] if readable else [], [], [])), \
                patch.object(wireless.os, "killpg") as self.killpg:
            return self.run_awake(popen, body, platform="linux")

    def test_with_caffeinate_the_assertion_is_held_and_released_silently(self):
        process, ran = running_process(), []
        popen = Mock(return_value=process)
        out, err = self.run_awake(popen, lambda: ran.append(True))
        self.assertIsNone(self.error)
        self.assertEqual(ran, [True])
        self.assertEqual(popen.call_args.args[0][:3], ["/usr/bin/caffeinate", "-i", "-w"])
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)
        process.stderr.close.assert_called_once()
        self.assertEqual((out, err), ("", ""))

    def test_with_caffeinate_an_error_of_the_update_releases_the_assertion(self):
        process = running_process()

        def failing():
            raise RuntimeError("update failed")

        self.run_awake(Mock(return_value=process), failing)
        self.assertIsInstance(self.error, RuntimeError)
        process.terminate.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_with_caffeinate_a_file_error_of_the_update_is_not_a_missing_caffeinate(self):
        process = running_process()

        def failing():
            raise FileNotFoundError("firmware.fwz")

        out, err = self.run_awake(Mock(return_value=process), failing)
        self.assertIsInstance(self.error, FileNotFoundError)
        self.assertEqual((out, err), ("", ""))  # no warning: caffeinate was there
        process.terminate.assert_called_once()

    def test_a_caffeinate_that_exits_at_once_is_an_error_and_the_update_does_not_start(self):
        process, ran = Mock(), []
        process.poll.return_value = 1
        self.run_awake(Mock(return_value=process), lambda: ran.append(True))
        self.assertIsInstance(self.error, SSHError)
        self.assertIn("idle-sleep assertion", str(self.error))
        self.assertEqual(ran, [])
        process.terminate.assert_not_called()
        process.stderr.close.assert_called_once()

    def test_a_caffeinate_that_does_not_stop_is_killed(self):
        process = running_process()
        process.wait.side_effect = [subprocess.TimeoutExpired("caffeinate", 5), None]
        self.run_awake(Mock(return_value=process))
        self.assertIsNone(self.error)
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)

    def test_without_caffeinate_the_update_runs_and_a_warning_is_printed_once(self):
        popen, ran = Mock(side_effect=FileNotFoundError("/usr/bin/caffeinate")), []
        out, err = self.run_awake(popen, lambda: ran.append(True))
        self.assertIsNone(self.error)
        self.assertEqual(ran, [True])
        self.assertEqual(popen.call_count, 1)  # launching is not retried
        self.assertEqual(out, "")
        self.assertEqual(err.count("Warning:"), 1)
        self.assertIn("caffeinate", err)
        self.assertIn("awake", err)

    def test_without_caffeinate_an_error_of_the_update_propagates_without_a_chained_context(self):
        def failing():
            raise RuntimeError("update failed")

        self.run_awake(Mock(side_effect=FileNotFoundError("/usr/bin/caffeinate")), failing)
        self.assertIsInstance(self.error, RuntimeError)
        self.assertIsNone(self.error.__context__)  # the update did not fail "while handling" the launch

    def test_without_caffeinate_a_file_error_of_the_update_is_still_an_error(self):
        def failing():
            raise FileNotFoundError("firmware.fwz")

        self.run_awake(Mock(side_effect=FileNotFoundError("/usr/bin/caffeinate")), failing)
        self.assertIsInstance(self.error, FileNotFoundError)
        self.assertIn("firmware.fwz", str(self.error))

    def test_other_launch_errors_are_not_hidden(self):
        for error in (PermissionError("/usr/bin/caffeinate"), OSError("exec format error")):
            with self.subTest(error=type(error).__name__):
                ran = []
                out, err = self.run_awake(Mock(side_effect=error), lambda: ran.append(True))
                self.assertIs(self.error, error)
                self.assertEqual(ran, [])
                self.assertEqual(err, "")

    def test_linux_holds_inhibition_for_the_update_and_releases_the_process_group(self):
        process, ran = running_process(), []
        popen = Mock(return_value=process)

        def update():
            self.killpg.assert_not_called()
            ran.append(True)

        out, err = self.run_linux(popen, update)
        self.assertIsNone(self.error)
        self.assertEqual(ran, [True])
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "systemd-inhibit")
        self.assertIn("--what=idle:sleep", command)
        self.assertIn("--mode=block", command)
        self.assertIn("--no-ask-password", command)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.killpg.assert_called_once_with(process.pid, signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=5)
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()
        self.assertEqual((out, err), ("", ""))

    def test_linux_missing_or_unusable_command_warns_and_continues(self):
        for error in (FileNotFoundError("systemd-inhibit"), PermissionError("systemd-inhibit")):
            with self.subTest(error=type(error).__name__):
                ran = []
                out, err = self.run_linux(Mock(side_effect=error), lambda: ran.append(True))
                self.assertIsNone(self.error)
                self.assertEqual(ran, [True])
                self.assertEqual(out, "")
                self.assertEqual(err.count("Warning:"), 1)
                self.assertIn("systemd-inhibit", err)
                self.killpg.assert_not_called()

    def test_linux_denied_or_stalled_inhibition_warns_and_cleans_up(self):
        for readable in (True, False):
            with self.subTest(readable=readable):
                process, ran = running_process(), []
                process.stdout.readline.return_value = b""  # exited without acquiring the lock
                out, err = self.run_linux(Mock(return_value=process), lambda: ran.append(True), readable=readable)
                self.assertIsNone(self.error)
                self.assertEqual(ran, [True])
                self.assertEqual(err.count("Warning:"), 1)
                self.killpg.assert_called_once_with(process.pid, signal.SIGTERM)
                process.wait.assert_called_once_with(timeout=5)
                process.stdout.close.assert_called_once()
                process.stderr.close.assert_called_once()

    def test_linux_update_errors_and_cancellation_release_inhibition(self):
        for error in (RuntimeError("update failed"), FileNotFoundError("firmware.fwz"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                process = running_process()
                out, err = self.run_linux(Mock(return_value=process), Mock(side_effect=error))
                self.assertIs(self.error, error)
                self.assertEqual((out, err), ("", ""))
                self.killpg.assert_called_once_with(process.pid, signal.SIGTERM)
                process.wait.assert_called_once_with(timeout=5)

    def test_linux_warning_does_not_swallow_an_update_error(self):
        error = FileNotFoundError("firmware.fwz")
        self.run_linux(Mock(side_effect=FileNotFoundError("systemd-inhibit")), Mock(side_effect=error))
        self.assertIs(self.error, error)
        self.assertIsNone(error.__context__)

    def test_linux_stalled_cleanup_kills_the_whole_process_group(self):
        process = running_process()
        process.wait.side_effect = [subprocess.TimeoutExpired("systemd-inhibit", 5), None]
        self.run_linux(Mock(return_value=process))
        self.assertIsNone(self.error)
        self.assertEqual([call.args for call in self.killpg.call_args_list],
                         [(process.pid, signal.SIGTERM), (process.pid, signal.SIGKILL)])
        self.assertEqual(process.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
