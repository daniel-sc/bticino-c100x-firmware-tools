# Flashing from macOS

The CLI uses TetherKit for USB networking and the device's researched
OpenWebNet/FTP update flow. Building an image and flashing one are independent:
the flasher accepts a compatible externally produced FWZ and does not require
e2fsprogs, SSH access or a build report.

**Current status:** native read-only USB preflight passed. FTP transfer,
recovery-mode networking and actual flashing remain unverified. Generated-image
boot and SSH behavior also need hardware acceptance. Read the
[validation record](ACCEPTANCE.md) before undertaking a write.

## Compatibility

The supported target is **C100X Door Entry 1.5.8**. Device checks require:

| Identity | Required value |
| --- | --- |
| Firmware | `1.5.8` |
| Hardware | `02*06*0` |
| Object model | `1.0.99` |
| Initial state | `4*0` |

The image must match the fixed package profile: stock-identical manifest,
recovery filesystem and kernel, with a compatible-format main filesystem.
All components are checked and privately staged before an update connection.
These checks establish package compatibility, not bootability.

## 1. Set up the flasher

Use an Apple Silicon Mac with Homebrew, mise and Xcode Command Line Tools.
Run these commands from the repository root:

```sh
mise trust
mise install python cmake
brew install libusb pkgconf
mise run setup
```

`mise run setup` creates `.venv` with the dependency used to read the vendor
installer. The image builder's additional tools are not needed for flashing.

Clone the pinned TetherKit helper and build it:

```sh
git clone https://github.com/XiaoMiku01/TetherKit.git research/TetherKit
git -C research/TetherKit checkout --detach 1ded051fd243c547fd6e250a898f0164cc30561d
mise run transport-build
```

Offline checks:

```sh
mise run test
mise exec -- ctest --test-dir .local/tetherkit-build --output-on-failure
```

Obtain the **MyHOME Suite 3.5.38 installer** from the
[manufacturer download](https://www.homesystems-legrandgroup.com/MatrixENG/liferay/bt_mxLiferayCheckout.jsp?fileFormat=generic&fileName=MyHOME_Suite_030538.exe&fileId=58107.23188.60514.44282)
and save it as `research/MyHOME_Suite_030538.exe`. The CLI reads its C100X profile
and FTP credentials in memory; it does not execute the installer.

## 2. Select and inspect the image

In the terminal you will use for CLI commands, choose your image path:

```sh
FW="$PWD/.local/custom.fwz"
INSTALLER="$PWD/research/MyHOME_Suite_030538.exe"
mise exec -- .venv/bin/python -m classe100x inspect-fw "$FW"
```

The normal format password is built into the profile. The optional
`--key-from-builder /path/to/legacy/main.py` reads a legacy literal without
executing that script. User passwords and FTP credentials are never arguments
or normal log output.

## 3. Start USB networking

Connect the powered intercom by USB. List matching RNDIS devices without root:

```sh
.local/tetherkit-build/bin/tetherkit-cli --lang en --vid 1da4 --pid 0056 --list
```

In a **second terminal**, also in the repository root, start the supervisor:

```sh
sudo "$PWD/.venv/bin/python" -m classe100x usb
```

Leave this terminal open. Root is needed for macOS feth/BPF networking. The
supervisor configures the reported system-side interface as `192.168.129.2/30`;
the intercom is `192.168.129.1`. Interface names can change after reconnecting.

## 4. Run read-only preflight

Back in the CLI terminal:

```sh
mise exec -- .venv/bin/python -m classe100x probe
mise exec -- .venv/bin/python -m classe100x plan "$FW" --myhome-installer "$INSTALLER"
/sbin/route -n get 192.168.129.1
```

`probe` queries identity/status/uptime. `plan` also validates the archive and
vendor profile; neither begins a transfer or sends update commands. Confirm
the route uses the feth interface reported by the supervisor, not ordinary LAN.

Complete the idle reconnect and supervisor-cleanup checks in
[ACCEPTANCE.md](ACCEPTANCE.md#native-read-only-preflight--passed) before flashing.
The intercom also exposes a `C100X` storage volume: eject it before an idle USB
disconnect. Firmware is transferred over the network, not copied to that volume.
Restart the supervisor and repeat preflight after those checks.

## 5. Explicitly flash

**This command writes firmware and reboots the device three times:**

```sh
mise exec -- .venv/bin/python -m classe100x flash "$FW" --myhome-installer "$INSTALLER"
```

Keep the Mac awake, the intercom powered and the USB supervisor running. Never
deliberately disconnect or terminate either process during a real write.

The researched sequence is recovery filesystem/kernel → reboot normal → clear
main kernel → reboot recovery → main filesystem/kernel → reboot normal. Each
component is uploaded and committed separately. Reboot checks require reset
uptime and the expected identity/status.

On error, record the reported stage and keep the intercom powered. The CLI does
not retry uncertain writes, resume a partial update or reboot as cleanup.

After protocol completion, verify calls, two-way audio, video, door release and
the selected payload's behavior. For generated SSH images, verify authentication
and host-key stability separately. Completion alone does not prove those functions
or the installed bytes. Stop the supervisor with Ctrl-C after the checks finish.

Restoring stock through the established Windows method first is an acceptance
test choice, not a protocol prerequisite. A direct modified-to-modified re-flash
is also a valid first hardware test; it leaves stock-to-modified acceptance open.
Both native flash paths are currently unverified. See [ADR-006](DECISIONS.md#adr-006-separate-direct-re-flash-testing-from-stock-device-acceptance).

## Further reference

- [Protocol](PROTOCOL.md): exact commands and supporting evidence.
- [Acceptance](ACCEPTANCE.md): observed results and pending hardware checks.
- [Operations](OPERATIONS.md): maintainer-specific research access and backups.
