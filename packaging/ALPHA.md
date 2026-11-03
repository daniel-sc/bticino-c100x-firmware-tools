Self-contained builder and flasher for **Apple Silicon macOS**. See `release.json`
for the artifact's minimum macOS version, bundled tool versions and source hashes.

Start with `README.md` in the downloaded `C100X` folder for installation and links
to the build/flash guides. [Current online overview](https://github.com/daniel-sc/bticino-c100x-firmware-tools#readme).
No Homebrew, Python, Xcode or MyHOME setup is required.

**New in alpha.4:** managed USB networking follows the device between normal-mode
RNDIS (USB helper) and recovery-mode native ECM. This fixes a feth-only assumption
that can stop alpha.3 at `entering recovery: rebooting` despite recovery booting.
The old helper is stopped before ECM takes over; cancellation during that teardown
finishes worker cleanup before returning. Reboot identity/uptime and route checks
remain required, with no automatic device-write retries.

New `plan-recovery` and `recover` commands can explicitly install main firmware
from matching idle recovery state after assessment of a stopped update. See
`docs/FLASHING.md`; these are not generic resume or uncertain-write retry commands.
Existing SSH verification and optional SSH/MQTT builder payloads remain available.

Fixes #1: before planned reboots, a bounded best-effort `diskutil` unmount targets
only storage identified beneath the C100X USB hardware. Ambiguous matches or
failures warn without aborting the firmware sequence solely for that host step.
No forced unmount/ejection or persistent host settings; preflight remains read-only.
Notification suppression and preserved networking after idle unmount still need
hardware confirmation.

**Experimental alpha:** release CI requires offline tests and relocated packaged
smoke checks, including simulated USB handover and recovery installation. One
stopped hardware flash passed recovery SSH integrity verification, then completed
main installation and verified normal boot using the recovery-entry command.
An uninterrupted full flash with this transport fix and detailed SSH/MQTT/household
functional acceptance remain pending. Version 1 waits for hardware validation.

The DMG is Developer ID signed, notarized and stapled. Dependency sources and
build recipes are supplied alongside it; firmware and user credentials are not
distributed. Keep generated firmware private.
