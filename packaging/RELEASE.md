Prerelease for **C100X Door Entry 1.5.8**, on Apple Silicon Macs running macOS 15
or later. Changes since v0.2.0-alpha.1:

- **FTP startup:** fixes the early `EOFError` when wireless flashing connects before
  the device's FTP server is ready. Connection setup now waits for its greeting.
- **Slow uploads:** refreshes the command connection after each upload so the
  device's idle timeout does not break the following firmware-write request.
- **SSH reconnection:** transient local SSH-control check timeouts now participate
  in readiness polling instead of immediately aborting a planned reboot transition.

These are Mac-tool fixes; existing firmware images do not need rebuilding.

Established USB and main-system functional evidence carries forward for unchanged
behavior. Wireless transport, customized recovery and OTA prevention still need
targeted hardware acceptance. See the
[validation record](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/main/docs/ACCEPTANCE.md)
for tested scope; existing installations change only when explicitly flashed.

The self-contained DMG is signed and notarized and includes all required tools.
Install with Homebrew:

```sh
brew install --cask daniel-sc/tap/c100x@preview
```

Or download the DMG below and copy its `C100X` folder into Applications.
Start with the [setup guide](https://github.com/daniel-sc/bticino-c100x-firmware-tools#readme);
see [validation and known limits](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/main/docs/ACCEPTANCE.md)
for tested coverage. Firmware is not distributed; keep generated images private.
