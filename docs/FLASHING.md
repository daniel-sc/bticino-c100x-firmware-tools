# Flashing from macOS

The bundled CLI manages USB networking and the researched OpenWebNet/FTP update
flow in one terminal. **Alpha status:** native read-only USB checks passed in the
earlier two-terminal workflow. Automatic session management is covered offline;
FTP transfer, recovery-mode networking and full flashing still need hardware
validation. See [ACCEPTANCE.md](ACCEPTANCE.md).

## Compatibility

The target is **C100X Door Entry 1.5.8**, hardware `02*06*0`, object model `1.0.99`,
initial status `4*0`. Firmware must retain the stock manifest, recovery and kernel
and match the main-filesystem profile. These checks establish package
compatibility, not bootability. The release manifest declares the minimum macOS
version; the downloadable bundle is for Apple Silicon.

## Download, inspect and flash

Download the DMG from [Releases](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases)
and copy the `C100X` folder into a writable location. Keep the executable and its support
folder together. No separate runtime, driver installation or MyHOME installer is
needed. C100X profile provenance is recorded in [PROTOCOL.md](PROTOCOL.md).

In a terminal in that folder:

```sh
./c100x inspect-fw /path/to/custom.fwz
```

Connect the powered intercom by USB, then run the read-only preflight:

```sh
sudo ./c100x plan /path/to/custom.fwz
```

The command validates the image, starts the bundled USB helper, configures the
reported feth interface, verifies the route to `192.168.129.1`, and checks device
identity/status. It shuts down its helper on exit. Root is needed for macOS
feth/BPF networking; image building should run without sudo.

To explicitly write firmware:

```sh
sudo ./c100x flash /path/to/custom.fwz
```

This runs the same preflight and then performs all four payload writes and three
reboot transitions. The helper stays alive through reconnects and configures each
new interface; network operations check the managed USB route. No second terminal
or manual `ifconfig`/route setup is required.

Keep the Mac awake, USB connected and device power stable throughout flashing.
The intercom's `C100X` storage volume is separate from USB networking; firmware
is not copied to that volume. Eject it before an idle physical disconnect.

The sequence is recovery filesystem/kernel → reboot normal → clear main kernel →
reboot recovery → main filesystem/kernel → reboot normal. Each payload is uploaded
and committed separately. On error, keep the device powered and record the stage.
The CLI stops subsequent actions; it does not retry uncertain writes, resume a
partial update or reboot as cleanup. Cleanup only closes local resources.

After protocol completion, test calls, audio/video, door release and payload
behavior. For SSH, test each configured authentication method and host identity
across a normal reboot. An ACK or completed sequence is not functional acceptance.

Stock restoration through Windows first is an acceptance-test choice, not a
protocol prerequisite. See [ADR-006](DECISIONS.md#adr-006-separate-direct-re-flash-testing-from-stock-device-acceptance).

## Development from source

Source builds require Homebrew and Xcode Command Line Tools (C++ compiler/macOS
SDK for TetherKit; full Xcode is not required). Install the command-line tools with
`xcode-select --install` if needed, then from the repository root:

```sh
brew install mise libusb pkgconf
mise trust
mise install python cmake
git clone https://github.com/XiaoMiku01/TetherKit.git research/TetherKit
git -C research/TetherKit checkout --detach 1ded051fd243c547fd6e250a898f0164cc30561d
mise run transport-build
mise run test
mise exec -- ctest --test-dir .local/tetherkit-build --output-on-failure
sudo "$(mise which python)" -m classe100x plan /path/to/custom.fwz
```

For debugging an independently supervised transport, run
`sudo "$(mise which python)" -m classe100x usb` in one terminal, then use
`mise exec -- python -m classe100x plan /path/to/custom.fwz --external-usb` in another.
With `--external-usb`, the caller owns transport lifetime and route verification;
this advanced mode does not start or clean up the existing helper. `probe` also
uses an existing network connection and supports the research SSH tunnel.

## Further reference

- [Protocol](PROTOCOL.md): exact commands and evidence.
- [Acceptance](ACCEPTANCE.md): observed results and pending hardware work.
- [Operations](OPERATIONS.md): maintainer research and private backups.
- [Releasing](RELEASING.md): CI packaging, signing and dependency sources.
