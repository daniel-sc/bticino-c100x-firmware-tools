# Architecture and domain model

This describes the current implementation. Decisions and their rationale are in
[DECISIONS.md](DECISIONS.md); wire-level evidence is in [PROTOCOL.md](PROTOCOL.md).
Actual test results belong in [ACCEPTANCE.md](ACCEPTANCE.md).

## Processes and communication

```text
Mac, ordinary user                         Intercom
  Python CLI
    OpenWebNet TCP :20000 ----------------> identity / update control
    FTP TCP :21 + passive data -----------> one staged payload at a time
                |
                | macOS IP stack, host 192.168.129.2/30
                v
Mac, separate sudo terminal
  Python `usb` supervisor
    TetherKit CLI <-> feth/BPF <-> libusb <-> USB RNDIS, device 192.168.129.1

Research only: LAN SSH -> read-only inspection / authorized partition backups
```

The privileged supervisor has no firmware or credential responsibilities. It
keeps networking available while the updater disconnects/reconnects across
device reboots. Interface names may change; the supervisor learns the system-side
name from the pinned helper's English output and configures its static address.
It does not install a kernel extension or a permanent background service.

`plan` and `flash` use a fixed device IP. They do not programmatically verify the
route is USB: the operator checks the feth route during preflight. `probe` accepts
host/port overrides, including the research tunnel.

## Module responsibilities

| Module | Responsibility and boundary |
| --- | --- |
| `__main__.py` | Command selection, hidden key prompt, installer loading, staging lifetime and user-facing errors |
| `firmware.py` | Accept only researched archive hashes; validate manifest and all payloads; expose `PreparedFirmware` and payload metadata |
| `vendor.py` | Parse the installer profile in memory into normal/recovery credentials; read a literal archive key from the legacy builder without executing it |
| `protocol.py` | TCP framing, command-session handshake, bounded exchanges and explicit read-only query allowlist |
| `updater.py` | `UpdateClient` adds write operations; `NetworkDevice` owns sockets/FTP/waits; `flash()` sequences stages and reports where a failure occurred |
| `transport.py` | Privileged helper lifecycle, interface configuration, reconnect and termination cleanup |

The CLI composes these modules. The updater depends on protocol, firmware metadata
and vendor credentials; those modules do not depend on the updater. Transport is
independent of the update state machine. Research tools are not flasher runtime
dependencies; installer extraction is the runtime use of `bitrock-unpacker`.

## Domain vocabulary

| Term | Meaning here |
| --- | --- |
| FWZ | Encrypted ZIP update package containing a manifest and firmware payloads; not a whole-device image |
| Manifest | XML 3.0 model/action description; its `btesuv3` label does not select the actual Windows protocol implementation |
| Vendor profile | Installer's per-product settings; this C100X profile selects BTESUXP and `watershedVer=always` |
| Payload | Exact compressed file sent over FTP, with byte length, SHA-256 and POSIX checksum |
| Prepared firmware | Fully validated payloads in a private temporary directory, valid for the surrounding context-manager lifetime |
| Object model | Compatibility identity `brand.line.code` (`1.0.99`); not a unique device serial number |
| Normal state 4 | Running main firmware, but main update requires recovery mode; this is an expected initial state |
| Recovery state 1 | Running the recovery environment, which can update the main filesystem/kernel |
| Recovery payload | Firmware for the recovery environment; not the writable configuration/data partition |
| Commit | OpenWebNet request to checksum and begin writing an uploaded payload; not an atomic transaction or a Git commit |
| Idle worker | Query 42 reports no upgrade child; does not establish write success |
| Verified reboot | Reset uptime relative to elapsed time, plus expected firmware/hardware/model/status |
| Functional acceptance | Calls, two-way audio, video, door release and SSH work after the sequence |

SHA-256 pins the archive and identifies payloads. POSIX `cksum` is the distinct
checksum required by the device commit command. ZIP CRC and gzip trailers are
additional package integrity checks, not substitutes for POSIX `cksum`.

The selected FWZ has main/recovery filesystem gzip files plus a shared kernel/DTB
ZIP. The raw backups made on 2026-10-27 instead cover main firmware (`p6`) and
configuration/data (`p7`). See [OPERATIONS.md](OPERATIONS.md) for that distinction.

## Update state and resource lifetime

```text
validate all local inputs -> inspect compatible device in state 4
  -> recovery: filesystem upload/commit/idle, kernel upload/commit/idle
  -> close FTP, settle, reboot -> verify state 4 + reset uptime
  -> invalidate main kernel, reboot -> verify state 1 + reset uptime
  -> main: filesystem upload/commit/idle, kernel upload/commit/idle
  -> close FTP, settle, reboot -> verify state 4 + reset uptime
  -> report protocol completion; functional checks still required
```

Credentials are selected by the **currently running environment**: normal
credentials write the recovery payloads; recovery credentials write the main
payloads. One FTP connection uploads/checks each file. The OpenWebNet connection
is replaced after each verified reboot.

Every error stops subsequent actions. The stage label is reported to the user;
there is no persistent resume journal, automatic rollback or write retry.
The updater closes its local socket in `finally`; that cannot cancel work already
accepted by the device. Staged local files are removed on normal context exit and
handled exceptions, not guaranteed after abrupt process death.

The USB supervisor handles SIGINT/SIGTERM/SIGHUP and gives the helper a grace
period before forced termination. The updater handles Ctrl-C; it does not share
the supervisor's signal handler. Restarting the transport is not resuming an
interrupted firmware update.

## Test boundaries and extension points

The sequence is tested with a simulated device implementing the operations
`flash()` uses; no formal backend interface or plugin framework exists. Framing
and lost-ACK tests use local sockets. FTP and supervisor tests simulate external
dependencies. None needs root or real hardware.

The separate helper makes native transport testing possible without starting a
firmware update. Successful idle reconnect does not establish recovery-mode USB
behavior. Likewise, a prepared archive or idle worker does not prove installed
bytes. The remaining hardware checks are recorded in [ACCEPTANCE.md](ACCEPTANCE.md).

Support for a new model, image or release requires new protocol/profile evidence,
payload validation and identity criteria, then simulations and hardware acceptance.
The current CLI is intentionally not a general manifest execution engine.
