# BTicino Classe 100X firmware tools

A command-line tool for building custom firmware images and flashing a
**BTicino Classe 100X (Door Entry), firmware 1.5.8**, from macOS.

**Experimental:** image building, USB preflight and one recovery-assisted native
installation have passed. An uninterrupted full flash with the latest transport
fix and detailed SSH/MQTT/household checks remain pending. See the
[validation record](docs/ACCEPTANCE.md).

## What's included?

- **Image builder:** download the verified original firmware or use your own
  copy, add features such as SSH or MQTT, and produce a new `.fwz` file.
- **SSH access:** configure administrative access with your public key,
  a password, or both.
- **MQTT bridge:** publish intercom events to your MQTT broker and receive raw
  OpenWebNet commands, with broker settings supplied when building.
- **Device flasher:** inspect an image, check the connected device, and explicitly
  start an update over USB. The stock-device flashing workflow does not require SSH.

The tested host is an **Apple Silicon Mac**. Other firmware families and 2.x
firmware are unsupported. Linux/WSL support is planned but not yet validated.
There is no GUI or Home Assistant configuration/discovery integration.

SSH and MQTT are independently optional and can be combined. Building creates a
file on your Mac; flashing installs that file on the intercom.

## Installation

Download the Apple Silicon DMG from [Releases](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases).
Copy the entire `C100X` folder to `/Applications` (or `~/Applications` for a
per-user installation). The DMG includes an Applications shortcut for
drag-and-drop installation. Eject the DMG after copying. Keep `c100x` and `support`
together. The release includes Python and all required tools;
**no Homebrew, mise, Xcode or MyHOME installation is needed**.
[v0.1.0-alpha.4](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.1.0-alpha.4)
is signed and notarized and requires **macOS 15.0 or later** on Apple Silicon.
Each release's `release.json` records its minimum macOS version.
Homebrew installation of `c100x` is not available yet; use the DMG.

Open Terminal and check the installed version:

```sh
/Applications/C100X/c100x --version
```

For a per-user installation, use `~/Applications/C100X/c100x` instead. Keep your
firmware and private settings outside the installation folder.

## Build and install firmware

1. [Build firmware](docs/BUILDER.md): choose [SSH access](docs/BUILDER.md#ssh-access),
   [MQTT](docs/BUILDER.md#mqtt-bridge), or both, and create a checked `.fwz` image.
2. [Flash firmware](docs/FLASHING.md): connect by USB, run read-only preflight,
   explicitly flash, then check the intercom's functions.

Already have a compatible image? Start with the flashing guide. USB networking
is managed automatically. Building runs as your normal user; device checks and
flashing use `sudo`. Keep generated images private: they can contain credentials.

## Updating the Mac tool

Finish any running build or flash, download the newer DMG, and replace the entire
installed `C100X` folder. Keep firmware and private settings outside that folder.
Check the version with `/Applications/C100X/c100x --version`.

Updating the Mac tool leaves the intercom unchanged. To update its SSH/MQTT
features, rebuild from stock with your settings and flash the new image.

## Advanced use and development

- [Custom payloads and builder reference](docs/BUILDER-REFERENCE.md): add your own
  files or services. These instructions run on your Mac; use only trusted sources.
- [Run from source and test](docs/SOURCE.md).
- [Architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md),
  [protocol evidence](docs/PROTOCOL.md), and [release packaging](docs/RELEASING.md).

## License

Project code is [MIT-licensed](LICENSE). Manufacturer firmware and external
dependencies retain their own licenses; firmware is not included in this repository.
