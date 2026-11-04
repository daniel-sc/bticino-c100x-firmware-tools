from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from classe100x.usb_session import Session, USBError, usb_session, native_usb_interface, check_native_usb
from classe100x.updater import NetworkDevice
from test_updater import identity


class USBSessionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("classe100x.usb_session.native_usb_interface", return_value=None))
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

    def test_worker_diagnostic_survives_until_failure(self):
        from classe100x.diagnostics import format_failure
        session = Session(self.worker('print(\'{"diagnostic":"libusb open failed: access denied"}\')'))
        with self.assertRaises(USBError) as error:
            session.check(timeout=5)
        self.assertIn("libusb open failed: access denied", format_failure(error.exception))

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

    def test_flash_reboot_verification_survives_rndis_ecm_rndis_handover(self):
        """Replay the observed recovery ECM route through the real reboot gate."""
        processes = []
        spawn = subprocess.Popen

        def start(*args, **kwargs):
            process = spawn(*args, **kwargs)
            processes.append(process)
            return process

        with tempfile.NamedTemporaryFile() as helper:
            command = [sys.executable, "-u", "-c",
                       'import time; print(\'{"interface":"feth42"}\'); time.sleep(30)']
            with patch("classe100x.usb_session.os.geteuid", return_value=0), \
                    patch("classe100x.usb_session.child_command", return_value=command), \
                    patch("classe100x.usb_session.subprocess.Popen", side_effect=start), \
                    patch("classe100x.usb_session.native_usb_interface", return_value=None) as native, \
                    patch("classe100x.updater.ReadOnlyClient") as probe:
                with usb_session(Path(helper.name)) as check:
                    device = NetworkDevice("unused", check_transport=check, reboot_timeout=0.5)
                    device.client = MagicMock()
                    device.client.query.return_value = ("0", "0", "10", "0")
                    reboot = device.client.reboot

                    def enter_recovery():
                        native.return_value = "en7"
                        self.route.return_value.stdout = "interface: en7\ninet 192.168.129.2 netmask 0xfffffffc\n"

                    reboot.side_effect = enter_recovery
                    info = identity(1)
                    info["uptime"] = ("0", "0", "0", "0")
                    probe.return_value.__enter__.return_value.inspect.return_value = info
                    with patch.object(device, "connect", return_value=info), \
                            patch("classe100x.updater.time.sleep"):
                        self.assertEqual(device.reboot_and_wait(1), info)
                    reboot.assert_called_once()
                    self.assertIsNotNone(processes[0].poll())
                    # Normal firmware needs a fresh helper; the old one must not
                    # keep owning a stale route while recovery uses native ECM.
                    native.return_value = None
                    self.route.return_value.stdout = "interface: feth42\n"
                    check()
                    self.assertEqual(len(processes), 2)
                self.assertTrue(all(process.poll() is not None for process in processes))

    def test_ecm_appearing_while_helper_has_no_feth_is_detected(self):
        with tempfile.NamedTemporaryFile() as helper:
            command = [sys.executable, "-u", "-c",
                       'import time; print(\'{"interface":null}\'); time.sleep(30)']
            self.route.return_value.stdout = "interface: en7\ninet 192.168.129.2 netmask 0xfffffffc\n"
            with patch("classe100x.usb_session.os.geteuid", return_value=0), \
                    patch("classe100x.usb_session.child_command", return_value=command), \
                    patch("classe100x.usb_session.native_usb_interface", side_effect=[None, "en7", "en7"]):
                with usb_session(Path(helper.name)):
                    pass

    def test_interrupt_during_handover_finishes_worker_cleanup(self):
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signum=signum), tempfile.NamedTemporaryFile() as binary:
                process = MagicMock()
                process.poll.return_value = None
                session = MagicMock(interface="feth42")
                previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}

                def interrupt_wait(*args, **kwargs):
                    signal.getsignal(signum)(signum, None)
                    raise subprocess.TimeoutExpired("worker", 20)

                # Deliver the signal from inside the actual teardown wait.
                waits = iter((interrupt_wait, lambda **kwargs: 0))
                process.wait.side_effect = lambda **kwargs: next(waits)(**kwargs)
                with patch("classe100x.usb_session.os.geteuid", return_value=0), \
                        patch("classe100x.usb_session.subprocess.Popen", return_value=process), \
                        patch("classe100x.usb_session.Session", return_value=session), \
                        patch("classe100x.usb_session.os.killpg") as kill, \
                        patch("classe100x.usb_session.native_usb_interface", side_effect=[None, "en7"]), \
                        patch("classe100x.usb_session.check_native_usb") as native:
                    with self.assertRaises(KeyboardInterrupt):
                        with usb_session(Path(binary.name)) as check:
                            check()
                    self.assertEqual(process.wait.call_count, 2)
                    kill.assert_called_once_with(process.pid, signal.SIGKILL)
                    session.reader.join.assert_called_once()
                    process.stdout.close.assert_called_once()
                    native.assert_not_called()
                self.assertEqual({sig: signal.getsignal(sig) for sig in previous}, previous)


class NativeRecoveryUSBTests(unittest.TestCase):
    def test_interface_must_descend_from_matching_usb_device(self):
        ethernet = {"IOObjectClass": "IOSkywalkLegacyEthernetInterface", "IORegistryEntryName": "en7"}
        usb = {"idVendor": 0x1da4, "idProduct": 0x0056,
               "IORegistryEntryChildren": [{"IORegistryEntryChildren": [ethernet]}]}
        other = {"idVendor": 123, "IORegistryEntryChildren": [ethernet]}
        with patch("classe100x.usb_session.subprocess.run") as run:
            run.return_value.returncode = 0
            for nodes, expected in (([other], None), ([other, usb], "en7"), ([], None)):
                run.return_value.stdout = plistlib.dumps(nodes)
                self.assertEqual(native_usb_interface(), expected)
            # ioreg emits no plist at all when no USB device is connected.
            run.return_value.stdout = b""
            self.assertIsNone(native_usb_interface())
            run.return_value.stdout = plistlib.dumps([usb, usb])
            with self.assertRaisesRegex(USBError, "only one"):
                native_usb_interface()
            run.return_value.stdout = b"invalid plist"
            with self.assertRaises(USBError):
                native_usb_interface()

    def test_native_route_cannot_fall_back_to_lan(self):
        configured = subprocess.CompletedProcess([], 0, "inet 192.168.129.2 netmask 0xfffffffc")
        for interface in ("en7", "en0"):
            route = subprocess.CompletedProcess([], 0, f"  interface: {interface}\n")
            with patch("classe100x.usb_session.subprocess.run", side_effect=[configured, route]):
                if interface == "en7":
                    check_native_usb("en7")
                else:
                    with self.assertRaisesRegex(USBError, "native C100X"):
                        check_native_usb("en7")

    def test_unconfigured_native_interface_is_configured_before_route_check(self):
        responses = [subprocess.CompletedProcess([], 0, ""), subprocess.CompletedProcess([], 0),
                     subprocess.CompletedProcess([], 0, "interface: en7\n")]
        with patch("classe100x.usb_session.subprocess.run", side_effect=responses) as run:
            check_native_usb("en7")
        self.assertEqual(run.call_args_list[1].args[0],
                         ["/sbin/ifconfig", "en7", "inet", "192.168.129.2", "netmask", "255.255.255.252", "up"])

    def test_native_recovery_then_helper_normal_boot_and_cleanup(self):
        with tempfile.NamedTemporaryFile() as binary, \
                patch("classe100x.usb_session.os.geteuid", return_value=0), \
                patch("classe100x.usb_session.native_usb_interface", side_effect=["en7", "en7", None, None]), \
                patch("classe100x.usb_session.check_native_usb") as native, \
                patch("classe100x.usb_session._helper_session") as helper:
            helper.return_value.__enter__.return_value.interface = "feth42"
            previous = signal.getsignal(signal.SIGTERM)
            with usb_session(Path(binary.name)) as check:
                helper.assert_not_called()
                check()
                self.assertEqual(native.call_count, 2)
                check()
                helper.assert_called_once_with(Path(binary.name).resolve())
                check()
                self.assertEqual(helper.return_value.__enter__.return_value.check.call_count, 2)
            helper.return_value.__exit__.assert_called_once()
            self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_failed_helper_start_is_not_repeated(self):
        with tempfile.NamedTemporaryFile() as binary, \
                patch("classe100x.usb_session.os.geteuid", return_value=0), \
                patch("classe100x.usb_session.native_usb_interface", side_effect=["en7", None]), \
                patch("classe100x.usb_session.check_native_usb"), \
                patch("classe100x.usb_session._helper_session") as helper:
            helper.return_value.__enter__.side_effect = USBError("not ready")
            with usb_session(Path(binary.name)) as check:
                with self.assertRaises(USBError):
                    check()
                with self.assertRaisesRegex(USBError, "startup failed"):
                    check()
            helper.assert_called_once()

    def test_non_root_and_native_route_failure_never_launch_helper(self):
        with patch("classe100x.usb_session.os.geteuid", return_value=501), \
                patch("classe100x.usb_session._helper_session") as helper:
            with self.assertRaises(PermissionError):
                with usb_session(Path("unused")):
                    self.fail("unexpected session")
            helper.assert_not_called()
        with tempfile.NamedTemporaryFile() as binary, \
                patch("classe100x.usb_session.os.geteuid", return_value=0), \
                patch("classe100x.usb_session.native_usb_interface", return_value="en7"), \
                patch("classe100x.usb_session.check_native_usb", side_effect=USBError("wrong route")), \
                patch("classe100x.usb_session._helper_session") as helper:
            with self.assertRaises(USBError):
                with usb_session(Path(binary.name)):
                    self.fail("unexpected session")
            helper.assert_not_called()
