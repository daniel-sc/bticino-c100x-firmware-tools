import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from classe100x import source_profiles as sp
from classe100x import updater, wireless
from classe100x.diagnostics import failure
from classe100x.recovery import RecoveryVerifier
from classe100x.updater import (NetworkDevice, ProtocolError, UpdateError, check_identity, check_resume,
                                resume_recovery)
from classe100x.wireless import SSHError, Wireless

ROOT = Path(__file__).resolve().parent.parent
V157, V158, V156 = (1, 5, 7), (1, 5, 8), (1, 5, 6)
SOURCE = frozenset({V157})
WRITES = ("begin", "commit", "upload", "invalidate", "reboot", "finish")


def identity(version=V158, status=4, hardware=("02", "06", "0")):
    return {"device_type": ("200",), "firmware": tuple(str(p) for p in version), "hardware": hardware,
            "object_model": ("1", "0", "99"), "update_status": (str(status), "0"),
            "uptime": ("0", "0", "0", "1")}


class Client:
    def __init__(self, device):
        self.device = device

    def idle(self):
        self.device.events.append("idle")
        return not self.device.busy

    def begin(self, recovery):
        self.device.events.append("begin-recovery" if recovery else "begin-main")

    def commit(self, payload):
        self.device.events.append("commit-" + payload.name)
        if payload.name == "btweb_only.ext4.gz":
            self.device.main_written = True

    def finish(self):
        self.device.events.append("finish")

    def invalidate_main_kernel(self):
        self.device.events.append("invalidate")
        if self.device.invalidate_error:
            raise self.device.invalidate_error
        self.device.cleared = True


class Device:
    """Stands in for NetworkDevice. Reboots check the identity with the real check_identity()."""

    def __init__(self, version=V157, recovery_version=V158, busy=False, invalidate_error=None):
        self.events, self.reboots = [], []
        self.version, self.status, self.recovery_version = version, 4, recovery_version
        self.busy, self.invalidate_error = busy, invalidate_error
        self.cleared = self.main_written = False
        self.client = Client(self)

    def connect(self):
        self.events.append("connect")
        return identity(self.version, self.status)

    def wait_idle(self):
        pass

    def upload(self, path, credentials):
        self.events.append("upload-" + Path(path).name)

    def reconnect(self):
        pass

    def settle(self):
        pass

    def close(self):
        self.events.append("close")

    def reboot_and_wait(self, status, **options):
        self.events.append(f"reboot-{status}")
        self.reboots.append((status, options))
        if self.cleared and status == 1:
            self.version, self.status = self.recovery_version, 1
        elif self.main_written:
            self.version, self.status = V158, 4
        info = identity(self.version, self.status)
        check_identity(info, status, **options)
        return info


class Verification:
    def __init__(self, device, verify_error=None, change_version=None):
        self.device, self.verify_error, self.change_version = device, verify_error, change_version
        self.results = []

    def preflight(self):
        self.device.events.append("verify-preflight")

    def verify(self):
        self.device.events.append("verify")
        if self.verify_error:
            raise self.verify_error
        if self.change_version:
            self.device.version = self.change_version

    def update_result(self, status, stage):
        self.results.append((status, stage))


FIRMWARE = SimpleNamespace(directory=Path("fw"),
                           payload=lambda name: SimpleNamespace(name=name, size=1, cksum=1))
PROFILE = SimpleNamespace(normal=object(), recovery=object())


def resume(device, verification, **options):
    messages = []
    options.setdefault("source_versions", SOURCE)
    result = resume_recovery(FIRMWARE, device, PROFILE, report=messages.append, verification=verification,
                             **options)
    return result, messages


def writes(device):
    return [e for e in device.events if e.startswith(WRITES)]


class CheckResumeTests(unittest.TestCase):
    def test_the_plan_only_reads(self):
        device = Device()
        verification = Verification(device)
        info = check_resume(device, verification, lambda message: None, source_versions=SOURCE)
        self.assertEqual(info["firmware"], ("1", "5", "7"))
        self.assertEqual(writes(device), [])
        self.assertEqual(device.events, ["connect", "idle", "verify-preflight", "verify", "connect", "close"])
        self.assertEqual(verification.results, [])  # nothing is recorded as an update in progress

    def test_a_source_that_is_not_supported_stops_before_the_readback(self):
        for version in (V156, V158):
            with self.subTest(version=version):
                device = Device(version)
                with self.assertRaises(UpdateError):
                    check_resume(device, Verification(device), lambda message: None, source_versions=SOURCE)
                self.assertNotIn("verify", device.events)

    def test_a_busy_update_worker_stops_before_the_readback(self):
        device = Device(busy=True)
        with self.assertRaisesRegex(UpdateError, "busy"):
            check_resume(device, Verification(device), lambda message: None, source_versions=SOURCE)
        self.assertNotIn("verify", device.events)

    def test_a_recovery_that_does_not_verify_fails_the_plan(self):
        device = Device()
        with self.assertRaises(RuntimeError):
            check_resume(device, Verification(device, verify_error=RuntimeError("recovery differs")),
                         lambda message: None, source_versions=SOURCE)
        self.assertEqual(writes(device), [])

    def test_the_source_versions_are_required(self):
        for versions in (None, frozenset()):
            with self.subTest(versions=versions):
                device = Device()
                with self.assertRaises(ValueError):
                    check_resume(device, Verification(device), lambda message: None, source_versions=versions)
                self.assertEqual(device.events, [])


class ResumeRecoveryTests(unittest.TestCase):
    def test_the_sequence_never_writes_recovery_again(self):
        device = Device()
        verification = Verification(device)
        resume(device, verification)
        events = device.events
        self.assertEqual(events.count("invalidate"), 1)
        self.assertEqual(events.count("verify-preflight"), 1)  # not repeated inside the recovery
        self.assertEqual(events.count("verify"), 1)
        self.assertNotIn("begin-recovery", events)
        self.assertEqual([e for e in events if e.startswith(("commit", "upload"))],
                         ["upload-btweb_only.ext4.gz", "commit-btweb_only.ext4.gz",
                          "upload-uImage.zip", "commit-uImage.zip"])
        self.assertLess(events.index("verify"), events.index("invalidate"))
        self.assertLess(events.index("invalidate"), events.index("reboot-1"))
        self.assertLess(events.index("reboot-1"), events.index("begin-main"))

    def test_only_the_target_firmware_is_accepted_after_the_main_kernel_is_cleared(self):
        device = Device()
        resume(device, Verification(device))
        self.assertEqual(device.reboots, [(1, {}), (4, {})])

    def test_the_outcome_is_recorded(self):
        device = Device()
        verification = Verification(device)
        calls = []
        resume(device, verification, final_verification=lambda: calls.append("final"))
        self.assertEqual(calls, ["final"])
        self.assertEqual([status for status, stage in verification.results], ["in_progress", "completed"])
        self.assertEqual(verification.results[-1][1], "update sequence completed")

    def test_a_recovery_that_does_not_verify_leaves_the_source_main_untouched(self):
        device = Device()
        verification = Verification(device, verify_error=RuntimeError("recovery differs"))
        with self.assertRaises(RuntimeError) as caught:
            resume(device, verification)
        self.assertEqual(writes(device), [])
        self.assertEqual(verification.results[-1][0], "stopped")
        self.assertIn("main kernel clear attempted: False", failure(caught.exception)["notes"])

    def test_the_message_says_the_main_kernel_was_not_cleared(self):
        device = Device()
        verification = Verification(device, verify_error=ProtocolError("link lost"))
        with self.assertRaisesRegex(UpdateError, "main kernel was not cleared") as caught:
            resume(device, verification)
        self.assertIn("resume: verifying the already written recovery", str(caught.exception))
        self.assertIn("Keep the device powered", str(caught.exception))

    def test_a_source_that_changes_during_the_readback_stops_before_the_main_kernel_is_cleared(self):
        device = Device()
        verification = Verification(device, change_version=V156)
        with self.assertRaises(UpdateError):
            resume(device, verification)
        self.assertNotIn("invalidate", device.events)
        self.assertNotIn("begin-main", device.events)

    def test_an_uncertain_clear_is_never_retried_and_never_claims_the_kernel_is_intact(self):
        device = Device(invalidate_error=ProtocolError("delivery uncertain"))
        verification = Verification(device)
        with self.assertRaises(UpdateError) as caught:
            resume(device, verification)
        self.assertEqual(device.events.count("invalidate"), 1)
        self.assertNotIn("reboot-1", device.events)
        self.assertNotIn("begin-main", device.events)
        self.assertNotIn("was not cleared", str(caught.exception))
        self.assertIn("Main-kernel clearing was attempted", str(caught.exception))
        self.assertIn("main kernel clear attempted: True", failure(caught.exception)["notes"])
        self.assertEqual(verification.results[-1][0], "stopped")

    def test_recovery_connection_failure_preserves_clear_state_in_saved_report(self):
        for error in (OSError("forward disconnected"), KeyboardInterrupt(), RuntimeError("unexpected")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                device = Device()
                original_connect = device.connect

                def connect():
                    if device.cleared:
                        raise error
                    return original_connect()

                reader = MagicMock(host_keys=[], uid=os.getuid(), gid=os.getgid())
                verification = RecoveryVerifier(SimpleNamespace(sha256="fixture"), reader,
                                                parent=directory, progress=lambda message: None)
                expected = RuntimeError if isinstance(error, RuntimeError) else UpdateError
                with patch.object(device, "connect", side_effect=connect), \
                     patch.object(verification, "preflight"), patch.object(verification, "verify"):
                    with self.assertRaises(expected) as caught:
                        with verification:
                            verification.record.update(preflight="passed", verification="passed")
                            resume(device, verification)
                record = json.loads((verification.directory / "report.json").read_text())
                self.assertTrue(device.cleared)
                self.assertEqual(device.events.count("invalidate"), 1)
                self.assertNotIn("begin-main", device.events)
                self.assertEqual(record["update_sequence"], "stopped")
                self.assertEqual(record["update_stage"], "resume: checking recovery before main transfer")
                self.assertIn("main kernel clear attempted: True", record["failure"]["notes"])
                self.assertIn("main kernel clear attempted: True", failure(caught.exception)["notes"])
                self.assertEqual(device.events[-1], "close")

    def test_final_verification_failure_retains_clear_state_without_repeating_writes(self):
        device = Device()
        verification = Verification(device)
        with self.assertRaises(UpdateError) as caught:
            resume(device, verification, final_verification=Mock(side_effect=OSError("SSH lost")))
        self.assertIn("final destination SSH verification", str(caught.exception))
        self.assertIn("Main-kernel clearing was attempted", str(caught.exception))
        self.assertEqual(device.events.count("invalidate"), 1)
        self.assertEqual(device.events.count("commit-btweb_only.ext4.gz"), 1)
        self.assertEqual(device.events.count("commit-uImage.zip"), 1)
        self.assertEqual(verification.results[-1], ("stopped", "final destination SSH verification"))

    def test_a_recovery_boot_that_reports_a_source_version_is_refused(self):
        device = Device(recovery_version=V157)
        with self.assertRaises(UpdateError):
            resume(device, Verification(device))
        self.assertNotIn("begin-main", device.events)

    def test_the_source_versions_are_required(self):
        for versions in (None, frozenset()):
            with self.subTest(versions=versions):
                device = Device()
                with self.assertRaises(ValueError):
                    resume(device, Verification(device), source_versions=versions)
                self.assertEqual(device.events, [])

    def test_the_device_is_closed_when_the_checks_fail(self):
        device = Device(busy=True)
        with self.assertRaises(UpdateError):
            resume(device, Verification(device))
        self.assertEqual(device.events[-1], "close")

    def test_an_interruption_is_reported_without_a_cleanup_reboot(self):
        device = Device()
        with self.assertRaisesRegex(UpdateError, "Interrupted at.*main kernel was not cleared"):
            resume(device, Verification(device, verify_error=KeyboardInterrupt()))
        self.assertNotIn("reboot-1", device.events)


class FlashFromRecoveryTests(unittest.TestCase):
    def test_a_verification_given_to_an_update_from_recovery_only_records_the_outcome(self):
        device = Device()
        device.cleared, device.version, device.status = True, V158, 1
        verification = Verification(device)
        updater._flash(FIRMWARE, device, PROFILE, lambda message: None, from_recovery=True,
                       verification=verification)
        self.assertNotIn("verify-preflight", device.events)
        self.assertEqual([status for status, stage in verification.results], ["completed"])

    def test_without_a_verification_nothing_changes(self):
        device = Device()
        device.cleared, device.version, device.status = True, V158, 1
        updater._flash(FIRMWARE, device, PROFILE, lambda message: None, from_recovery=True)
        self.assertEqual([e for e in device.events if e.startswith("begin")], ["begin-main"])


def key(label):
    return "ssh-rsa " + base64.b64encode(label.encode()).decode()


class WirelessResumeTests(unittest.TestCase):
    P157, P158 = sp.SOURCE_PROFILES[V157], sp.SOURCE_PROFILES[V158]

    def make(self, **changes):
        w = object.__new__(Wireless)
        w.phase, w.reconnecting, w.connection, w.tunnel = 0, False, Mock(), None
        w.source_candidates, w.rotation_accepted = (self.P157,), False
        for name, value in changes.items():
            setattr(w, name, value)
        return w

    def test_resume_moves_to_the_phase_that_follows_the_recovery_transfer(self):
        w = self.make()
        w.resume_after_recovery()
        self.assertEqual(w.phase, 1)
        self.assertTrue(w.rotation_accepted)

    def test_the_next_reboot_must_be_the_one_into_recovery(self):
        w = self.make(old_key=key("source"), image=SimpleNamespace(host_key=key("image")), previous_key=None)
        w.resume_after_recovery()
        with self.assertRaises(SSHError):
            w.rebooting(4)
        w.rebooting(1)
        self.assertEqual((w.phase, w.reconnecting, w.previous_key), (2, True, key("source")))

    def test_resume_needs_a_freshly_entered_source_main(self):
        for label, changes in (("already resumed", dict(phase=1)),
                               ("waiting for a reboot", dict(reconnecting=True)),
                               ("not connected", dict(connection=None)),
                               ("no matched profile", dict(source_candidates=()))):
            with self.subTest(label):
                w = self.make(**changes)
                with self.assertRaises(SSHError):
                    w.resume_after_recovery()
                self.assertEqual(w.phase, changes.get("phase", 0))


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "classe100x", *arguments], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    def test_the_commands_offer_the_ssh_options_and_no_usb_transport(self):
        for command in ("plan-resume-recovery", "resume-recovery"):
            with self.subTest(command=command):
                result = self.run_cli(command, "--help")
                self.assertEqual(result.returncode, 0)
                for option in ("--host", "--ssh-key", "--ssh-password", "--destination-ssh-user",
                               "--accept-regenerated-host-key", "--debug"):
                    self.assertIn(option, result.stdout)
                for option in ("--transport", "--external-usb", "--tetherkit"):
                    self.assertNotIn(option, result.stdout)

    def test_an_invalid_firmware_stops_before_any_device_connection(self):
        for command in ("plan-resume-recovery", "resume-recovery"):
            with self.subTest(command=command):
                result = self.run_cli(command, "--host", "192.0.2.1", "--ssh-key", "unused", "missing.fwz")
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
