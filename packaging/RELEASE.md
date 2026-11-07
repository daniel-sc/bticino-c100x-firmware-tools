**C100X v0.2.0 — OTA flashing over SSH and vendor-update blocking.**
For C100X Door Entry 1.5.8 on Apple Silicon Macs running macOS 15 or later.

- **Wireless OTA flashing over SSH:** run `plan` and `flash --transport ssh` from
  your Mac over the LAN, using existing administrative SSH access. A complete
  hardware run passed recovery integrity verification, all four transfers and
  three reboot transitions, and final destination SSH verification.
- **Vendor updates blocked by default:** newly built firmware suppresses
  manufacturer installation in both main and recovery, preserving owner-controlled
  flashing. Use `--allow-vendor-updates` when building to retain vendor updates.
- **SSH in both environments:** selecting the SSH payload provisions main and
  recovery with shared login settings and a persistent host identity, enabling
  recovery access during wireless updates.
- **Broader hardware compatibility:** accepts the vendor-supported `02.*.*`
  hardware family, with recorded flashing coverage on `02*06*0` and
  community-reported stock-to-modified USB installation on `02*07*0`.
- **Reliable wireless transfers:** waits for FTP startup, refreshes command
  connections after long uploads and handles transient SSH readiness timeouts
  across planned reboots.

The tested wireless image had vendor-update blocking enabled, and the user
confirmed post-flash household tests passed. See
[validation and known limits](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/main/docs/ACCEPTANCE.md)
for the observed scope and remaining coverage.
Updating the Mac tool leaves installed firmware unchanged; rebuild and explicitly
flash to install the new firmware policy and dual-image SSH.

The self-contained DMG is signed and notarized and includes all required tools.
Install with Homebrew:

```sh
brew install --cask daniel-sc/tap/c100x
```

For an existing stable installation, use `brew upgrade --cask daniel-sc/tap/c100x`.
To switch from preview, uninstall `c100x@preview` before installing `c100x`;
keep firmware and private settings outside `/Applications/C100X`.

Or download the DMG below and copy its `C100X` folder into Applications.
Start with the [setup guide](https://github.com/daniel-sc/bticino-c100x-firmware-tools#readme)
and [SSH flashing guide](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/main/docs/FLASHING.md#wireless-updates-over-ssh).
Firmware is not distributed; keep generated images private.
