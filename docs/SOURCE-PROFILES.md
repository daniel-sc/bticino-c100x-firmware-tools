# Source firmware profiles

The update sequence was researched on firmware 1.5.8. A **source profile** records what is known about another firmware version that the sequence may start from. Profiles are data in [`classe100x/source_profiles.py`](../classe100x/source_profiles.py), and the update logic contains no version-specific code. For how they are used during an update, see [Updating from an earlier firmware version](FLASHING.md#updating-from-an-earlier-firmware-version).

## What a profile pins

- `version`: the firmware version, for example `(1, 5, 7)`.
- `executable_sha256`: the SHA-256 of `bt_device`, `bt_daemon`, `fw_manager` and `dedrifupdater` in `/home/bticino/bin`. All four are required: a profile that misses one, or has a malformed digest, cannot be created. They are the executables that take part in the update path. The commands were researched against the 1.5.8 executables, and a profile claims that the executables of another version behave the same for that path. Only hardware evidence can establish that.
- `host_key_policy`: `STABLE` when the SSH host key survives a normal reboot, `EPHEMERAL_ON_NORMAL_REBOOT` when it does not.

Device type, hardware family, object model and update state are not part of a profile: they are fixed values checked in every phase.

## How a running system is matched

The preflight hashes the four executables and compares them with every profile. A profile matches only when all four are equal. Two versions may ship identical executables. All of their versions are then accepted together, and the version the device reports must be one of them.

## Current profiles

- **1.5.8**, `STABLE`. The stock executables, equal to the pins of the `no-ota` payload. The 1.5.8 update path is the one recorded in [ACCEPTANCE.md](ACCEPTANCE.md).
- **1.5.7**, `EPHEMERAL_ON_NORMAL_REBOOT`. Read from one intercom (`02*06*0`). `bt_device`, `bt_daemon` and `dedrifupdater` equal those of 1.5.8. `fw_manager` is `8456017c289be20a8956ce496d806aa6083ad482a80562cfd8aed0cba88673f9`, not yet compared with an official 1.5.7 image. The host key is regenerated at every normal boot because `/var/lib` is a RAM disk.

## Adding a version

A version is added as a data entry, with this evidence:

1. **Hashes.** Prefer an official image of that version: hash the four executables of its main filesystem. If there is none, hash them on a running intercom of that version and say so, because one device is weaker evidence.
2. **Identity.** Record what the device reports (for example with `probe`): device type 200, hardware family 02, object model 1.0.99 and update state 4 in the normal system. These are what the update checks.
3. **Host key.** Reboot the system normally and compare its SSH host key before and after (`ssh-keyscan -t rsa HOST`). If it changes, use `EPHEMERAL_ON_NORMAL_REBOOT`.
4. **The update path.** Run `plan` and a complete `flash` on an intercom of that version, and record the result in [ACCEPTANCE.md](ACCEPTANCE.md). A profile without a completed update is not evidence that the sequence works from that version.
5. **The entry.** Add it to `SOURCE_PROFILES`. `tests/test_source_profiles.py` checks every entry, so a new version needs a test of its own only for behavior that is specific to it.
