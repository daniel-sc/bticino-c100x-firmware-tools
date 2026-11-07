Prerelease for **C100X Door Entry 1.5.8**, on Apple Silicon Macs running macOS 15
or later. Changes since v0.1.0:

- **Broader hardware compatibility:** accepts hardware family `02.*.*`, including
  `02*07*0`, following the vendor updater's rule ([#6](https://github.com/daniel-sc/bticino-c100x-firmware-tools/issues/6)).
  Recorded flash and household acceptance remains on `02*06*0`.
- **Wireless updates:** `plan` and `flash --transport ssh` use existing
  administrative SSH access, with phase-specific host identity checks and mandatory
  recovery integrity verification. First installation on a stock device still uses USB.
- **SSH in main and recovery:** selecting the SSH payload now provisions both
  environments with shared owner credentials and a persistent host identity.
- **Manufacturer updates blocked by default:** new builds apply OTA prevention in
  main and recovery, including builds with no optional payloads. Add
  `--allow-vendor-updates` to retain manufacturer updates.

Wireless operation, dual-image changes and flashing on additional hardware
revisions have offline coverage but still need hardware acceptance. See the
[validation record](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/v0.2.0-alpha.1/docs/ACCEPTANCE.md)
for tested scope; existing installations change only when explicitly flashed.

The self-contained DMG is signed and notarized and includes all required tools.
Install with Homebrew:

```sh
brew install --cask daniel-sc/tap/c100x
```

Or download the DMG below and copy its `C100X` folder into Applications.
Start with the [setup guide](https://github.com/daniel-sc/bticino-c100x-firmware-tools#readme);
see [validation and known limits](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/v0.2.0-alpha.1/docs/ACCEPTANCE.md)
for tested coverage. Firmware is not distributed; keep generated images private.
