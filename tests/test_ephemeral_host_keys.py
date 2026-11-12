import base64
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from classe100x import source_profiles as sp
from classe100x import wireless
from classe100x.wireless import HostIdentityError, SSHError, Wireless, fingerprint

ROOT = Path(__file__).resolve().parent.parent
P157 = sp.SOURCE_PROFILES[(1, 5, 7)]
P158 = sp.SOURCE_PROFILES[(1, 5, 8)]
assert P157.host_key_policy is sp.HostKeyPolicy.EPHEMERAL_ON_NORMAL_REBOOT
assert P158.host_key_policy is sp.HostKeyPolicy.STABLE


def key(label):
    return "ssh-rsa " + base64.b64encode(label.encode()).decode()


FIRST, SECOND, TARGET, OTHER = key("first boot"), key("second boot"), key("target image"), key("other")


def credentials(label):
    return SimpleNamespace(label=label, connection=Mock(name=label + "-connection"), password=label)


def make(phase=0, reconnecting=False, candidates=(P157,), old=FIRST, previous=None, accept=True,
         accepted=False):
    w = object.__new__(Wireless)
    w.host, w.ip = "intercom.example", "192.0.2.1"
    w.phase, w.reconnecting = phase, reconnecting
    w.old_key, w.previous_key = old, previous
    w.image = SimpleNamespace(host_key=TARGET)
    w.connection = w.tunnel = None
    w.host_keys = []
    w.source_candidates = tuple(candidates)
    w.confirm = Mock(return_value=True)  # first enrollment only: never used for a regenerated key
    w.accept_regenerated_key = accept
    w.rotation_accepted = accepted
    w.trust = Mock()
    w.existing, w.destination = credentials("existing"), credentials("destination")
    return w


class EphemeralPolicyTests(unittest.TestCase):
    def test_policy_requires_every_candidate_to_be_ephemeral(self):
        twin = sp.SourceProfile(version=(1, 5, 9), executable_sha256=P157.executable_sha256)
        self.assertTrue(make(candidates=(P157,)).ephemeral_source)
        self.assertFalse(make(candidates=(P158,)).ephemeral_source)
        self.assertFalse(make(candidates=(P157, twin)).ephemeral_source)
        self.assertFalse(make(candidates=()).ephemeral_source)


class RegeneratedKeyTests(unittest.TestCase):
    def connect(self, w, observed):
        with patch.object(wireless, "scan_keys", return_value=observed), patch.object(wireless, "Tunnel") as tunnel:
            w._connect()
        return tunnel

    def test_new_key_is_accepted_once_without_prompt_and_used_with_the_existing_credentials(self):
        w = make(phase=1, reconnecting=True, previous=FIRST)
        tunnel = self.connect(w, {SECOND})
        w.confirm.assert_not_called()
        tunnel.assert_called_once_with(w.existing, "192.0.2.1", SECOND)
        w.existing.connection.assert_called_once_with("192.0.2.1", SECOND)
        self.assertEqual(w.old_key, SECOND)
        self.assertTrue(w.rotation_accepted)
        self.assertEqual([r["status"] for r in w.host_keys], ["regenerated_key_accepted", "verified"])
        self.assertEqual(w.host_keys[0]["previous_fingerprint"], fingerprint(FIRST))

    def test_without_the_opt_in_the_new_key_is_refused(self):
        w = make(phase=1, reconnecting=True, previous=FIRST, accept=False)
        with patch.object(wireless, "scan_keys", return_value={SECOND}), patch.object(wireless, "Tunnel") as tunnel:
            with self.assertRaisesRegex(HostIdentityError, "Unexpected SSH identity"):
                w._connect()
        tunnel.assert_not_called()
        self.assertFalse(w.rotation_accepted)
        self.assertEqual(w.old_key, FIRST)

    def test_the_previous_key_still_answering_means_waiting_not_rotation(self):
        w = make(phase=1, reconnecting=True, previous=FIRST)
        w.old_key = SECOND  # the expected key differs, but the old environment still answers
        with patch.object(wireless, "Tunnel") as tunnel, patch.object(wireless, "scan_keys", return_value={FIRST}):
            with self.assertRaises(SSHError) as caught:
                w._connect()
        self.assertNotIsInstance(caught.exception, HostIdentityError)
        tunnel.assert_not_called()
        self.assertFalse(w.rotation_accepted)

    def test_stable_profiles_keep_strict_continuity_even_with_the_opt_in(self):
        w = make(phase=1, reconnecting=True, candidates=(P158,), previous=FIRST)
        with patch.object(wireless, "scan_keys", return_value={SECOND}), patch.object(wireless, "Tunnel") as tunnel:
            with self.assertRaisesRegex(HostIdentityError, "Unexpected SSH identity"):
                w._connect()
        tunnel.assert_not_called()

    def test_a_second_regeneration_is_refused(self):
        w = make(phase=1, reconnecting=True, previous=FIRST, accepted=True, old=SECOND)
        with patch.object(wireless, "scan_keys", return_value={OTHER}), patch.object(wireless, "Tunnel") as tunnel:
            with self.assertRaises(HostIdentityError):
                w._connect()
        tunnel.assert_not_called()

    def test_only_the_first_normal_reboot_may_regenerate_the_key(self):
        cases = (("before any reboot", dict(phase=0, reconnecting=False)),
                 ("not waiting for a reboot", dict(phase=1, reconnecting=False)),
                 ("recovery boot", dict(phase=2, reconnecting=True)),
                 ("final main boot", dict(phase=3, reconnecting=True)))
        for label, options in cases:
            with self.subTest(label):
                w = make(previous=FIRST, **options)
                with patch.object(wireless, "scan_keys", return_value={OTHER}), \
                        patch.object(wireless, "Tunnel") as tunnel:
                    with self.assertRaises(HostIdentityError):
                        w._connect()
                tunnel.assert_not_called()

    def test_recovery_and_final_main_still_require_the_target_image_key(self):
        w = make(phase=2, reconnecting=True, previous=SECOND, old=SECOND, accepted=True)
        tunnel = self.connect(w, {TARGET})
        tunnel.assert_called_once_with(w.destination, "192.0.2.1", TARGET)
        w.confirm.assert_not_called()


class EnterTrustTests(unittest.TestCase):
    def enter(self, candidates, accept):
        w = make(candidates=(), accept=accept)
        w.trust.enroll.return_value = FIRST

        def preflight():
            w.source_candidates = tuple(candidates)

        with patch.object(wireless, "resolve", return_value="192.0.2.1"), patch.object(w, "_connect"), \
                patch.object(w, "preflight", side_effect=preflight):
            w.__enter__()
        return w

    def test_a_stable_source_identity_is_saved_as_trust(self):
        for accept in (False, True):
            with self.subTest(accept=accept):
                self.enter((P158,), accept).trust.save.assert_called_once_with(FIRST)

    def test_an_ephemeral_source_with_the_opt_in_is_never_saved(self):
        self.enter((P157,), True).trust.save.assert_not_called()

    def test_an_ephemeral_source_without_the_opt_in_stops_before_any_write(self):
        w = make(candidates=(), accept=False)
        w.trust.enroll.return_value = FIRST

        def preflight():
            w.source_candidates = (P157,)

        with patch.object(wireless, "resolve", return_value="192.0.2.1"), patch.object(w, "_connect"), \
                patch.object(w, "preflight", side_effect=preflight):
            with self.assertRaisesRegex(SSHError, "--accept-regenerated-host-key"):
                w.__enter__()
        w.trust.save.assert_not_called()


class SequenceTests(unittest.TestCase):
    def test_full_sequence_for_an_ephemeral_source(self):
        w = make(candidates=(P157,))
        scans = iter([{FIRST}, {SECOND}, {SECOND}, {TARGET}, {TARGET}, {TARGET}])
        with patch.object(wireless, "scan_keys", side_effect=lambda ip: next(scans)), \
                patch.object(wireless, "Tunnel") as tunnel, \
                patch.object(wireless, "resolve", return_value="192.0.2.1"), \
                patch.object(w, "preflight"):
            tunnel.return_value.ports = [23000, 23001, 23002]
            w._connect()                       # source MAIN, first boot key
            w.rebooting(4)                     # recovery written, normal reboot
            self.assertEqual(w.previous_key, FIRST)
            w.endpoints()                      # regenerated key, accepted by the opt-in
            w.arrived(4)
            self.assertEqual(w.old_key, SECOND)
            w.rebooting(1)                     # main kernel cleared, reboot into recovery
            self.assertEqual(w.previous_key, SECOND)
            with self.assertRaises(SSHError):  # the source MAIN still answers: wait, do not connect
                w.endpoints()
            w.endpoints()                      # recovery image key
            w.arrived(1)
            w.rebooting(4)
            w.endpoints()                      # final MAIN carries the image key
            w.arrived(4)
            w.verified()
            w.trust.save.assert_not_called()
            w.remember()
            w.trust.save.assert_called_once_with(TARGET)
        w.confirm.assert_not_called()
        self.assertEqual([c.args[0].label for c in tunnel.call_args_list],
                         ["existing", "existing", "destination", "destination"])


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "classe100x", *arguments], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    def test_the_opt_in_is_offered_for_plan_and_flash(self):
        for command in ("plan", "flash"):
            with self.subTest(command=command):
                result = self.run_cli(command, "--help")
                self.assertEqual(result.returncode, 0)
                self.assertIn("--accept-regenerated-host-key", result.stdout)

    def test_the_opt_in_requires_the_ssh_transport(self):
        for command in ("plan", "flash"):
            with self.subTest(command=command):
                result = self.run_cli(command, "--accept-regenerated-host-key", "unused.fwz")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("--transport ssh", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
