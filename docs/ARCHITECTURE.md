# Architecture and domain model

This describes the current implementation. Decisions and their rationale are in
[DECISIONS.md](DECISIONS.md); wire-level evidence is in [PROTOCOL.md](PROTOCOL.md).
Actual test results belong in [ACCEPTANCE.md](ACCEPTANCE.md).

## Processes and communication

```text
Mac, sudo for managed plan/flash           Intercom
  Python CLI
    OpenWebNet TCP :20000 ----------------> identity / update control
    FTP TCP :21 + passive data -----------> one staged payload at a time
                |
                | macOS IP stack, host 192.168.129.2/30
                v
Mac, supervised child of plan/flash (sudo)
  Python USB worker
    TetherKit CLI <-> feth/BPF <-> libusb <-> USB RNDIS, device 192.168.129.1

Research only: LAN SSH -> read-only inspection / authorized partition backups

Optional verification: USB SSH :22 -> installed recovery readback -> host e2fsprogs
```

The USB worker has no firmware or credential responsibilities. It
keeps networking available while the updater disconnects/reconnects across
device reboots. Interface names may change; the supervisor learns the system-side
name from the pinned helper's English output and configures its static address.
It does not install a kernel extension or a permanent background service.

`plan` and `flash` use a fixed device IP and own a managed USB session by default.
The session waits for interface configuration and verifies that the device route
uses the reported feth interface. Reconnection and FTP setup recheck this route.
`--external-usb` retains the developer-managed transport mode. `probe` accepts
host/port overrides and uses an existing connection, including the research tunnel.

## Module responsibilities

| Module | Responsibility and boundary |
| --- | --- |
| `__main__.py` | Command selection, private user-password input, staging lifetime and user-facing errors |
| `firmware.py` | Fixed package profile, preserved component hashes, bounded archive validation/staging; expose `PreparedFirmware` and transfer payload metadata |
| `download.py` | Fetch and cache the pinned original, verify size/hash, no-clobber publication |
| `builder.py` | Private working copy, ordered trusted image payloads, repacking, final checks and publication |
| `ext4.py`, `host.py` | Image-file e2fsprogs operations, metadata readback, bounded/redacted subprocess boundary |
| `payload.py`, `payload_runner.py` | Small workspace helpers and subprocess execution for trusted Python payload hooks |
| `payloads/ssh/` | Stock-specific SSH account/config/key preparation, raw image commands and verification |
| `vendor.py` | Bundled C100X normal/recovery FTP settings with source provenance and redacted representations |
| `protocol.py` | TCP framing, command-session handshake, bounded exchanges and explicit read-only query allowlist |
| `updater.py` | `UpdateClient` adds write operations; `NetworkDevice` owns sockets/FTP/waits; `flash()` sequences stages and reports where a failure occurred |
| `recovery.py` | Optional pre-write SSH prerequisites and post-recovery-write integrity gate; bounded acquisition, offline checks and private evidence |
| `ssh.py`, `ssh_askpass.py`, `ssh-askpass` | Fixed USB OpenSSH reads, invoking-user authentication, memory-only password broker and warning-only host-key evidence |
| `transport.py` | Privileged helper lifecycle, interface configuration, reconnect and termination cleanup |
| `usb_session.py` | Parent-owned USB worker, readiness/route checks, bounded startup and cleanup |
| `resources.py`, `entrypoint.py` | Relocatable release assets and isolated child interpreter entry points |

The CLI composes these modules. The updater depends on protocol, firmware metadata
and vendor credentials; those modules do not depend on the updater. Transport is
independent of the update state machine. The Python CLI uses only the standard
library. `bitrock-unpacker` is a research-only dependency, used to establish the
bundled profile from the public installer.
Builder modules are imported only for builder commands. Ordinary inspection,
planning and flashing do not require builder tools. Explicit SSH recovery
verification imports the shared host-tool boundary and requires e2fsprogs; it
does not import the builder or require 7zip, Dropbear keygen or OpenSSL.
No native macOS frameworks are imported by the Python CLI; the USB supervisor's
feth/helper execution remains macOS-specific.

## Domain vocabulary

| Term | Meaning here |
| --- | --- |
| FWZ | Encrypted ZIP update package containing a manifest and firmware payloads; not a whole-device image |
| Manifest | XML 3.0 model/action description; its `btesuv3` label does not select the actual Windows protocol implementation |
| Vendor profile | Fixed settings derived from the public installer; this C100X profile selects BTESUXP and `watershedVer=always` |
| Payload | Exact compressed file sent over FTP, with byte length, SHA-256 and POSIX checksum |
| Image payload | Trusted directory of optional preparation/verification hooks, raw debugfs commands and ordinary assets; distinct from the transfer `Payload` class |
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
  -> if selected: SSH readback + offline checks + persist passed evidence
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

The optional verifier runs prerequisites before the first recovery write. At its
gate it reads only the fixed recovery partitions, requires them unmounted by
major/minor identity, compares an independent device read/hash, verifies the
reference-defined rootfs extent and kernel/DTB file set, and runs read-only fsck
on host images. Every failure blocks main-kernel invalidation. Reports retain
integrity and update outcomes separately; no report is a resume token. The
standard path has no verifier. Authentication and evidence ownership use the
invoking ordinary user even though USB management runs under sudo. See
[ADR-012](DECISIONS.md#adr-012-optional-ssh-recovery-integrity-gate).

Managed USB sessions handle SIGINT/SIGTERM/SIGHUP, stop the worker and allow the
helper to clean up before forced termination. The standalone `usb` developer
command retains its own signal handling. Restarting transport is not resuming an
interrupted update; no device reboot/write is performed as local cleanup.

## Test boundaries and extension points

The builder's lifecycle and trust contract are detailed in [BUILDER.md](BUILDER.md).
It starts from pinned stock, edits only a private main-filesystem copy, checks
the baseline/output read-only with e2fsck, preserves archive components, and
reopens the final FWZ before no-clobber publication. No filesystem is mounted.
Raw payloads have host permissions; their commands are not inferred into a change
plan. Declared readback checks catch some composition conflicts, not all of them.

Stock-image no-op and SSH builds have passed offline checks on macOS. Synthetic
fixtures exercise failure, metadata and composition behavior without firmware or
a device. Linux parity, MyHOME import and generated-image hardware acceptance
remain pending. Fresh host keys and archive randomness rule out bit-identical
reproducibility; semantic checks are the contract.

The sequence is tested with a simulated device implementing the operations
`flash()` uses; no formal backend interface or plugin framework exists. Framing
and lost-ACK tests use local sockets. FTP and supervisor tests simulate external
dependencies. None needs root or real hardware.

The separate helper makes native transport testing possible without starting a
firmware update. Successful idle reconnect does not establish recovery-mode USB
behavior. Likewise, a prepared archive or idle worker does not prove installed
bytes. The remaining hardware checks are recorded in [ACCEPTANCE.md](ACCEPTANCE.md).

Support for a new model or release requires new protocol/profile evidence,
payload validation and identity criteria, then simulations and hardware acceptance.
New images within this fixed profile do not require adding an archive hash;
they still require independent package/device checks and functional acceptance.
The current CLI is intentionally not a general manifest execution engine.
