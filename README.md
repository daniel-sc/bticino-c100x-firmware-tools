# BTicino Classe 100X firmware tools

A command-line tool for building custom firmware images and flashing a
**BTicino Classe 100X (Door Entry), firmware 1.5.8**, from macOS or Linux.

**v0.2.0 adds owner-controlled OTA flashing over SSH and blocks vendor updates
by default in built firmware.** Full USB and SSH flash sequences and post-flash
household tests have passed; see [validation and known limits](docs/ACCEPTANCE.md)
for hardware evidence and functional coverage.

## What's included?

- **Image builder:** download the verified original firmware or use your own
  copy, add features such as SSH or MQTT, and produce a new `.fwz` file.
- **SSH access:** configure administrative access with your public key,
  a password, or both.
- **MQTT bridge:** publish intercom events to your MQTT broker and receive raw
  OpenWebNet commands, with broker settings supplied when building.
- **Vendor-update blocking:** builds block manufacturer installation in main
  and recovery by default; `--allow-vendor-updates` opts out.
- **Device flasher:** inspect an image, check the connected device, and explicitly
  start an update over USB or wirelessly over SSH. SSH flashing includes mandatory
  recovery integrity verification and final SSH verification.
  The stock-device USB workflow does not require SSH.

USB flashing is hardware-validated on macOS; current source adds **experimental
Ubuntu 24.04/26.04 Desktop USB**. Firmware building and SSH updates also run on
[Linux](docs/LINUX.md), with limited hardware validation. Release bundles target
**Apple Silicon Macs** and **x86-64 Linux**. Other firmware families and
2.x firmware are unsupported.
There is no GUI or Home Assistant configuration/discovery integration.

The tool accepts hardware family **`02.*.*`**,
following the vendor updater's compatibility rule for C100X 1.5.8.
Hardware results cover **`02*06*0`** and a community-reported stock-to-modified
installation on **`02*07*0`**. Evidence carries forward for unchanged behavior.

SSH and MQTT are optional. Selecting SSH provisions both main and recovery;
MQTT applies only to main. Manufacturer-update policy is independent of SSH and
transport. Building creates a file; flashing installs it on the intercom.

See [builder policy](docs/BUILDER.md#ota-prevention) and
[wireless usage](docs/FLASHING.md#wireless-updates-over-ssh).

## Installation

### macOS

With [Homebrew](https://brew.sh), install the signed Apple Silicon stable release:

```sh
brew install --cask daniel-sc/tap/c100x
c100x --version
```

For prereleases, use `brew install --cask daniel-sc/tap/c100x@preview` instead.

This installs the complete bundle into `/Applications/C100X` and puts `c100x` on
PATH. Requires **macOS 15.0 or later**.

#### Direct download (no Homebrew required)

Download the Apple Silicon DMG from [v0.2.0](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.2.0).
Copy the entire `C100X` folder to `/Applications` (or `~/Applications` for a
per-user installation). The DMG includes an Applications shortcut for
drag-and-drop installation. Eject the DMG after copying. Keep `c100x` and `support`
together. The release includes Python and all required tools;
**no Homebrew, mise, Xcode or MyHOME installation is needed**.
These instructions describe **v0.2.0**. Hardware coverage is described in
[validation and known limits](docs/ACCEPTANCE.md).
Each release's `release.json` records its minimum macOS version.

Open Terminal and check the installed version:

```sh
/Applications/C100X/c100x --version
```

For a per-user installation, use `~/Applications/C100X/c100x` instead. Keep your
firmware and private settings outside the installation folder.

### Linux

Download the `c100x-<version>-linux-x86_64.tar.gz` bundle from
[releases](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases), then:

```sh
tar -xzf c100x-*-linux-x86_64.tar.gz
./C100X/c100x --version
```

Requires x86-64 Linux with glibc 2.39+ (for example Ubuntu 24.04), OpenSSH client
and CA certificates. Python and builder tools are included. Keep `c100x` and
`support` together. Use `--transport ssh` for wireless flashing. Current source
also offers experimental native USB on Ubuntu 24.04/26.04 Desktop with NetworkManager;
check the bundle's release notes before using that path.
See [Linux usage](docs/LINUX.md).

## Build and install firmware

1. [Build firmware](docs/BUILDER.md): choose [SSH access](docs/BUILDER.md#ssh-access)
   and/or [MQTT](docs/BUILDER.md#mqtt-bridge), review the
   [update policy](docs/BUILDER.md#ota-prevention), and create a checked `.fwz` image.
2. [Flash firmware](docs/FLASHING.md): connect by USB or use
   [SSH over your LAN](docs/FLASHING.md#wireless-updates-over-ssh), run read-only
   preflight, explicitly flash, then check the intercom's functions.

Already have a compatible image? Start with the flashing guide. USB networking
is managed automatically. Building runs as your normal user; device checks and
USB flashing use `sudo`; wireless commands run without it. Keep generated
images private: they can contain credentials.

## Updating the Mac tool

Finish any running build or flash first. For a Homebrew installation:

```sh
brew upgrade --cask daniel-sc/tap/c100x
```

To switch from the preview channel to stable:

```sh
brew uninstall --cask c100x@preview
brew install --cask daniel-sc/tap/c100x
```

For a direct installation, download the newer DMG and replace the entire installed
`C100X` folder. Keep firmware and private settings outside that folder.
Check the version with `/Applications/C100X/c100x --version`.

Updating the Mac tool leaves the intercom unchanged. To update its SSH/MQTT
features, rebuild from stock with your settings and flash the new image.

## Error diagnostics

Errors identify the failed operation. Add `--debug` for a traceback:

```sh
c100x --debug inspect-fw custom.fwz
```

Review output and reports before sharing: they retain paths, usernames and tool
messages, with known passwords removed. A failed build can create the requested
`--report` file; use a new report path for the next attempt. See the
[diagnostic details](docs/BUILDER-REFERENCE.md#publication-and-failure-handling).

## Advanced use and development

- [Custom payloads and builder reference](docs/BUILDER-REFERENCE.md): add your own
  files or services. These instructions run on your Mac; use only trusted sources.
- [Run from source and test](docs/SOURCE.md).
- [Architecture](docs/ARCHITECTURE.md), [decisions](docs/DECISIONS.md),
  [protocol evidence](docs/PROTOCOL.md), and [release packaging](docs/RELEASING.md).

## Useful links and related work

Thanks to the authors and contributors of the community projects below for the
research and tools on which this project is partly based.

- [bticinoClasse300x](https://github.com/fquinto/bticinoClasse300x) provides community firmware tools and research, currently focused on Classe 300X, with legacy C100X material.
- [c300x-controller](https://github.com/slyoldfox/c300x-controller) adds intercom APIs, MQTT events, WebRTC and HomeKit support to rooted devices.
- [BTicino Telegram community](https://t.me/bTicinoClasse300x) discusses Classe 300X and other intercom integrations, including Home Assistant.
- [BTicino software and firmware](https://www.bticino.com/tools/product-software-and-firmware/home-systems) points to official downloads, including MyHOME Suite.
- [Classe 100X generation guide](https://assets.legrand.com/pim/AUTRE/Classe100X_README_v1.pdf) explains how to distinguish Door Entry and Home + Security models and their incompatible firmware.

## License

Project code is [MIT-licensed](LICENSE). Manufacturer firmware and external
dependencies retain their own licenses; firmware is not included in this repository.
