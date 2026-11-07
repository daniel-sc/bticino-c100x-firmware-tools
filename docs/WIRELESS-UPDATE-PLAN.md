# Owner wireless updates: consolidated design

**Approved 2026-11-07; implemented in source, hardware validation pending.** The
owner approved implementation and offline validation, with no legacy `no-ota`
alias. Device writes require separate authorization. Usage is in [FLASHING.md](FLASHING.md).
Decisions and amendments are recorded in
[the interview](WIRELESS-UPDATE-DESIGN.md); factual support and limits are in
[the research](WIRELESS-UPDATES.md). ADR-019 records the changed recovery policy.

## 1. User-visible contract

Support explicitly initiated updates of the pinned C100X 1.5.8-based firmware.
The owner selects a trusted local package. Build and flash remain separate.

### Building

- Every build blocks manufacturer installation in **both main and recovery** by
  default. `--allow-vendor-updates` explicitly retains manufacturer behavior.
- With no optional features, the default result is prevention-only. With no
  optional features and `--allow-vendor-updates`, preserve stock contents.
- Selecting SSH provisions the same owner account/authentication in both images.
  Support public keys, password or both. Generate one fresh server host key per
  build and share it between the two images.
- Ordinary payloads such as MQTT and custom applications apply only to main.
  Recovery receives built-in access and prevention changes as selected. Retain
  recovery's own vendor account records and startup scripts.
- Keep the stock kernel/bootloader and USB update facilities. Preserve originals;
  modify private image copies. Do not add a hostname customization option.
- Report the effective manufacturer-update policy and access capabilities.

**Final selection:** replace the unreleased `--payload no-ota` spelling outright;
reject it with guidance to use the default policy or `--allow-vendor-updates`.
There is no compatibility alias or additional explicit-block flag.

### Flashing

- Extend `plan` and `flash` with `--transport ssh`; USB remains the default.
  Keep preflight read-only on the device and require the explicit flash command.
- Default wireless target: `Bticino-Classe100X.local`. `--host` accepts a real
  DNS/mDNS hostname or IP. Re-resolve names during reconnect. Do not add subnet
  scanning or personal SSH-config aliases/proxies/jump hosts in v1.
- Reuse existing SSH username/key/password/agent inputs. Destination login settings
  default to the current settings, with explicit overrides for credential changes.
  Gather required inputs and check destination compatibility before writing.
- The Mac coordinates the whole run and holds a scoped idle-sleep assertion.
  Display sleep is allowed; explicit sleep/lid closure and network loss are not
  prevented by that assertion.
- V1 starts from normal firmware. After an investigated failure, existing USB
  recovery entry remains available; a wireless `recover` command is deferred.

## 2. Identity and credentials

Use an existing trusted key when available. Otherwise show the initial fingerprint
for explicit enrollment before sending credentials or device-changing commands.
Unexpected changes to an already trusted identity stop the operation. Store
public trust records under the invoking user's ownership, separate from general
SSH settings; do not automatically edit `~/.ssh/known_hosts`.

| Running environment | Login settings | Expected server identity |
| --- | --- | --- |
| Existing main, before recovery write | Existing | Enrolled/trusted existing key |
| Existing main, after normal reboot | Existing | Same existing key |
| Newly installed recovery | Destination | Key derived from selected package |
| Newly installed main | Destination | Same destination key |

Use strict phase-specific trust. During an expected reboot, an observation of the
known preceding environment is merely not-ready; it must not receive the next
phase's writes. A third, unexpected identity is an error. Require vendor state and
uptime reboot evidence as well as SSH identity, including when reinstalling the
same package and its key does not change.

Promote destination identity to the tool's current-main trust record only after
final verification succeeds. A failed run/report does not authorize trust
promotion, write replay or resume. Exact key transitions remain tied to the
selected immutable staged package for the current run.

Passwords stay in memory for the run, are passed through private pipes/brokers,
and are not persisted by the flasher. Preserve the invoking user's agent/key
context. Offline credential matching does not prove future SSH service startup
or agent availability; actual authentication is required at each environment.

The default mDNS name is a locator, not unique device identification. A host key
also is not a unique physical serial if the same package is installed on multiple
devices. This design targets an owner-selected endpoint, not fleet discovery.

## 3. Admission and competing installers

### Local package

Retain the supported archive shape and pinned manifest/kernel. Validate both
filesystem sizes, geometry and supported features; replace the stock-recovery
byte pin with an explicit recovery profile. Preserve bounded decompression,
archive checksums, payload hashes and the vendor POSIX checksum contract.

Wireless admission additionally inspects both images for supported SSH account,
authentication, permissions, daemon/service/startup configuration and actual
server key material. Verify the selected login can match both destination access
configurations. A legacy main-only SSH package is not wireless-capable merely
because its normal image has SSH. Check any claimed prevention policy from final
contents. This is content validation, not a new package-signing infrastructure.
Assume a trusted home network and owner-selected package. For SSH executable
files, require regular files with execute permission rather than an exact
owner/group or `0755` mode. Keep destination startup/content and credential checks
needed to establish future access; stock vendor protocol components remain pinned.

### Existing device

Require compatible normal state, model/version/hardware, idle protocol worker,
administrative SSH and an evidenced stable existing-main identity across its
reboot. Existing SSH need not use the exact `c100x-ssh` startup implementation:
authenticate before writing and again with the same key/credentials after the
first planned normal reboot. Only then proceed to recovery verification and
main-kernel invalidation. A missing service or changed identity stops the run
with main's kernel intact. Check vendor update components independently; do not
infer protocol compatibility from the version string alone.

Read known staging/resume-state locations and inspect manufacturer installer
activity separately from the protocol worker. Reject observed staged packages,
active installation or unsupported/inconsistent state; do not delete packages or
rewrite flags to make preflight pass. An idle `fw_manager` on OTA-enabled firmware
is not by itself an active installation. Query 42 checks only the protocol worker.
Repeat relevant read-only checks at old-main reconnection before advancing.

These are snapshots. The owner accepts a competing manufacturer installation
starting afterward in **any unprotected phase**, not just initial bootstrap.
Existing prevention is not an admission prerequisite. Do not add temporary
in-place suppression or automatically alter the existing firmware before flashing.

## 4. Update sequence and transport

Keep one source-owned sequence in `updater.py`:

1. Validate/stage the package, credentials, host dependencies and device preflight.
2. Through existing-main SSH, use the vendor protocol and FTP to write recovery
   filesystem and kernel, with the established worker/transfer checks.
3. Perform the normal reboot and verify old main using the existing key, expected
   state and reset uptime.
4. Run the existing reference-driven recovery integrity gate. Read back 200 MiB,
   compare independent device hashes, check contents/filesystems and persist its
   evidence before clearing the main kernel. A failure stops the sequence.
5. Use the evidenced main-kernel invalidation/reboot sequence to enter recovery.
   Reconnect using destination credentials/key and verify recovery state/reboot.
6. Use recovery's vendor protocol and FTP to write main filesystem and kernel.
7. Reboot and verify normal identity/state/reset uptime plus destination SSH.
   Report completion and retain the new trusted identity for future runs.

The SSH transport module owns connection/forward lifetime, phase-specific trust,
endpoint resolution and bounded readiness/reconnection. Its small interface
supplies protocol/FTP endpoints and administrative reads to the shared sequence.
USB and SSH are the two transport adapters; no general transport plugin framework
is needed. Reuse OpenSSH and its current invoking-user/password handling.

Forward remote loopback ports 20000, 21 and passive FTP 11111. Allocate local
loopback-only listeners and explicitly map FTP's advertised data port to the
chosen local data listener. Protocol/FTP readiness must be established through
the authenticated connection; a running tunnel process alone is insufficient.
No wireless exposure of the vendor protocol ports is required.

Writes are sent once. Errors or uncertain delivery stop subsequent actions without
automatic retry, resume, rollback, transport fallback or cleanup reboot. Bounded
read-only waits across planned reboots are ordinary sequencing, not write retries.
Close/reap local resources on exit; this does not cancel accepted device work.

## 5. Implementation reuse

- **Builder:** prepare both private filesystems, resolve built-in policy once,
  apply ordinary payloads to main, and verify both after composition and again
  from the repacked archive. Preserve recovery-specific metadata and vendor files.
- **Prevention:** reuse the four startup controls in both images: omit manager
  startup, set cloud `FwUpdate=0`, remove early Dedrifu startup and retain daemon
  Dedrifu disablement. Recovery needs different verifier pins, not another bypass.
- **Package module:** keep structural admission independent of builder imports
  and host image-editing tools. Add the bounded recovery geometry/profile checks
  using the existing streaming header-validation approach.
- **Wireless admission:** reuse read-only `Ext4` inspection and the e2fsprogs
  dependency already required by mandatory recovery verification. Derive access
  metadata from package contents rather than trusting a build report.
- **Host key/password checks:** prefer the already shipped `dropbearkey` and
  OpenSSL tools over new cryptographic parsers. Make them explicit lazy wireless
  dependencies and check availability before writing. Use a bounded pipe-only
  subprocess path for password checking, not the temporary-file stdin helper.
  Do not expose private key material, passwords or derived password hashes in logs.
- **Compatibility:** ordinary USB flashing remains SSH-independent and does not
  acquire builder-tool dependencies. Reports distinguish protocol, recovery
  integrity, final SSH and functional acceptance evidence.

These reuse choices were approved. Interface names, exact input limits and timeout
constants follow existing patterns and test evidence. If validation requires changing agreed behavior,
revisit that decision explicitly.

## 6. Validation and completion of design

Offline work precedes hardware use:

- Build/check both images with default prevention, explicit allowance, SSH key,
  password/both, MQTT composition, prevention-only and stock-preserving inputs.
  Verify policy conflicts, malformed packages/keys, metadata and size limits.
- Exercise the shared sequence through simulated transports: all reboot/key/
  credential transitions, known stale endpoints, unexpected keys, FTP forwarding,
  integrity-gate failure, authentication failure, timeout and lost ACK. Assert no
  further writes or cleanup reboots after failure and no premature trust promotion.
- Verify password handling, invoking-user ownership, trust enrollment/persistence,
  subprocess cleanup and idle-sleep assertion lifetime through their interfaces.
- Run `mise run test` and the relevant packaged checks after implementation.

The recovery static audit is complete: its cloud startup/status logic supports
the same prevention policy. Hardware must still establish recovery Wi-Fi/DHCP,
Bonjour, SSH/forwarded transfers, selected prevention, preserved USB operation,
full wireless completion and household functions. Validate in explicitly
authorized maintenance with USB available. Never inject failure into an actual
write; preserve dated evidence and report unsupported cases honestly.

**Design confirmed.** The owner approved the consolidated design and tool reuse,
and rejected retaining the unreleased payload spelling. Source implementation and
offline results are recorded in [ACCEPTANCE.md](ACCEPTANCE.md). No device access
or writes were performed during implementation.
