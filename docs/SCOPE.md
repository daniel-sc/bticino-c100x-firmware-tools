# Native macOS Classe 100X flashing

## Goal

Flash an existing, previously Windows-tested modified C100X 1.5.8 `.fwz`
from an Apple Silicon Mac onto stock firmware, without SSH. A CLI and
Homebrew system libraries are acceptable. Manage project tools with mise.
Firmware creation and Home Assistant design are outside this project.

SSH on the currently modified intercom is available for read-only research.
USB access requires manual setup and is only occasionally available.

## Acceptance

1. Verify connectivity and the update sequence as far as possible without writes.
2. With the previously used Windows flasher available, restore official 1.5.8
   using that established method.
3. Flash the selected modified image from macOS, starting from stock, without SSH.
4. Check calls, audio/video, door release, and restored SSH.
5. Deliver a repeatable command, compatibility checks, useful errors/logging,
   and handling for expected disconnects and reboots.

Exercise failures in simulation; never intentionally interrupt a firmware write.
Windows availability does not guarantee recovery from every failure.

## Selected image

User confirmed `NEW_c100x_1.5.8_MQTT_20251106_205901.fwz`.

- SHA-256: `67848425d6ec5a251ff8362394dad052737f42eb8326cdc8333038d7ede22abc`
- Size: 106895070 bytes.
- Original stock `c100x_1.5.8.fwz` SHA-256:
  `bca0dd7e407c2406d6f8c696f0a9e50bc1e795c8e4700c89e83f09ff96c3efb2`.
- Original images remain in the user's backup directory and are never modified.

## Protocol evidence

Use device binaries/scripts, stock firmware, and MyHOME Suite analysis to
establish commands. Upstream diagrams are leads, not a protocol specification.
Do not guess write parameters or substitute direct partition writes.

Current upstream `fquinto/bticinoClasse300x` was checked at
`55d2dab9538e8c89e6c3efd559845c344b910327`; no `flasher/` implementation exists
there. Legacy C100X support does exist.

## Environment observed

- Mac: macOS 27.0.1 (26A434), arm64, Xcode command-line tools installed.
- Device: Linux 4.9.11+imx+, armv7l; board string
  `BTicino SHARK board (Dig-2/Car-6)`, CPU revision `0206`.
- Installed firmware metadata: 1.5.8. Root filesystem mounted read-only.
- SSH research uses a user-opened multiplexed connection; no password is stored.
- USB has not yet been connected or tested in this workspace.

## Current validation status

Implemented the `usb`, `probe`, `inspect-fw`, `plan` and `flash` CLI commands.
The established BTESUXP sequence is recovery filesystem/kernel → reboot normal
→ clear main kernel → reboot recovery → main filesystem/kernel → reboot normal.
See [PROTOCOL.md](PROTOCOL.md) for evidence and completion limitations.

The selected archive has been fully validated. The read-only identity probe,
including uptime and normalized object model, has succeeded through the existing
research SSH tunnel. All 36 Python tests pass, including simulated per-step
disconnects, lost commit ACK, FTP failures, reboot verification and USB helper
cleanup. The pinned TetherKit build passed 23 CTest entries; privileged/C100X
hardware coverage is still pending.

No firmware-write commands have been sent to the real device. Native USB
preflight, stock restoration and macOS stock-to-modified flashing still require
physical access. Track these in [ACCEPTANCE.md](ACCEPTANCE.md).
