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

Before clearing the main kernel, the normal-reboot status check reflects stock
firmware's installed recovery `uImage` CRC check on ordinary non-NFS boots. It
does **not** verify the installed recovery filesystem or device-tree files. Full
readback is available through the optional SSH check below; stock USB update
services alone do not provide it. Details are in [PROTOCOL.md](PROTOCOL.md).

After protocol completion, test calls, audio/video, door release and payload
behavior. For SSH, test each configured authentication method and host identity
across a normal reboot. An ACK or completed sequence is not functional acceptance.

Stock restoration through Windows first is an acceptance-test choice, not a
protocol prerequisite. See [ADR-006](DECISIONS.md#adr-006-separate-direct-re-flash-testing-from-stock-device-acceptance).

## Optional recovery verification (existing SSH)

If the **currently installed firmware** already has SSH enabled, add the same
options to `plan` and `flash`. For the usual administrative `root2` account:

```sh
sudo ./c100x plan custom.fwz --verify-recovery-ssh --ssh-user root2 --ssh-password
sudo ./c100x flash custom.fwz --verify-recovery-ssh --ssh-user root2 --ssh-password
```

Each command prompts once. The password stays in memory and is reused after the
normal reboot. SSH uses the managed USB connection, not a LAN alias. Incoming
firmware that enables SSH cannot provide this access yet.

`plan` checks prerequisites without firmware writes. During `flash`, the extra
check runs **after writing recovery and rebooting normally, before clearing the
main kernel**. It compares the recovery filesystem and kernel/DTB contents with
stock and checks the copied filesystems offline. Failure or uncertainty stops
the update. This verifies integrity, not recovery bootability or household
functions. USB/SSH hardware validation of this new feature remains pending.

- Allow several extra minutes and **512 MiB** of free space. SSH readiness is
  limited to two minutes; readback/analysis to fifteen minutes. Failed acquisitions
  are not retried.
- For keys, omit `--ssh-password`; optionally supply `--ssh-key /path/to/key`.
  Encrypted keys must already be unlocked in your agent. If sudo removes the agent
  socket, use `sudo --preserve-env=SSH_AUTH_SOCK ...`. ECDSA P-256 is recommended;
  legacy RSA host/login signatures are enabled only for this connection. Ed25519 is not
  supported by stock Dropbear.
- SSH host keys may change on older installations. First-seen/changed fingerprints
  produce warnings and are recorded, without changing your `known_hosts` file.
  This policy does not prove cryptographic identity continuity.
- A private `c100x-verification-<timestamp>-.../report.json` is saved in the working
  directory, owned by your ordinary user. Raw copies are removed on normal exit.
  After an abrupt kill/power loss, remove any leftover `raw/` directory explicitly;
  it can contain private firmware. Reports never authorize resuming a flash.

Use `sudo` from your ordinary account and an administrative device account (UID
0). This mode requires managed USB, so it cannot be combined with `--external-usb`.
Release bundles include the filesystem tools; source users need e2fsprogs.

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
- [Boot fallback and rescue evidence](RECOVERY.md): what recovery covers and the
  remaining serial/ROM rescue gaps.
- [Operations](OPERATIONS.md): maintainer research and private backups.
- [Releasing](RELEASING.md): CI packaging, signing and dependency sources.
