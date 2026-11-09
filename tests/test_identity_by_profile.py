import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from classe100x import source_profiles as sp
from classe100x import updater
from classe100x.updater import NetworkDevice, UpdateError, check_identity, flash, flash_recovery

V157, V158, V156 = (1, 5, 7), (1, 5, 8), (1, 5, 6)


def identity(version=V158, status=4, hardware=("02", "06", "0"), **overrides):
    info = {"device_type": ("200",), "firmware": tuple(str(p) for p in version),
            "hardware": hardware, "object_model": ("1", "0", "99"),
            "update_status": (str(status), "0"), "uptime": ("0", "0", "0", "1")}
    info.update(overrides)
    return info


class CandidateVersionTests(unittest.TestCase):
    def test_versions_of_matched_profiles(self):
        self.assertEqual(sp.candidate_versions(sp.SOURCE_PROFILES.values()), frozenset({V157, V158}))
        self.assertEqual(sp.candidate_versions([sp.SOURCE_PROFILES[V157]]), frozenset({V157}))

    def test_no_candidates_means_target_only(self):
        self.assertIsNone(sp.candidate_versions(()))


class CheckIdentityTests(unittest.TestCase):
    def test_default_accepts_only_the_target(self):
        check_identity(identity(V158), 4)
        with self.assertRaises(UpdateError):
            check_identity(identity(V157), 4)

    def test_source_versions_are_accepted_and_others_rejected(self):
        allowed = frozenset({V157})
        check_identity(identity(V157), 4, source_versions=allowed)
        for version in (V158, V156):
            with self.subTest(version=version), self.assertRaisesRegex(UpdateError, "one of 1.5.7"):
                check_identity(identity(version), 4, source_versions=allowed)

    def test_every_other_field_stays_strict(self):
        allowed = frozenset({V157})
        for label, info, status in (
                ("hardware family", identity(V157, hardware=("03", "06", "0")), 4),
                ("object model", identity(V157, object_model=("1", "0", "98")), 4),
                ("device type", identity(V157, device_type=("201",)), 4),
                ("update status", identity(V157, status=1), 4),
                ("missing firmware", {k: v for k, v in identity(V157).items() if k != "firmware"}, 4)):
            with self.subTest(label), self.assertRaises(UpdateError):
                check_identity(info, status, source_versions=allowed)


class FakeClient:
    def __init__(self, device):
        self.device = device

    def idle(self):
        return True

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
        self.device.cleared = True


class FakeDevice:
    """Mimics NetworkDevice for _flash(): reboot identity is checked with the real check_identity."""

    def __init__(self, version=V157, status=4, recovery_version=V158):
        self.events, self.reboot_calls = [], []
        self.version, self.status, self.recovery_version = version, status, recovery_version
        self.cleared = self.main_written = False
        self.client = FakeClient(self)

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
        self.reboot_calls.append((status, options))
        if self.cleared and status == 1:
            self.version, self.status = self.recovery_version, 1
        elif self.main_written:
            self.version, self.status = V158, 4
        info = identity(self.version, self.status)
        check_identity(info, status, **options)
        return info


FIRMWARE = SimpleNamespace(directory=Path("fw"),
                           payload=lambda name: SimpleNamespace(name=name, size=1, cksum=1))
PROFILE = SimpleNamespace(normal=object(), recovery=object())


class FakeVerification:
    """Stands in for RecoveryVerifier: records when the installed recovery is read back."""

    def __init__(self, device):
        self.device = device

    def preflight(self):
        self.device.events.append("verify-preflight")

    def update_result(self, status, stage):
        pass

    def verify(self):
        self.device.events.append("verify")


def run_flash(device, **kwargs):
    return flash(FIRMWARE, device, PROFILE, report=lambda message: None, **kwargs)


class FlashFlowTests(unittest.TestCase):
    def test_source_version_is_accepted_only_before_recovery_is_entered(self):
        device = FakeDevice(V157)
        run_flash(device, source_versions=frozenset({V157}))
        self.assertEqual(device.reboot_calls, [(4, {"source_versions": frozenset({V157})}), (1, {}), (4, {})])
        events = device.events
        self.assertLess(events.index("begin-recovery"), events.index("invalidate"))
        self.assertLess(events.index("invalidate"), events.index("begin-main"))
        self.assertEqual(events.count("invalidate"), 1)

    def test_source_version_is_accepted_around_the_recovery_readback(self):
        device = FakeDevice(V157)
        run_flash(device, source_versions=frozenset({V157}), verification=FakeVerification(device))
        events = device.events
        self.assertLess(events.index("verify-preflight"), events.index("begin-recovery"))
        self.assertLess(events.index("verify"), events.index("invalidate"))
        # Three explicit identity reads on the source MAIN: initial, after the preflight and
        # after the readback. The first reboot checks the identity inside reboot_and_wait().
        self.assertEqual(events.count("connect"), 3)

    def test_a_source_that_changes_during_the_readback_stops_before_the_main_kernel_is_cleared(self):
        device = FakeDevice(V157)

        class ChangingVerification(FakeVerification):
            def verify(self):
                super().verify()
                device.version = V156

        with self.assertRaises(UpdateError):
            run_flash(device, source_versions=frozenset({V157}), verification=ChangingVerification(device))
        self.assertNotIn("invalidate", device.events)
        self.assertNotIn("begin-main", device.events)

    def test_reinstalling_the_target_still_works(self):
        device = FakeDevice(V158)
        run_flash(device, source_versions=frozenset({V158}))
        self.assertEqual([call[0] for call in device.reboot_calls], [4, 1, 4])

    def test_without_source_versions_the_old_behaviour_is_unchanged(self):
        device = FakeDevice(V158)
        run_flash(device)
        self.assertEqual(device.reboot_calls, [(4, {}), (1, {}), (4, {})])

    def test_unsupported_source_stops_before_any_write(self):
        for version, allowed in ((V156, frozenset({V157})), (V157, None)):
            with self.subTest(version=version):
                device = FakeDevice(version)
                with self.assertRaises(UpdateError):
                    run_flash(device, source_versions=allowed)
                self.assertFalse([e for e in device.events if e.startswith(("begin", "commit", "upload", "invalidate"))])

    def test_recovery_boot_must_report_the_target_firmware(self):
        device = FakeDevice(V157, recovery_version=V157)
        with self.assertRaisesRegex(UpdateError, "firmware"):
            run_flash(device, source_versions=frozenset({V157}))
        self.assertNotIn("begin-main", device.events)

    def test_resuming_from_recovery_never_accepts_a_source_version(self):
        device = FakeDevice(V157, status=1)
        with self.assertRaises(UpdateError):
            flash_recovery(FIRMWARE, device, PROFILE, report=lambda message: None)
        with self.assertRaises(ValueError):
            updater._flash(FIRMWARE, FakeDevice(V158, status=1), PROFILE, lambda message: None,
                           from_recovery=True, source_versions=frozenset({V157}))


class RebootProbe:
    info = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def inspect(self):
        return RebootProbe.info


class RebootClient:
    def query(self, number):
        return ("0", "0", "10", "0")

    def reboot(self):
        pass

    def close(self):
        pass


class RebootAndWaitTests(unittest.TestCase):
    def reboot(self, info, **options):
        RebootProbe.info = info
        device = NetworkDevice("127.0.0.1")
        device.client = RebootClient()
        with patch.object(updater, "ReadOnlyClient", RebootProbe), \
                patch.object(updater.time, "sleep"), \
                patch.object(device, "connect", return_value=info):
            return device.reboot_and_wait(4, **options)

    def test_target_by_default(self):
        self.assertEqual(self.reboot(identity(V158))["firmware"], ("1", "5", "8"))
        with self.assertRaises(UpdateError):
            self.reboot(identity(V157))

    def test_source_version_is_checked_on_both_identity_reads(self):
        allowed = frozenset({V157})
        self.assertEqual(self.reboot(identity(V157), source_versions=allowed)["firmware"], ("1", "5", "7"))
        with self.assertRaises(UpdateError):
            self.reboot(identity(V156), source_versions=allowed)


if __name__ == "__main__":
    unittest.main()
