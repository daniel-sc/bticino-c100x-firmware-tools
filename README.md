# Classe 100X firmware flashing from macOS

Native Python CLI plus TetherKit USB/RNDIS transport for the researched Classe
100X 1.5.8 update path. The stock-device workflow uses USB, OpenWebNet and FTP;
it does not require SSH or Windows.

**Status: native C100X read-only preflight passed on 2026-10-27; actual flashing
remains unverified.** USB probe, non-writing firmware plan, idle reconnect and
supervisor cleanup passed. FTP transfer and recovery-mode networking still
await hardware validation.

Only the two archive hashes in [docs/SCOPE.md](docs/SCOPE.md) are accepted.
Device checks require firmware `1.5.8`, hardware `02*06*0`, object model `1.0.99`
and initial status `4*0`. Firmware is staged unchanged in a private temporary
directory, fully checked before connecting for an update, and removed on exit.

## Setup

Run from the project directory on an Apple Silicon Mac with Xcode command-line
tools and mise installed:

```sh
mise trust
mise install python cmake
brew install libusb pkgconf
mise run setup
```

The CLI uses the mise-managed Python 3.14.9 virtual environment. The remaining
tools in `mise.toml` are for offline reverse engineering.

The local TetherKit checkout is pinned to
`1ded051fd243c547fd6e250a898f0164cc30561d`. For a fresh workspace:

```sh
git clone https://github.com/XiaoMiku01/TetherKit.git research/TetherKit
git -C research/TetherKit checkout --detach 1ded051fd243c547fd6e250a898f0164cc30561d
```

Build and run offline checks:

```sh
mise run transport-build
mise run test
mise exec -- ctest --test-dir .local/tetherkit-build --output-on-failure
```

Obtain the user's MyHOME Suite 3.5.38 installer as
`research/MyHOME_Suite_030538.exe`. The CLI reads the C100X profile and FTP
credentials into memory without executing the installer or exporting credentials.

## Offline firmware inspection

For this workspace, set these paths in the terminal used for the CLI:

```sh
FW="/Users/daniel/backup-2026-04-08/dev/bticinoClasse300x/custom_firmware/NEW_c100x_1.5.8_MQTT_20251106_205901.fwz"
BUILDER="/Users/daniel/backup-2026-04-08/dev/bticinoClasse300x/main.py"
INSTALLER="$PWD/research/MyHOME_Suite_030538.exe"
mise exec -- .venv/bin/python -m classe100x inspect-fw "$FW" --key-from-builder "$BUILDER"
```

`--key-from-builder` statically reads the existing legacy builder's C100X archive
key; it does not execute the builder. Omit this option for a hidden terminal
prompt. The key and FTP credentials are never command-line arguments or output.
Payload hashes and POSIX checksums are recorded in
[docs/selected-image.json](docs/selected-image.json).

## Native USB preflight — no firmware writes

Connect the powered intercom by USB using the established physical setup. List
matching RNDIS devices without root:

```sh
.local/tetherkit-build/bin/tetherkit-cli --lang en --vid 1da4 --pid 0056 --list
```

In a separate, real terminal, from this project directory:

```sh
sudo "$PWD/.venv/bin/python" -m classe100x usb
```

Leave this terminal open. The supervisor configures each detected **system-side**
feth interface as `192.168.129.2/30`; the intercom is `192.168.129.1`. It handles
new interface names and restarts the helper if it exits. Root is needed for
feth/BPF. Use terminal `sudo`, following TetherKit's documented signal-handling
constraints.

In the CLI terminal:

```sh
mise exec -- .venv/bin/python -m classe100x probe
mise exec -- .venv/bin/python -m classe100x plan "$FW" \
  --key-from-builder "$BUILDER" --myhome-installer "$INSTALLER"
```

`probe` sends only allowlisted identity/status/uptime queries. `plan` also checks
the complete archive and vendor profile; it does not start FTP or send update
commands. Check that the route to `192.168.129.1` uses the reported feth interface
with `/sbin/route -n get 192.168.129.1`.

Before any flashing, verify idle USB disconnect/reconnect and supervisor Ctrl-C
cleanup as described in [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).

## Flash

For the agreed stock-to-modified acceptance run, first complete native preflight,
then restore stock 1.5.8 with the previously successful Windows method. Reconnect
to the Mac and repeat `probe` and `plan`. Keep the USB supervisor running.

Re-flashing the selected modified image onto the currently modified 1.5.8 device
uses the same sequence and is also a valid first hardware test. Restoring stock
first is an acceptance-test choice, not a protocol prerequisite; a direct re-flash
would leave stock-to-modified compatibility acceptance pending.

**This command writes firmware and reboots the device three times:**

```sh
mise exec -- .venv/bin/python -m classe100x flash "$FW" \
  --key-from-builder "$BUILDER" --myhome-installer "$INSTALLER"
```

Sequence: recovery filesystem/kernel → reboot normal → clear main kernel →
reboot recovery → main filesystem/kernel → reboot normal. Each payload is
uploaded and committed separately. Reboot verification requires reset uptime
and the expected identity/status.

On an error, retain the reported stage and keep the intercom powered. The CLI
does not retry uncertain writes, resume a partial update, or reboot as cleanup.
Never deliberately disconnect or terminate either process during a real write.
After completion, verify calls, two-way audio, video, door release and SSH;
protocol completion alone does not prove those functions or the installed bytes.

Stop the USB supervisor with Ctrl-C after the update and checks are finished.
SIGINT, SIGTERM and SIGHUP request helper cleanup. If the helper cannot stop
within ten seconds it is forcibly terminated and feth cleanup is reported as
unverified.

## Implementation and evidence

- `classe100x/protocol.py`: bounded framing and read-only query allowlist.
- `classe100x/firmware.py`, `vendor.py`: package checks and in-memory settings.
- `classe100x/updater.py`: FTP transfer and recovery-first state sequence.
- `classe100x/transport.py`: pinned TetherKit CLI supervision.
- [docs/PROTOCOL.md](docs/PROTOCOL.md): command evidence and protocol limitations.
- [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md): hardware validation record.

The tests use local sockets and simulated devices/processes. They require
neither an intercom nor root and never contact a real device.
