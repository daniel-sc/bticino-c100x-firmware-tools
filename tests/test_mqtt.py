"""Host input checks and deterministic fault injection for the target runtime."""
from collections import deque
import contextlib
import io
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from classe100x.firmware import FirmwareError
from test_mqtt_runtime import bridge, PRESS, RELEASE

ROOT = Path(__file__).resolve().parent.parent
configuration = runpy.run_path(str(ROOT / "payloads/mqtt/common.py"))["configuration"]


class InputsTests(unittest.TestCase):
    def test_cli_requires_private_inputs_before_download_or_build(self):
        from classe100x.__main__ import main
        old_umask = os.umask(0o077)
        self.addCleanup(os.umask, old_umask)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.json"
            path.write_text('{"mqtt":{"password":"private-secret"}}')
            path.chmod(0o644)
            with patch.object(sys, "argv", ["c100x", "build-fw", "--stock", "c100x-1.5.8",
                                           "--inputs", str(path), "--output", str(path.parent / "output.fwz")]), \
                    patch("classe100x.download.fetch_stock") as fetch, patch("classe100x.builder.build") as build, \
                    patch("os.geteuid", return_value=501), contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(main(), 1)
                fetch.assert_not_called()
                build.assert_not_called()
            self.assertIn("private permissions", errors.getvalue())
            self.assertNotIn("private-secret", errors.getvalue())

    def test_credentials_roundtrip_without_interpolation_or_evaluation(self):
        values = dict(transport="plain", host="192.0.2.1", username=" user%#; ", password="$(no); ü#% ")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.ini"
            path.write_bytes(configuration(values))
            decoded = bridge.configuration(str(path))
        self.assertEqual(decoded["username"], values["username"].encode())
        self.assertEqual(decoded["password"], values["password"].encode())
        self.assertEqual(decoded["prefix"], b"Bticino")

    def test_invalid_inputs_are_rejected_without_disclosure(self):
        valid = dict(transport="plain", host="192.0.2.1", username="fixture", password="private-secret")
        for name, value in (("host", "secret-host"), ("host", 1), ("host", "::1"),
                            ("port", True), ("port", 0), ("port", 65536),
                            ("prefix", "a/#"), ("prefix", "/a"), ("prefix", "a" * 129),
                            ("password", "secret\nvalue"), ("username", ""),
                            ("password", "x" * 513), ("transport", "tls"), ("unexpected", "secret")):
            with self.subTest(name=name, value=value), self.assertRaises(FirmwareError) as error:
                configuration(dict(valid, **{name: value}))
            self.assertNotIn("secret", str(error.exception))


class LifecycleTests(unittest.TestCase):
    def tearDown(self):
        bridge.STOP = False

    def generation(self, commands):
        mqtt = Mock(subscribed=True, commands=deque(commands))
        mqtt.step.side_effect = [None, bridge.BridgeError("connection lost")]
        return mqtt

    def test_expired_commands_discarded_and_remaining_queue_cleared_on_failure(self):
        mqtt = self.generation([(0, PRESS), (10, RELEASE)])
        with patch.object(bridge, "clock", return_value=10), patch.object(bridge, "open_monitor"), \
                patch.object(bridge.select, "select", return_value=([], [], [])), patch.object(bridge, "Command") as command:
            with self.assertRaisesRegex(bridge.BridgeError, "connection lost"):
                bridge.generation(mqtt, Mock(), b"started")
        command.assert_not_called()
        self.assertFalse(mqtt.commands)
        self.assertFalse(mqtt.accepting)

    def test_uncertain_command_is_not_retried_and_discards_pending_commands(self):
        mqtt = self.generation([(10, PRESS), (10, RELEASE)])
        command = Mock()
        command.step.side_effect = bridge.BridgeError("uncertain")
        with patch.object(bridge, "clock", return_value=10), patch.object(bridge, "open_monitor"), \
                patch.object(bridge.select, "select", return_value=([], [], [])), \
                patch.object(bridge, "Command", return_value=command) as factory:
            with self.assertRaisesRegex(bridge.BridgeError, "uncertain"):
                bridge.generation(mqtt, Mock(), b"started")
        factory.assert_called_once_with(PRESS)
        command.close.assert_called_once()
        self.assertFalse(mqtt.commands)

    def test_monitor_loss_prevents_queued_command(self):
        mqtt = self.generation([(10, PRESS)])
        monitor = Mock()
        monitor.recv.return_value = b""
        with patch.object(bridge, "open_monitor", return_value=monitor), \
                patch.object(bridge.select, "select", return_value=([monitor], [], [])), \
                patch.object(bridge, "Command") as command:
            with self.assertRaisesRegex(bridge.BridgeError, "monitor disconnected"):
                bridge.generation(mqtt, Mock(), b"started")
        command.assert_not_called()
        monitor.close.assert_called_once()

    def test_command_partial_write_timeout_never_resends_prefix(self):
        stream = Mock()
        stream.connect_ex.return_value = 0
        stream.getsockopt.return_value = 0
        stream.send.side_effect = [3, len(PRESS) - 3]
        with patch.object(bridge.socket, "socket", return_value=stream), \
                patch.object(bridge, "clock", return_value=0) as clock, \
                patch.object(bridge.select, "select", return_value=([], [stream], [])):
            command = bridge.Command(PRESS)
            self.assertFalse(command.step())
            self.assertFalse(command.step())
            self.assertEqual([c.args[0] for c in stream.send.call_args_list], [PRESS, PRESS[3:]])
            clock.return_value = 3
            with self.assertRaisesRegex(bridge.BridgeError, "uncertain"):
                command.step()
            command.close()
        self.assertEqual(stream.send.call_count, 2)

    def test_retry_delays_and_generation_destruction(self):
        library = Mock()
        library.mosquitto_lib_init.return_value = 0
        delays = []

        def pause(delay):
            delays.append(delay)
            if len(delays) == 7:
                bridge.STOP = True

        with patch.object(bridge.C, "CDLL", return_value=library), \
                patch.object(bridge, "MQTT") as mqtt, patch.object(bridge, "pause", side_effect=pause), \
                patch.object(bridge, "generation", side_effect=bridge.BridgeError("lost")):
            bridge.worker({}, Mock())
        self.assertEqual(delays, [1, 2, 4, 8, 16, 30, 30])
        self.assertEqual(mqtt.return_value.close.call_count, 7)

    def test_publication_backlog_is_bounded_before_calling_native_library(self):
        mqtt = bridge.MQTT.__new__(bridge.MQTT)
        mqtt.pending = {i: 0 for i in range(64)}
        with self.assertRaisesRegex(bridge.BridgeError, "backlog"):
            mqtt.publish("tx", PRESS)

    def test_process_supervision_restarts_worker_and_releases_single_instance_lock(self):
        # Actual fork, signal and flock; worker is a local fixture with no network.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").write_bytes(configuration(dict(transport="plain", host="192.0.2.1",
                                                             username="fixture", password="fixture")))
            runner = root / "runner.py"
            runner.write_text("import sys, os, time\n"
                              f"sys.path.insert(0, {str(ROOT / 'payloads/mqtt/files')!r})\n"
                              "import bridge\n"
                              f"bridge.STATE={str(root / 'state')!r}\nbridge.CONFIG={str(root / 'config')!r}\n"
                              "def worker(config, log):\n"
                              f"    with open({str(root / 'workers')!r}, 'a') as f: f.write(str(os.getpid())+'\\n')\n"
                              "    while bridge.running(): time.sleep(.02)\n"
                              "bridge.worker=worker\nbridge.main('start')\n")
            process = subprocess.Popen([sys.executable, str(runner)], stderr=subprocess.PIPE)
            try:
                def workers(count):
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        if (root / "workers").exists():
                            pids = (root / "workers").read_text().splitlines()
                            if len(pids) >= count:
                                return [int(pid) for pid in pids]
                        time.sleep(.02)
                    self.fail("worker fixture timeout")

                pid = workers(1)[0]
                duplicate = subprocess.run([sys.executable, str(runner)], timeout=2, capture_output=True)
                self.assertEqual(duplicate.returncode, 0)
                os.kill(pid, signal.SIGKILL)
                workers(2)
                process.terminate()
                _, stderr = process.communicate(timeout=8)
                self.assertEqual(process.returncode, 0, stderr)
                import fcntl
                with (root / "state/lock").open() as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                for path in (root / "state").iterdir():
                    self.assertEqual(path.stat().st_mode & 0o077, 0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=8)
