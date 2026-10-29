# Optional SSH recovery verification — design interview

**2026-10-29 — Design confirmed; implementation authorized.** This records the
agreed optional verifier. It is not authorization to flash a device.

Terminology is in [../GLOSSARY.md](../GLOSSARY.md); existing behavior and research
evidence are in [PROTOCOL.md](PROTOCOL.md).

## Agreed: Q1–Q4

1. Add a supported, explicitly selected optional SSH-verification mode for devices
   with SSH already enabled in their currently installed main firmware.
2. Once selected, verification must pass before clearing the normal kernel.
   Unavailable authentication, failed checks or inconclusive results stop the
   sequence; there is no automatic fallback to unchecked flashing.
3. Use SSH over the same USB network connection, with no automatic LAN fallback.
   Establish access before firmware writes. USB can transport SSH, but acceptance
   of SSH connections on this device's USB address still needs validation.
4. Prefer comprehensive recovery filesystem, kernel and DTB verification over a
   quick sample check, accepting additional transfer time and temporary storage.

## Agreed: Q5–Q9

5. Support existing keys/agents and interactive passwords. Prompt for a password
   once and retain it in process memory for reconnection after reboot; never put
   it in command-line arguments, environment variables, files or logs. The exact
   OpenSSH credential-delivery mechanism remains to be designed.
6. SSH host-key changes produce a warning rather than blocking the sequence.
   This accommodates installations using volatile/generated boot-time host keys.
   Retain the USB-route and compatibility checks, but do not describe them as
   proof of cryptographic identity continuity. Unknown keys also warn; record
   fingerprints for the run without modifying persistent known-hosts data.
7. Require unmounted recovery partitions and perform filesystem analysis on host
   copies without device repairs, mounting, service stopping or cache changes.
8. Permit e2fsprogs in the optional verifier with pre-write availability checks,
   keeping ordinary flashing independent of these tools. This requires a scoped
   revision to the documented flasher dependency boundary.
9. Use temporary raw copies plus a private, redacted persistent verification
   report on success or failure. Cleanup removes raw copies during normal exit;
   abrupt termination may leave private files for explicit removal.

## Agreed: Q10–Q15

10. Require exact recovery-rootfs bytes over the reference-defined filesystem
    extent, the exact expected kernel/DTB file set and contents, and successful
    read-only filesystem consistency checks of both acquisitions. Unexpected
    metadata differences are failures, not automatically tolerated exceptions.
11. Warn on first-seen host keys, record first-seen/changed fingerprints, and do
    not prompt or alter the user's normal known-hosts file. Reports distinguish
    compatibility/USB routing from cryptographic identity continuity.
12. Require an explicit SSH account. Default to key/agent authentication, allow
    an explicit private-key path, and offer a password option prompting once.
    Avoid accidental dependence on root's SSH configuration under sudo.
13. Allow up to two minutes for SSH readiness after reboot, with a separate
    generous acquisition deadline. Stop on failed established readback; do not
    automatically restart partition transfers or reuse partial copies.
14. Automatically create a private timestamped evidence directory in the working
    directory. Check writability before writes and save the verification result
    before main-kernel invalidation. A report publication failure blocks that
    transition. Reports do not authorize resumption.
15. Support the optional SSH checks in read-only `plan`: tools, authentication,
    privileges, partition identity/size, mount state and available host storage.
    Repeat prerequisites in `flash` before writes. Preflight does not substitute
    for the full post-write verification gate.

## Agreed: Q16–Q19 and simplicity constraint

16. Bound the full readback-and-analysis phase to 15 minutes, separately from
    the two-minute post-reboot SSH readiness wait. Expiry blocks invalidation.
17. Announce the evidence directory at startup. Leave artifacts surviving abrupt
    termination for explicit removal; do not automatically reuse or delete old
    runs. Document cleanup.
18. Report integrity verification, update-sequence completion and functional
    acceptance as separate evidence levels. A later update failure does not
    erase a passed integrity check or become a successful-flash report.
19. Validate with offline simulations first, then separately authorized read-only
    USB/SSH rehearsal before actual flashing. Existing recovery differences may
    fail the strict comparison; fresh-write equality remains hardware-unvalidated
    until a real update is observed.

Keep the feature small and specific to this supported C100X profile and trusted
devices. Prefer system OpenSSH and existing bundled filesystem tools, a single
optional verification gate, and existing failure handling. Do not expand it into
a generic remote-management, backup/restore or resume framework.

## Agreed: Q20–Q21

20. Require an administrative remote account (UID 0), without remote sudo or
    device permission changes.
21. Run host SSH as the invoking ordinary user and leave evidence owned by that
    user. Use existing unlocked agents for encrypted keys rather than introducing
    key-passphrase caching/unlocking; the single-prompt password mode remains
    available as an alternative.

## Confirmed implementation contract

All interview decisions and the complete design were confirmed. No device write
or hardware-test authorization follows from agreement on the design. Usage is
documented in [FLASHING.md](FLASHING.md#optional-recovery-verification-existing-ssh).

The selected-mode sequence is:

```text
validate package and SSH/tool/storage prerequisites
  -> write recovery filesystem and kernel using the existing vendor flow
  -> verified normal reboot, including existing state-4 requirement
  -> wait for SSH, inspect partition identity and unmounted state
  -> acquire recovery partitions and verify acquisition length/hashes
  -> compare expected filesystem extent and kernel/DTB files; offline fsck
  -> persist verification result
  -> only on success: existing main-kernel clear and remaining update sequence
```

Reference data comes from the already-validated recovery gzip and kernel ZIP
staged for this flash. Check acquisition against an independently repeated
device-side read/hash of the same bytes. No additional stock download, full main
filesystem expansion or new public backup/restore command is required.

Implementation acceptance requires offline tests proving gate ordering and that
every verification failure blocks main-kernel invalidation, including acquisition
length/hash failures, unexpected mount/device identity, comparison/fsck failures,
authentication/timeout/cancellation, and failure to persist the gate result.
Also check disabled-mode behavior, password redaction, host-key warning policy,
private artifact cleanup/ownership, and packaged helper/tool availability.
Update protocol, usage and dependency-boundary documentation with implementation;
record hardware evidence only when observed.

## Research informing later questions

- The gate fits after recovery writes and the existing verified normal reboot,
  before main-kernel invalidation. The running main firmware and its SSH identity
  should still be the previous installation at this point.
- The C100X recovery-rootfs writer streams decompressed image bytes directly to
  its block device. No recovery-rootfs mutation was identified in the inspected
  subsequent normal-boot paths. Exact equality of the freshly written filesystem
  extent is therefore a plausible fail-closed requirement, pending design choice
  and hardware validation.
- The expected filesystem extent is 153600000 bytes; the observed partition has
  another 3686400 bytes outside that extent. The reference must determine the
  comparison length, not an unchecked device superblock.
- Recovery-kernel installation and normal startup can change its filesystem
  metadata. Compare its expected kernel/DTB file set and contents, rather than
  whole-partition equality.
- Prior installed-recovery metadata differences do not establish acceptable
  differences immediately after a fresh rewrite. No automatic tolerance for
  such differences has been agreed.
- Reboot plus repeated reads strengthens acquisition evidence but does not prove
  uncached physical-media reads, power-loss durability or recovery bootability.

System OpenSSH can use a shipped askpass helper with private local IPC to reuse
the in-memory password. Only helper/IPC paths belong in its environment. The
existing builder subprocess/input helpers must not be reused for this purpose:
they can serialize input to temporary files. Transient copies in SSH/helper
memory are expected; no disk-backed password cache is intended.
