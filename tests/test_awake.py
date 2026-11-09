import io
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from classe100x import wireless
from classe100x.wireless import SSHError


def running_process():
    process = Mock()
    process.poll.return_value = None
    return process


class AwakeTests(unittest.TestCase):
    def run_awake(self, popen, body=lambda: None):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(wireless.subprocess, "Popen", popen), patch.object(wireless.time, "sleep"), \
                redirect_stdout(out), redirect_stderr(err):
            try:
                with wireless.awake():
                    body()
            except BaseException as error:
                self.error = error
            else:
                self.error = None
        return out.getvalue(), err.getvalue()

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


if __name__ == "__main__":
    unittest.main()
