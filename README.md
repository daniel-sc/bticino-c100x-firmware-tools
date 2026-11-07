# BTicino Classe 100X firmware tools

A command-line tool for building custom firmware images and flashing a
**BTicino Classe 100X (Door Entry), firmware 1.5.8**, from macOS.

Building, a full USB flash, SSH and MQTT/household functions have passed on the
tested installation. See [validation and known limits](docs/ACCEPTANCE.md)
for tested scope and follow-up coverage.

## What's included?

- **Image builder:** download the verified original firmware or use your own
  copy, add features such as SSH or MQTT, and produce a new `.fwz` file.
- **SSH access:** configure administrative access with your public key,
  a password, or both.
- **MQTT bridge:** publish intercom events to your MQTT broker and receive raw
  OpenWebNet commands, with broker settings supplied when building.
- **OTA prevention:** v0.2.0-alpha.1 builds block manufacturer installation in main
  and recovery by default; `--allow-vendor-updates` opts out (hardware validation pending).
- **Device flasher:** inspect an image, check the connected device, and explicitly
  start an update over USB. The prerelease also provides explicit SSH wireless
  transport with mandatory recovery verification (hardware validation pending).
  The stock-device USB workflow does not require SSH.

The tested host is an **Apple Silicon Mac**. Other firmware families and 2.x
firmware are unsupported. Linux/WSL support is planned but not yet validated.
There is no GUI or Home Assistant configuration/discovery integration.

Version **v0.2.0-alpha.1** and source builds accept hardware family **`02.*.*`**,
following the vendor updater's compatibility rule for C100X 1.5.8.
Hardware flashing and household functions have
been tested on **`02*06*0`**; other revisions, including `02*07*0`, have not yet
been flash-validated here. Published v0.1.0 still requires `02*06*0`.

SSH and MQTT are optional. Prerelease SSH provisions both main and recovery;
MQTT applies only to main. Manufacturer-update policy is independent of SSH and
transport. Building creates a file; flashing installs it on the intercom.

**Stable v0.1.0 retains manufacturer updates and main-only SSH.** The
v0.2.0-alpha.1 prerelease includes the new default policy, dual-image SSH and
wireless transport;
see [builder policy](docs/BUILDER.md#ota-prevention) and
[wireless usage](docs/FLASHING.md#wireless-updates-prerelease).

## Installation

With [Homebrew](https://brew.sh), install the signed Apple Silicon stable release:

```sh
brew install --cask daniel-sc/tap/c100x
c100x --version
```

For prereleases, use `brew install --cask daniel-sc/tap/c100x@preview` instead.

This installs the complete bundle into `/Applications/C100X` and puts `c100x` on
PATH. Requires **macOS 15.0 or later**.

### Direct download (no Homebrew required)

Download the Apple Silicon DMG from [Releases](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases).
Copy the entire `C100X` folder to `/Applications` (or `~/Applications` for a
per-user installation). The DMG includes an Applications shortcut for
drag-and-drop installation. Eject the DMG after copying. Keep `c100x` and `support`
together. The release includes Python and all required tools;
**no Homebrew, mise, Xcode or MyHOME installation is needed**.
Get the [v0.2.0-alpha.1 prerelease](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.2.0-alpha.1)
for the features documented here, or [stable v0.1.0](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.1.0)
for the previously validated USB-only feature set. New prerelease hardware coverage
is described in [validation and known limits](docs/ACCEPTANCE.md).
Each release's `release.json` records its minimum macOS version.

Open Terminal and check the installed version:

```sh
/Applications/C100X/c100x --version
```

For a per-user installation, use `~/Applications/C100X/c100x` instead. Keep your
firmware and private settings outside the installation folder.

## Build and install firmware

1. [Build firmware](docs/BUILDER.md): choose [SSH access](docs/BUILDER.md#ssh-access)
   and/or [MQTT](docs/BUILDER.md#mqtt-bridge), review the
   [update policy](docs/BUILDER.md#ota-prevention), and create a checked `.fwz` image.
2. [Flash firmware](docs/FLASHING.md): connect by USB, run read-only preflight,
   explicitly flash, then check the intercom's functions.

Already have a compatible image? Start with the flashing guide. USB networking
is managed automatically. Building runs as your normal user; device checks and
USB flashing use `sudo`; wireless commands run without it. Keep generated
images private: they can contain credentials.

## Updating the Mac tool

Finish any running build or flash first. For a Homebrew installation:

```sh
brew upgrade --cask daniel-sc/tap/c100x
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

## License

Project code is [MIT-licensed](LICENSE). Manufacturer firmware and external
dependencies retain their own licenses; firmware is not included in this repository.
