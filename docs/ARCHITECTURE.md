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

Explicit --transport ssh: LAN SSH -> loopback OpenWebNet + FTP control/passive forwards

Optional verification: USB SSH :22 -> installed recovery readback -> host e2fsprogs
Mandatory wireless verification: LAN SSH -> recovery readback -> host e2fsprogs
```

The USB worker has no firmware or credential responsibilities. It
keeps networking available while the updater disconnects/reconnects across
device reboots. Interface names may change; the supervisor learns the system-side
name from the pinned helper's English output and configures its static address.
It does not install a kernel extension or a permanent background service.

`plan` and `flash` use a fixed USB device IP and own a managed USB session by default.
With `--transport ssh`, they use `Bticino-Classe100X.local` or `--host`, own strict
phase-specific SSH forwards and require recovery verification. Names are resolved
again after planned reboots. Wireless recovery entry is not implemented.
The session waits for interface configuration and verifies that the device route
uses the reported feth interface. Reconnection and FTP setup recheck this route.
`--external-usb` retains the developer-managed transport mode. `probe` accepts
host/port overrides and uses an existing connection, including the research tunnel.

All managed commands use one USB session across both environments: native
Ethernet discovered beneath the C100X USB VID/PID, or the existing helper when
native Ethernet is absent. Native `.2/30` configuration and destination routing
are checked before device access. During reconnection the parent checks for ECM
even when the worker has not reported a feth interface, stops/reaps the helper
before using native ECM, and starts a fresh helper if RNDIS returns. An arbitrary
LAN `en` interface is never accepted (ADR-015).

## Module responsibilities

| Module | Responsibility and boundary |
| --- | --- |
| `__main__.py` | Command selection, private user-password input, staging lifetime and user-facing errors |
| `diagnostics.py` | Shared exception-chain/traceback rendering and JSON evidence; bounded notes/tool diagnostics and exact known-secret removal |
| `firmware.py` | Fixed package profile, preserved component hashes, bounded archive validation/staging; expose `PreparedFirmware` and transfer payload metadata |
| `download.py` | Fetch and cache the pinned original, verify size/hash, no-clobber publication |
| `builder.py` | Two private filesystem copies, automatic vendor-update policy, shared SSH provisioning, main-only ordinary payloads, repacking and final checks |
| `ext4.py`, `host.py` | Image-file e2fsprogs operations, metadata readback and bounded subprocess execution with failure diagnostics |
| `payload.py`, `payload_runner.py` | Small workspace helpers and subprocess execution for trusted Python payload hooks |
| `payloads/ssh/` | Stock-specific SSH account/key preparation, independently owned init service, vendor-control disablement and image verification |
| `payloads/mqtt/` | Stock-runtime bridge, private broker configuration, startup integration and image readback checks |
| `payloads/no-ota/` | Internal default-on startup suppression in both filesystems and environment-specific pinned checks; not a selectable payload |
| `vendor.py` | Bundled C100X normal/recovery FTP settings with source provenance and redacted representations |
| `protocol.py` | TCP framing, command-session handshake, bounded exchanges and explicit read-only query allowlist |
| `updater.py` | `UpdateClient` adds write operations; `NetworkDevice` owns sockets/FTP/waits; `flash()` sequences stages and reports where a failure occurred |
| `recovery.py` | SSH prerequisites and post-recovery-write integrity gate (optional for USB, mandatory for wireless); bounded acquisition, offline checks and private evidence |
| `ssh.py`, `ssh_askpass.py`, `ssh-askpass` | OpenSSH reads, invoking-user authentication and memory-only password broker; warning-only USB evidence or strict expected wireless identity |
| `wireless.py` | Direct LAN resolution, owner trust enrollment/records, phase-owned strict SSH forwards, credential reuse, read-only installer checks and scoped idle-sleep prevention |
| `wireless_image.py` | Wireless-only expanded image admission, content-derived host identity/access policy and pipe-only future credential checks |
| `transport.py` | Privileged helper lifecycle, interface configuration, reconnect and termination cleanup |
| `usb_session.py` | Native ECM/helper RNDIS selection, parent-owned worker, readiness/route checks, bounded startup and cleanup |
| `usb_storage.py` | Bounded best-effort macOS unmount of USB-associated storage before planned reboot; no device protocol or persistent host settings |
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
Wireless admission additionally uses the shipped Dropbear keygen and OpenSSL
tools to inspect the destination identity and authentication. These imports/tools
are lazy; ordinary USB inspection/flashing remains independent of them.
No native macOS frameworks are imported by the Python CLI; the USB supervisor's
feth/helper execution remains macOS-specific.

Diagnostics use existing exceptions, explicit chaining and Python exception notes;
new scenarios can add context with `details()` or `tool_error()`. The CLI renders
causes by default and stacks with `--debug` (always for unexpected exceptions).
Recovery reports and requested build failure reports serialize the same chain,
including stacks without local variables. Messages/tool output retain the last
8,192 characters per field, marking truncation. SSH stderr and
the managed USB helper's recent output survive failures; read-only readiness
loops retain their final failure/observation rather than logging every poll.
Known secret values are registered in memory and replaced exactly. Ordinary paths,
usernames and diagnostic text are retained; reports need review before sharing.

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

`recover` is a separate explicit entry into the shared main-transfer sequence.
It requires matching state `1*0` and an idle worker, writes only main filesystem
and kernel, then verifies one normal reboot. `plan-recovery` performs only local
validation and device reads. Neither command interprets a previous report as a
resume token; the interrupted state must be assessed first.

The CLI injects host storage preparation only into write-capable `NetworkDevice`
instances. Before each planned reboot, query 19 refreshes the command idle timer,
then a best-effort unmount uses a ten-second total budget. Transport is rechecked
and uptime sampled afterward for the existing reboot proof. Preflight and error
cleanup never unmount storage or request a reboot (ADR-016).

The optional verifier runs prerequisites before the first recovery write. At its
gate it reads only the fixed recovery partitions, requires them unmounted by
major/minor identity, compares an independent device read/hash, verifies the
reference-defined rootfs extent and kernel/DTB file set, and runs read-only fsck
on host images. Every failure blocks main-kernel invalidation. Reports retain
integrity and update outcomes separately; no report is a resume token. The
standard path has no verifier. Authentication and evidence ownership use the
invoking ordinary user even though USB management runs under sudo. See
[ADR-012](DECISIONS.md#adr-012-optional-ssh-recovery-integrity-gate).

Wireless always uses that verifier, borrowing administrative reads from the
transport without closing its owner at the integrity gate. The old-main key and
credentials apply across the first reboot. Package-derived destination identity
and credentials apply in recovery and final main. Expected keys never become a
permissive union: a known preceding environment is only not-ready during a planned
transition, and an unexpected identity is fatal. Read-only polling can recreate
forwards during planned reboots; an unexpected active-stage tunnel loss stops.
Final normal reboot/state and SSH are required before promoting destination trust.
Trust records are invoking-user-owned and separate from general SSH settings.
On the trusted-home network model, existing-main SSH is admitted by working
administrative access and actual same-key reconnection after its planned reboot,
without matching a particular startup script or configuration spelling. A failed
reconnection stops before main-kernel invalidation. Destination images still require
checked startup contents and credentials; executable metadata checks accept
equivalent modes/ownership instead of requiring exactly root-owned `0755`.

The three forwards use unprivileged loopback listeners for remote 20000, 21 and
11111. The FTP adapter requires PASV port 11111 and maps it to the owned local
listener, ignoring the advertised address. No vendor port is exposed on the LAN.
Known staged packages, nonempty vendor update metadata and active installers stop
preflight; an idle manager alone does not. Competition after a snapshot remains
accepted in unprotected environments. No device configuration is changed by checks.

Managed USB sessions handle SIGINT/SIGTERM/SIGHUP, stop the worker and allow the
helper to clean up before forced termination. The standalone `usb` developer
command retains its own signal handling. Restarting transport is not resuming an
interrupted update; no device reboot/write is performed as local cleanup.

## Test boundaries and extension points

The optional SSH payload owns `c100x-ssh`, with separate defaults and PID file,
runlevel-5 startup and runlevel-0/1/6 shutdown. Stock Dropbear is reused, but the
vendor init script exits on `NO_START=1` before either start or stop. Persistent
`abil_ssh` therefore cannot race with the selected service. No configuration-data
write or flasher dependency is introduced. Shell lifecycle tests simulate process
control; image checks verify installed assets, the vendor gate and boot links.
Observed SSH-v2 hardware results are in [ACCEPTANCE.md](ACCEPTANCE.md) (ADR-017).

The optional MQTT payload is self-contained: host hooks verify stock dependencies
and install scripts/configuration. On-device, a lock-holding Python supervisor
restarts one worker. The worker owns a connection generation: clean-session MQTT,
public loopback monitor and serialized short-lived command sockets. Generation
failure discards queued data and closes its resources before bounded backoff.
Native callbacks enqueue bounded commands; the same worker loop drives MQTT,
event framing and command progress. A dead supervisor causes its worker to exit.
No vendor process, updater or SSH service is managed by this payload. See
[ADR-013](DECISIONS.md#adr-013-optional-stock-runtime-mqtt-payload) and
[builder reference](BUILDER-REFERENCE.md#mqtt-limits-and-diagnostics) for the compatibility contract.

The default manufacturer-update policy removes the manager from the vendor process list
and disables the independent boot installer link. `FwUpdate=0` bypasses the cloud
client's startup dependency on that manager; both selectable XML variants retain
the disabled daemon installer setting. Exact image checks reject conflicting
configuration and optional daemon INI overrides. MQTT accepts the stock or exact
prevention XML. No runtime component is added; installer files and persistent
update data remain intact. Apply this to both prepared filesystems unless
`--allow-vendor-updates` is selected. Recovery uses its own verifier pins and
startup script. Hardware acceptance remains pending; existing unprotected
firmware is not changed by preparation (ADRs 018/019, [OTA.md](OTA.md)).

The builder's lifecycle and trust contract are detailed in [BUILDER-REFERENCE.md](BUILDER-REFERENCE.md).
It starts from pinned stock, edits private main/recovery filesystem copies, checks
the baseline/output read-only with e2fsck, preserves archive components, and
reopens both images in the final FWZ before no-clobber publication. No filesystem is mounted.
Raw payloads have host permissions; their commands are not inferred into a change
plan. Declared readback checks catch some composition conflicts, not all of them.

Stock-image no-op, SSH and MQTT+SSH builds have passed offline checks on macOS;
main-system SSH+MQTT has passed the recorded hardware/household checks.
Synthetic fixtures exercise failure, metadata and composition behavior without
firmware or a device. Linux parity and MyHOME import remain unvalidated. Fresh
host keys and archive randomness rule out bit-identical reproducibility;
semantic checks are the contract.

The sequence is tested with a simulated device implementing the operations
`flash()` uses; no formal backend interface or plugin framework exists. Framing
and lost-ACK tests use local sockets. FTP and supervisor tests simulate external
dependencies. None needs root or real hardware.

The separate helper makes native transport testing possible without starting a
firmware update. Successful idle reconnect does not establish recovery-mode USB
behavior. Likewise, a prepared archive or idle worker does not prove installed
bytes. The remaining hardware checks are recorded in [ACCEPTANCE.md](ACCEPTANCE.md).

Support for a new device model or vendor firmware release requires new protocol/profile evidence,
payload validation and identity criteria, then simulations and hardware acceptance.
Within C100X 1.5.8, source tools accept hardware family `02.*.*` using the vendor's
first-component rule at every identity check. Revision-specific observed hardware
results are recorded separately in [ACCEPTANCE.md](ACCEPTANCE.md): maintainer
coverage on `02*06*0` and a community stock-to-modified report on `02*07*0`
with evidence carried forward for unchanged behavior. See the
[hardware-policy amendment](DECISIONS.md#adr-001-preserve-the-existing-image-and-restrict-compatibility).
New images within this fixed profile do not require adding an archive hash;
they still require independent package/device checks and targeted functional
acceptance for material changes. A new tool version alone does not reset evidence.
The current CLI is intentionally not a general manifest execution engine.
