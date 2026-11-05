First stable release of the **BTicino Classe 100X firmware tools** for Apple
Silicon Macs running macOS 15 or later, supporting **C100X Door Entry 1.5.8**.

Build firmware with optional SSH access and an MQTT bridge, then install it over
USB with automatic networking and read-only preflight. Building and flashing are
separate commands; flashing a stock device does not require SSH.

The self-contained DMG is signed and notarized and includes all required tools.
Install with Homebrew:

```sh
brew install --cask daniel-sc/tap/c100x
```

Or download the DMG below and copy its `C100X` folder into Applications.
Start with the [setup guide](https://github.com/daniel-sc/bticino-c100x-firmware-tools#readme);
see [validation and known limits](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/v0.1.0/docs/ACCEPTANCE.md)
for tested coverage. Firmware is not distributed; keep generated images private.
