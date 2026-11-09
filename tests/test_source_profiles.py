import unittest
from types import MappingProxyType
from unittest.mock import patch

from classe100x import source_profiles as sp
from classe100x.wireless import SSHError, Wireless, installer_check
from classe100x.wireless_image import facts

P157 = sp.SOURCE_PROFILES[(1, 5, 7)]
P158 = sp.SOURCE_PROFILES[(1, 5, 8)]


def hashes(profile):
    return dict(profile.executable_sha256)


def make_wireless(profile_hashes, phase=0, candidates=()):
    # Wireless without a real SSH connection: only run() is replaced.
    wireless = object.__new__(Wireless)
    wireless.phase = phase
    wireless.source_candidates = candidates

    def run(command, **kwargs):
        if command == installer_check():
            return b"READY\n"
        if command == "sha256sum " + " ".join(sp.UPDATE_EXECUTABLES):
            return "".join(f"{profile_hashes[p]}  {p}\n" for p in sp.UPDATE_EXECUTABLES).encode()
        raise AssertionError("Unexpected remote command: " + command)

    wireless.run = run
    return wireless


class SourceProfileTableTests(unittest.TestCase):
    def test_every_profile_pins_every_update_executable(self):
        for version, profile in sp.SOURCE_PROFILES.items():
            with self.subTest(version=version):
                self.assertEqual(profile.version, version)
                self.assertEqual(set(profile.executable_sha256), set(sp.UPDATE_EXECUTABLES))

    def test_target_profile_equals_the_no_ota_pins(self):
        pins = facts("no-ota")["UNCHANGED"]
        for path in sp.UPDATE_EXECUTABLES:
            self.assertEqual(sp.target_profile().executable_sha256[path], pins[path][0], path)

    def test_invalid_profiles_are_rejected(self):
        good = hashes(P158)
        for label, bad in (("missing", {k: v for k, v in good.items() if "fw_manager" not in k}),
                           ("short", {**good, sp.UPDATE_EXECUTABLES[0]: "abc"}),
                           ("uppercase", {**good, sp.UPDATE_EXECUTABLES[0]: "A" * 64})):
            with self.subTest(label), self.assertRaises(ValueError):
                sp.SourceProfile(version=(9, 9, 9), executable_sha256=bad)

    def test_matching_requires_exact_and_complete_hashes(self):
        self.assertEqual(sp.matching_profiles(hashes(P157)), (P157,))
        self.assertEqual(sp.matching_profiles(hashes(P158)), (P158,))
        altered = {**hashes(P157), sp.UPDATE_EXECUTABLES[0]: "0" * 64}
        self.assertEqual(sp.matching_profiles(altered), ())
        with self.assertRaises(ValueError):
            sp.matching_profiles({sp.UPDATE_EXECUTABLES[0]: "0" * 64})

    def test_select_by_version(self):
        self.assertIs(sp.select_by_version((P157, P158), (1, 5, 8)), P158)
        with self.assertRaises(ValueError):
            sp.select_by_version((P157,), (1, 5, 8))

    def test_new_version_needs_only_a_table_entry(self):
        p156 = sp.SourceProfile(version=(1, 5, 6),
                                executable_sha256={**hashes(P157), sp.UPDATE_EXECUTABLES[1]: "1" * 64})
        table = MappingProxyType({**sp.SOURCE_PROFILES, (1, 5, 6): p156})
        with patch.object(sp, "SOURCE_PROFILES", table):
            self.assertEqual(sp.matching_profiles(hashes(p156)), (p156,))
            wireless = make_wireless(hashes(p156))
            wireless.preflight()
            self.assertEqual(wireless.source_candidates, (p156,))

    def test_identical_executables_in_two_versions_stay_ambiguous_until_version_is_known(self):
        twin = sp.SourceProfile(version=(1, 5, 9), executable_sha256=hashes(P158))
        table = MappingProxyType({**sp.SOURCE_PROFILES, (1, 5, 9): twin})
        with patch.object(sp, "SOURCE_PROFILES", table):
            found = sp.matching_profiles(hashes(P158))
            self.assertEqual({p.version for p in found}, {(1, 5, 8), (1, 5, 9)})
            self.assertIs(sp.select_by_version(found, (1, 5, 9)), twin)

    def test_mismatch_description_names_the_closest_profile_and_files(self):
        altered = {**hashes(P157), sp.UPDATE_EXECUTABLES[0]: "0" * 64}
        text = sp.describe_mismatch(altered)
        self.assertIn("1.5.7", text)
        self.assertIn("bt_device", text)
        self.assertNotIn("fw_manager", text)


class PreflightPhaseTests(unittest.TestCase):
    def test_source_main_accepts_each_supported_profile(self):
        for profile in sp.SOURCE_PROFILES.values():
            with self.subTest(version=profile.version):
                wireless = make_wireless(hashes(profile))
                wireless.preflight()
                self.assertEqual(wireless.source_candidates, (profile,))

    def test_unknown_source_is_rejected_and_names_the_difference(self):
        altered = {**hashes(P157), sp.UPDATE_EXECUTABLES[1]: "0" * 64}
        with self.assertRaisesRegex(SSHError, "no supported source firmware profile.*bt_daemon"):
            make_wireless(altered).preflight()

    def test_same_profile_must_still_match_after_first_normal_reboot(self):
        wireless = make_wireless(hashes(P157), phase=1, candidates=(P157,))
        wireless.preflight()
        self.assertEqual(wireless.source_candidates, (P157,))

    def test_source_cannot_change_profile_across_the_first_reboot(self):
        wireless = make_wireless(hashes(P158), phase=1, candidates=(P157,))
        with self.assertRaises(SSHError):
            wireless.preflight()

    def test_recovery_and_final_main_require_the_target_profile(self):
        for phase in (2, 3):
            with self.subTest(phase=phase):
                make_wireless(hashes(P158), phase=phase, candidates=(P157,)).preflight()
                with self.assertRaisesRegex(SSHError, "differ from the target profile.*fw_manager"):
                    make_wireless(hashes(P157), phase=phase, candidates=(P157,)).preflight()


if __name__ == "__main__":
    unittest.main()
