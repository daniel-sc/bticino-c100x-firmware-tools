Self-contained builder and flasher for **Apple Silicon macOS**. See `release.json`
for the artifact's minimum macOS version, bundled tool versions and source hashes.

Start with `README.md` in the downloaded `C100X` folder for installation and links
to the build/flash guides. [Current online overview](https://github.com/daniel-sc/bticino-c100x-firmware-tools#readme).
No Homebrew, Python, Xcode or MyHOME setup is required.

**New in alpha.5:** richer failure diagnostics throughout SSH/recovery verification,
USB networking, FTP/flashing, firmware validation/downloads and builder tools/hooks.
Errors retain original causes, operation/stage, exit status and bounded tool output.
`--debug` adds Python stack traces; unexpected programming errors show them directly.
Recovery failure reports and explicitly requested build failure reports retain
exception chains and stacks even without `--debug`. Existing reports are never
overwritten; choose a new build-report path for another attempt.

SSH preflight identifies the failed prerequisite, and SSH/reboot readiness timeouts
retain their final failure or observation. Managed USB failures include recent
helper output. Paths, usernames and original messages remain useful; known secret
values are removed. Review diagnostics before sharing. This release improves
evidence capture but does not establish the cause of the previously reported live
SSH preflight failures.

Includes alpha.4's ECM/RNDIS handover, explicit `plan-recovery`/`recover` commands,
and best-effort storage unmount before planned reboots. Device-write ordering,
reboot-proof checks and the no-uncertain-write-retry policy remain unchanged.
See `docs/FLASHING.md` for usage; firmware is still built and flashed separately.

**Experimental alpha:** release CI requires offline tests and relocated packaged
smoke checks, including simulated USB handover and recovery installation. One
stopped hardware flash passed recovery SSH integrity verification, then completed
main installation and verified normal boot using the recovery-entry command.
An uninterrupted full flash with this transport fix and detailed SSH/MQTT/household
functional acceptance remain pending. Version 1 waits for hardware validation.

The DMG is Developer ID signed, notarized and stapled. Dependency sources and
build recipes are supplied alongside it; firmware and user credentials are not
distributed. Keep generated firmware private.
