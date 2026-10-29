# BTicino Classe 100X firmware tools

A command-line tool for building custom firmware images and flashing a
**BTicino Classe 100X (Door Entry), firmware 1.5.8**, from macOS.

**Experimental:** image building and read-only USB preflight have passed local
validation. Full native flashing and the generated images' boot/SSH behavior
still need hardware testing. See the [validation record](docs/ACCEPTANCE.md).

## What's included?

- **Image builder:** download the verified original firmware or use your own
  copy, apply selected payloads, and produce a new `.fwz` file.
- **Bundled SSH payload:** configure administrative access with your public key,
  a password, or both. A binary/config/service example helps you add other payloads.
- **Device flasher:** inspect an image, check the connected device, and explicitly
  start an update over USB. The stock-device flashing workflow does not require SSH.

The tested host is an **Apple Silicon Mac**. Other firmware families and 2.x
firmware are unsupported. Linux/WSL support is planned but not yet validated.
There is no GUI or ready-made MQTT/Home Assistant integration.

## Quick start: download and build

Download the Apple Silicon DMG from [Releases](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases).
Copy the `C100X` folder into a writable location and open a terminal there. Keep `c100x`
and `support` together. The release includes Python and all required tools;
**no Homebrew, mise, Xcode or MyHOME installation is needed**.
[v0.1.0-alpha.1](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.1.0-alpha.1)
is signed and notarized and requires **macOS 15.0 or later** on Apple Silicon.
Each release's `release.json` records its minimum macOS version.

```sh
./c100x builder-doctor
./c100x build-fw --stock c100x-1.5.8 --payload ssh --ssh-password \
  --output custom.fwz --report custom.build.json
```

Enter the new SSH password when prompted. The account will be `root2`. The tool
downloads and verifies stock firmware, works on a private copy, and checks the
finished image. Keep `custom.fwz` private: it contains SSH credentials and a host
private key. `custom.build.json` is a redacted report of offline checks.

Build as your ordinary user. To check and then explicitly flash a connected device:

```sh
sudo ./c100x plan custom.fwz
sudo ./c100x flash custom.fwz
```

USB networking is started, maintained across reboots, and cleaned up automatically.
`plan` performs read-only device checks; `flash` writes firmware. See the
[flashing guide](docs/FLASHING.md) for device compatibility and acceptance details.

**Building and flashing are separate operations.** Existing outputs are never
overwritten. Alpha downloads precede full hardware acceptance; v1 will follow
successful native flashing and functional validation.

## Run from source

You need [Homebrew](https://brew.sh) and at least
**4 GiB of free disk space**. Clone or download this repository, then open a
terminal in its root directory—the folder containing `mise.toml`.

Xcode Command Line Tools are needed when compiling the USB helper for flashing;
the builder quick start uses prebuilt tools on Apple Silicon.

```sh
brew install mise e2fsprogs dropbear openssl
mise trust
mise install python 7zip
mise exec -- python -m classe100x builder-doctor
```

```sh
mise exec -- python -m classe100x build-fw --stock c100x-1.5.8 \
  --payload ssh --ssh-password \
  --output .local/custom.fwz --report .local/custom.build.json
```

Prefer public-key login or an offline build? See the
[builder guide](docs/BUILDER.md). Stock Dropbear supports ECDSA P-256 keys;
RSA keys need a legacy client option, and Ed25519 keys are unsupported.

## What next?

| Goal | Guide |
| --- | --- |
| Use your own firmware file, choose SSH authentication, or inspect a build | [Builder usage](docs/BUILDER.md) |
| Add scripts, binaries or configuration through a local payload | [Payload authoring](docs/BUILDER.md#authoring-trusted-payloads) |
| Set up USB, run read-only checks, or flash an image | [Flashing guide](docs/FLASHING.md) |
| Check what has actually been tested | [Validation and remaining hardware work](docs/ACCEPTANCE.md) |

Only use payloads you trust: their commands and Python scripts run with your
host-user permissions.

## Development

```sh
mise run test
```

Tests use simulated devices and synthetic filesystems; no intercom or root access
is required. Builder integration tests run when their tools are installed.

For implementation details, see the [architecture](docs/ARCHITECTURE.md),
[design decisions](docs/DECISIONS.md), and [protocol evidence](docs/PROTOCOL.md).
Run `mise exec -- python -m classe100x --help` for the command list.
Release packaging and signing are documented in [RELEASING.md](docs/RELEASING.md).

## License

Project code is [MIT-licensed](LICENSE). Manufacturer firmware and external
dependencies retain their own licenses; firmware is not included in this repository.
