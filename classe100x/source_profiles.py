"""Verified source firmware profiles for supported update transitions."""
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

UPDATE_EXECUTABLES = (
    "/home/bticino/bin/bt_device",
    "/home/bticino/bin/bt_daemon",
    "/home/bticino/bin/fw_manager",
    "/home/bticino/bin/dedrifupdater",
)

class HostKeyPolicy(Enum):
    STABLE = "stable"
    EPHEMERAL_ON_NORMAL_REBOOT = "ephemeral_on_normal_reboot"

@dataclass(frozen=True)
class SourceProfile:
    version: tuple[int, int, int]
    executable_sha256: Mapping[str, str]
    device_type: tuple[int, ...] = (200,)
    hardware_family: tuple[int, ...] = (2,)
    object_model: tuple[int, ...] = (1, 0, 99)
    normal_status: tuple[int, ...] = (4, 0)
    host_key_policy: HostKeyPolicy = HostKeyPolicy.STABLE

    def __post_init__(self):
        if set(self.executable_sha256) != set(UPDATE_EXECUTABLES):
            raise ValueError("Source profile must pin every update executable")
        for digest in self.executable_sha256.values():
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Invalid SHA-256 in source profile")
        object.__setattr__(self, "executable_sha256",
                           MappingProxyType(dict(self.executable_sha256)))

SOURCE_PROFILES = MappingProxyType({
    (1, 5, 7): SourceProfile(
        version=(1, 5, 7),
        host_key_policy=HostKeyPolicy.EPHEMERAL_ON_NORMAL_REBOOT,
        executable_sha256={
            "/home/bticino/bin/bt_device": "e0db9d2d01e549479a0c3e832a6dbcb76a5d355d95b3105d00fe1eb303b604be",
            "/home/bticino/bin/bt_daemon": "812189781d79a417f3b32dbd780cb89ec75cbb3aedffd99f91c1780889621b5a",
            "/home/bticino/bin/fw_manager": "8456017c289be20a8956ce496d806aa6083ad482a80562cfd8aed0cba88673f9",
            "/home/bticino/bin/dedrifupdater": "faae6c8fd4a876e4609e695b742302079430b287cd465d1f07d8593323ae518d",
        },
    ),
    (1, 5, 8): SourceProfile(
        version=(1, 5, 8),
        executable_sha256={
            "/home/bticino/bin/bt_device": "e0db9d2d01e549479a0c3e832a6dbcb76a5d355d95b3105d00fe1eb303b604be",
            "/home/bticino/bin/bt_daemon": "812189781d79a417f3b32dbd780cb89ec75cbb3aedffd99f91c1780889621b5a",
            "/home/bticino/bin/fw_manager": "9b6aee9fbe5003a3b231ba61887f1a50dd818cbd66fa83bd045f1f2b7025b643",
            "/home/bticino/bin/dedrifupdater": "faae6c8fd4a876e4609e695b742302079430b287cd465d1f07d8593323ae518d",
        },
    ),
})

def profile_for_version(version: tuple[int, int, int]) -> SourceProfile:
    try:
        return SOURCE_PROFILES[version]
    except KeyError as exc:
        raise ValueError(f"Unsupported source firmware version: {version}") from exc


# Firmware version the bundled FWZ profile installs. Recovery and the final MAIN
# must always match this profile, whatever the source version was.
TARGET_VERSION = (1, 5, 8)


def target_profile() -> SourceProfile:
    return SOURCE_PROFILES[TARGET_VERSION]


def matching_profiles(observed: Mapping[str, str]) -> tuple[SourceProfile, ...]:
    """Profiles whose pinned executables equal the observed hashes exactly.

    Several profiles may match when two versions ship identical executables. The
    version reported by the device then selects between them (select_by_version).
    """
    if set(observed) != set(UPDATE_EXECUTABLES):
        raise ValueError("Observed hashes must cover every update executable")
    return tuple(profile for profile in SOURCE_PROFILES.values()
                 if dict(profile.executable_sha256) == dict(observed))


def select_by_version(candidates, version) -> SourceProfile:
    for profile in candidates:
        if profile.version == tuple(version):
            return profile
    raise ValueError(f"No candidate source profile for firmware {tuple(version)}")


def describe_mismatch(observed: Mapping[str, str], profiles=None) -> str:
    """Human-readable difference against the closest profile, for error messages."""
    pool = tuple(SOURCE_PROFILES.values() if profiles is None else profiles)
    if not pool:
        return ""

    def differing(profile):
        return [path for path in UPDATE_EXECUTABLES
                if observed.get(path) != profile.executable_sha256[path]]

    closest = min(pool, key=lambda profile: len(differing(profile)))
    names = ", ".join(path.rsplit("/", 1)[-1] for path in differing(closest))
    return "closest profile {}.{}.{} differs in: {}".format(*closest.version, names)
