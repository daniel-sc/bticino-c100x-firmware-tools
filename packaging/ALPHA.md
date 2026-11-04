Self-contained builder and flasher for **Apple Silicon macOS**. See `release.json`
for the artifact's minimum macOS version, bundled tool versions and source hashes.

Start with `README.md` in the downloaded `C100X` folder for installation and links
to the build/flash guides. [Current online overview](https://github.com/daniel-sc/bticino-c100x-firmware-tools#readme).
No Homebrew, Python, Xcode or MyHOME setup is required.

**New in alpha.6:** SSH payload v2 owns its service lifecycle. The vendor daemon
could stop the previous SSH service during boot when persistent `abil_ssh` was
absent or zero. The new image disables that vendor init control path and installs
`c100x-ssh` with its own configuration, PID file and startup/shutdown links.
It reuses stock Dropbear, existing authentication options and a fresh persistent
host key; it does not change the device's configuration/data partition.

Manage SSH through `/etc/init.d/c100x-ssh start|stop|restart|status`. Vendor SSH
start/stop calls are no-ops for this image. Key-only builds disable password
authentication. This change requires **rebuilding and flashing** your firmware;
upgrading the Mac CLI alone does not repair an installed image.

Two independent fresh reviews found no actionable issues. All 187 offline tests
passed, including lifecycle and payload-composition checks, and a real pinned-stock
SSH build passed final archive verification. Fresh-image hardware acceptance is
still pending. See the SSH lifecycle verification section in `docs/FLASHING.md`.

Includes alpha.5's original-error/tool diagnostics, `--debug` tracebacks and saved
failure evidence. Review reports before sharing; generated firmware remains private.

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
