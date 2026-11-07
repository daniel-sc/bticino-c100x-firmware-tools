# Architecture decision records

Recorded retrospectively on **2026-10-28** from the implementation and project
discussion. All records below are **accepted**; acceptance describes the design
choice, not successful hardware flashing. Keep these IDs stable and record a
superseding decision if the approach changes.

Hardware-status statements within individual records describe their recording
date. Use [ACCEPTANCE.md](ACCEPTANCE.md) for current passed/open checks.

## ADR-001: Preserve the existing image and restrict compatibility

**Status update, 2026-10-28:** firmware-creation scope and whole-archive admission
are superseded by ADR-007. Original preservation and device checks still apply.

**Hardware-policy amendment, 2026-11-07 (issue #6):** follow the researched MyHOME
BTESUXP first-component hardware comparison for the fixed C100X 1.5.8 profile.
Accept hardware family `02.*.*` with three nonnegative numeric fields, alongside
the existing exact device type, firmware, object model and state checks. Apply
the same rule at entry, after reboots and during explicit recovery installation.
This supersedes the exact `02*06*0` hardware restriction in source; published
v0.1.0 retains it. Vendor compatibility and observed hardware acceptance are
distinct: the recorded full flash and household checks remain on `02*06*0`.
The vendor rule, common SHARK storage selection and stock Car-6/Car-7 DTBs provide
positive compatibility evidence; no identified incompatibility justifies a
revision allowlist. No generic bypass is needed. See the
[protocol evidence](PROTOCOL.md#hardware-family-compatibility-2026-11-07).

**Context:** The goal is native macOS installation of an existing Windows-tested
modified C100X image. Firmware modification and Home Assistant design are outside
this project. Matching a firmware version alone does not identify compatible
hardware or a known package.

**Decision:** Preserve the originals. Accept only the two researched stock/custom
archive hashes and the established 1.5.8 hardware/model/status combination. Fully
validate and stage every payload before the updater connects. Provide separate
offline inspection, read-only planning and explicit flashing commands.

**Consequences:** A newly generated image, even with version 1.5.8, is rejected.
Adding a hash is a compatibility change requiring evidence, not a generic bypass.
Exact hashes and scope are maintained in [SCOPE.md](SCOPE.md).

## ADR-002: Python orchestration and a separate native USB helper

**Status update, 2026-10-28:** ADR-011 replaces the default two-terminal lifecycle
with an automatically managed USB session. The native helper remains separate.

**Context:** macOS needs an RNDIS transport, while protocol research and simulation
benefit from a small CLI. The final stock-device workflow cannot depend on SSH.
The user accepts terminal sudo and Homebrew system libraries, and requires mise
for project-local tools.

**Decision:** Use Python for package/protocol orchestration and pinned TetherKit
for libusb/feth/BPF networking. Run the USB supervisor in a separate sudo terminal;
run the firmware CLI as the ordinary user. Use a static `.2/30` host address to
match the stock gadget/trusted-source configuration. Manage tools with mise.

**Consequences:** There are two terminal lifecycles, and the helper output format
is an integration dependency. Changing TetherKit needs revalidation of interface
detection, reconnect and cleanup. Pin details are in [SOURCE.md](SOURCE.md#usb-helper-setup).
Python 3.14.9 was selected after the research dependency `dissect.cstruct` failed
under 3.15; this was an observed dependency issue, not proof the CLI cannot ever
support newer Python. A VM/Windows runtime and SSH-based flashing are not part of
the native workflow; SSH remains useful for research and backups.

## ADR-003: Follow the actual BTESUXP recovery-first workflow

**Context:** The manifest's provider label and the older BTESU v3 code initially
left model mapping and update order ambiguous. The C100X installer profile and
newer updater resolve both. Status 4 is expected and requires recovery for main
updates; `watershedVer=always` selects recovery first even for the same version.

**Decision:** Use the evidenced sequence: recovery filesystem/kernel, reboot
normal, clear main kernel, reboot recovery, main filesystem/kernel, reboot normal.
Transfer one payload at a time, filesystem before kernel, through vendor FTP and
OpenWebNet commands. Do not substitute direct partition writes or synthesize the
manifest's absent extra files.

**Consequences:** Four payload writes and three reboot boundaries are required by
normal-entry flashing. ADR-014 adds an explicit main installation from an already
running recovery environment after investigation of a stopped update. The six
absent extras in both researched packages do not block their separate firmware
actions. Exact commands and source references are in [PROTOCOL.md](PROTOCOL.md).

## ADR-004: Stop on uncertain delivery and distinguish completion evidence

**Context:** A lost write ACK can mean the command was delivered. Query 42 only
reports whether an upgrade child exists. Version 1.5.8 remains unchanged across
reinstallation, and a transient network outage is not proof of reboot.

**Decision:** Send each write command once. On uncertainty stop subsequent steps,
report the stage and close local connections; do not retry, resume or reboot as
error cleanup. Verify reboot with uptime reset and expected identity/status.
Keep protocol completion distinct from installed-byte and functional verification.

**Consequences:** Some recoverable interruptions still require investigation.
Timeouts bound waiting but do not cancel device writes. Only simulation deliberately
injects failures; actual writes are never intentionally interrupted. Read-only
allowlisting excludes query 44 because it schedules a reboot. See
[ARCHITECTURE.md](ARCHITECTURE.md) for lifecycle and testing boundaries.

## ADR-005: Keep vendor secrets and private artifacts out of source control

**Diagnostic-policy update, 2026-11-04:** The diagnostic amendment to ADR-008 below
supersedes blanket suppression of original FTP/tool errors. Private credentials
remain excluded; ordinary diagnostic context is retained for user review.

**Status update, 2026-10-28:** ADR-007 bundles the public FWZ format password;
ADR-010 supersedes runtime FTP-profile extraction with bundled public vendor
settings. Private device/user credentials and artifacts remain excluded.

**Context:** The workflow needs vendor FTP settings and an FWZ archive key. Research
artifacts and raw backups can contain credentials and private configuration.

**Decision:** Extract FTP settings directly into memory from the user's installer.
Obtain the archive key through a hidden prompt or static AST parsing of the legacy
builder; never execute the builder. Suppress credential representations and raw
FTP errors. Track code, documentation, test fixtures and non-secret checksums;
exclude installers, firmware, extracted research, local environments and backups.

**Consequences:** Git alone does not reproduce the complete local workspace.
External inputs must be obtained separately. The explicitly requested plain
partition backups are an intentional private-data artifact, stored with restrictive
permissions outside Git, not an exception allowing credentials into logs/source.
Their acquisition and consistency limits are documented in
[ACCEPTANCE.md](ACCEPTANCE.md); the one-off backup script is not a supported CLI.

## ADR-006: Separate direct re-flash testing from stock-device acceptance

**Context:** The user asked whether a stock restore was technically necessary
before re-flashing the modified image. Installed update binaries match stock,
the device meets the same compatibility/status checks, and the profile requests
the full sequence for same-version updates.

**Decision:** A direct modified-to-modified re-flash is a valid first hardware
test. Restoring stock first is an acceptance-test choice, not a protocol
prerequisite. The original stock-to-modified, no-SSH acceptance goal remains.

**Consequences:** There is no known protocol difference requiring stock first,
but modified services/configuration are not proof of identical runtime behavior.
A successful direct re-flash would not close the stock-to-modified acceptance
item. At the time of recording, neither flash path has been performed by this CLI.

## ADR-007: Integrate a fixed-profile builder and verified stock acquisition

**Accepted 2026-10-28**, following the image-builder design review and explicit
authorization for implementation, dependency setup, downloads and local builds.
No device access or flashing was authorized in that implementation session.

**Design amendment, 2026-11-06:** ADR-019 permits a customized recovery filesystem
for the planned owner wireless-update feature. Its design is still in progress;
the currently implemented stock-recovery package checks have not changed.

**Decision:** Keep one Python CLI with separate builder/flasher modules. Build
only from the stock C100X Door Entry 1.5.8 SHA-256 pin. A named stock selection may
download the exact manufacturer artifact on verified-cache miss. Local files
remain supported offline. Never modify originals or overwrite an existing output.

Flashing admits a fixed package profile rather than two complete archive hashes:
the manifest, recovery gzip and kernel ZIP must remain byte-identical to stock,
and the main filesystem must have the expected expanded size, geometry and
features. Require exact members and evidenced classic ZipCrypto ZIP properties.
The published format password is profile data; it is not a private credential.
No build report, payload metadata or e2fsprogs installation is required by the
flasher. Actual-device checks and the recovery-first sequence remain independent.

**Consequences:** Newly built/external matching images can be inspected and
flashed, but passing format checks does not prove filesystem health, bootability
or integration behavior. New releases/models need new evidence. Mac support is
observed locally; Linux parity and Windows/MyHOME import remain acceptance work.
Windows-native support is not promised. No-op and SSH image checks are recorded
separately from hardware results.

## ADR-008: Trusted raw payloads and a small e2fsprogs process boundary

**Accepted 2026-10-28.**

**Diagnostic amendment, accepted 2026-11-04:** Troubleshooting takes priority over
blanket withholding of original errors. Preserve exception causes and bounded
stderr, identify failed operations, and retain final read-only polling failures.
Use Python exception notes and one shared renderer/JSON serializer rather than a
logging framework or new exception hierarchy. `--debug` adds terminal stacks;
unexpected programming errors always show stacks. Persistent failure reports
retain stacks regardless of that flag, and an explicitly requested build report
may now be published on failure as well as success, without overwriting files.

Keep ordinary paths, usernames and tool messages. Do not collect argv, stdin,
local variables or raw image/hook stdout. Allow diagnostic stdout from fsck and
packaging tools. Remove exact known secret values in memory; do not attempt a
general-purpose sensitive-data classifier. Users review diagnostics before
sharing. This supersedes the raw-log suppression below and FTP-error suppression
in ADR-005/010, while retaining private credentials and artifacts outside Git.

**Decision:** Use raw `apply.debugfs` command files and optional `prepare.py` and
`verify.py` hooks, in explicit CLI order. Payloads are trusted host programs;
the workspace is not a sandbox. Reject duplicate identities; do not invent a
filesystem DSL, dependency solver or complete conflict detector. Bundled payloads
require critical-result checks; other payloads may omit them.

Use `debugfs` against regular image files without mounting. Reject diagnostics
other than the expected banner because observed failing writes returned exit 0
and the batch continued. Bound tool output/time, suppress raw logs, and check
actual bytes/types/owners/modes/links. Run read-only e2fsck before/after changes;
no vendor-error exceptions or automatic repair are currently enabled. Reopen the
finished archive and repeat payload checks before publishing.

Use mise's 7zip for traditional encrypted DEFLATE output. Stock and SSH round trips
passed; unsupported output variants fail profile validation. Small incompressible
fixtures demonstrated 7zip's automatic STORE behavior, so compression-method checks
are required even with `-mm=Deflate`. A pyminizip 0.2.6 installation experiment
failed against the current Apple SDK's stdio headers; it was not added as a
dependency. No custom ZIP crypto implementation or language change was introduced.

**Consequences:** Some raw operations remain semantically unchecked without a
payload verifier. Python hooks can perform guarded edits and credential/key
preparation without embedding SSH/MQTT concepts in the engine. Hook/tool versions
and diagnostics are maintenance boundaries. Report/image publication is not a
two-file transaction: an optional report failure may leave a valid published FWZ.

## ADR-009: Ship explicitly selected stock-Dropbear SSH access

**Accepted 2026-10-28.**

**Decision:** Track SSH preparation/commands/checks, never user credentials or
host private keys. Reuse the stock Dropbear and init script. Add the evidenced
`root2` administrative account while preserving vendor accounts. Accept a supplied
public key, password or both; key-only mode disables password authentication
daemon-wide. Use the observed stock SHA-512-crypt password format with fresh salts.
Generate a fresh ECDSA P-256 host key on every build and point init's generic `-r`
argument at its persistent image path, avoiding volatile host-key generation.

Prefer ECDSA P-256 user keys for modern OpenSSH. RSA keys are supported for the
user's existing default key, with the explicit legacy user-signature limitation.
No Ed25519 support or upgraded target daemon is claimed. The stock binary contains
ECDSA algorithm identifiers, but vendor-build ECDSA login needs hardware proof.

**Consequences:** Reboot identity should be stable; a newly built image has a new
identity. Password mode retains other vendor accounts and their existing records.
The generated FWZ contains credentials/private host identity and stays private.
SSH is selected explicitly, so a no-payload build remains a useful no-op test.

**Superseded in part by ADR-017 (2026-11-04):** retain stock Dropbear, accounts and
host-key policy, but give the selected SSH payload its own init service instead
of enabling the vendor-controlled init script.

## ADR-010: Bundle the public C100X settings and simplify setup

**Accepted 2026-10-28**, at the user's request.

**Decision:** Bundle the fixed normal/recovery FTP settings from the publicly
distributed MyHOME Suite 3.5.38 C100X profile, with installer hash and member-path
provenance. These are shared vendor profile data, like the FWZ format password,
not personal credentials. Keep credential representations and FTP errors redacted.

Remove runtime installer extraction, its required CLI argument and its pip
dependency. Remove the obsolete legacy-builder archive-key override as the format
key is already fixed by the supported profile. The CLI now uses Python's standard
library; delete the runtime requirements file and setup task. Keep installer
unpacking dependencies only in the separate research environment.

Xcode Command Line Tools belong in USB-helper setup because TetherKit needs a
C++ compiler and macOS SDK. The Apple Silicon builder quick start uses prebuilt
tools. Homebrew may still require developer tools for source installations;
see its [installation requirements](https://docs.brew.sh/Installation).

**Consequences:** Users can plan/flash with the firmware path alone, without
downloading MyHOME or providing a legacy builder. Package/device checks and the
recovery-first update sequence still enforce the researched target. Changes to
the supported device profile require new evidence and a code update. This does
not establish hardware acceptance; user passwords, host private keys, firmware
and backups remain private artifacts.

## ADR-011: Distribute one self-contained CLI through alpha releases

**Accepted 2026-10-28**, following the short release-design interview.

**Validation amendment, accepted 2026-11-05:** Carry forward observed hardware
acceptance for unchanged device behavior. Documentation and small host-side fixes
use appropriate offline and release-artifact checks; they do not require a fresh
firmware flash for every release. Material changes to write sequencing, reboot/USB
handover, compatibility or installed payload behavior need targeted validation
of the affected path. Version labels alone do not determine hardware-test scope.

The alpha.6 full flash and functional checks satisfy the original v1 milestone
for the tested installation. Stock-to-modified remains a disclosed one-time
coverage goal under ADR-006, not a prerequisite for every release or a claimed
pass. The post-alpha.6 best-effort storage-discovery correction can ship after
offline and packaged checks; live observations can join the next planned hardware
session. This balances useful regression evidence with avoiding unnecessary
household-device flashes. Current policy is in [RELEASING.md](RELEASING.md#validation-policy).

**Decision:** Ship an Apple Silicon macOS DMG containing one CLI entry point and
its support files. Build and Flash remain explicit independent commands. Bundle
CPython, tools and payloads so end users install no prerequisites. Compile the
bundled interpreter from source and preserve Python hook semantics; no automatic
pip dependencies. Reject root execution for builds/hooks.

`plan`/`flash` manage the USB worker, route checks, readiness and cleanup. Root is
requested through ordinary terminal sudo. Keep the independent `usb` command and
`--external-usb` for development. Preserve the evidenced update protocol and
non-retry behavior; process cleanup must never become device cleanup.

GitHub CI runs offline tests, builds the release, audits library relocation,
exercises shipped tools and hooks, then signs/notarizes/staples tagged alpha DMGs.
Publish dependency sources and build provenance with the binary. Existing Apple
team credentials can sign this project but must be provided as this repository's
secrets. Alpha publication precedes hardware validation; v1 requires successful
native flashing and functional acceptance. Detailed design and credential setup
are in [RELEASING.md](RELEASING.md).

**Homebrew distribution decision, 2026-11-04:** Add a cask in the separate public
`daniel-sc/homebrew-tap` repository, reusing the signed DMG. This gives users a
one-command install without another build pipeline. Keep Apple Silicon/macOS 15+
support, install the complete `/Applications/C100X` bundle and expose `c100x` on
PATH. Track published alpha releases with manual version/checksum updates.
See the release guide for the maintenance step.

**Stable publication, accepted 2026-11-05:** Publish `v<major>.<minor>.<patch>`
tags as stable GitHub releases, starting with v0.1.0; retain `-alpha.<number>`
for prereleases. Both use the same signed/notarized artifacts and validation
pipeline. Stable releases become latest; alphas do not replace them. Maintain
`packaging/RELEASE.md` with one or two user-facing sentences per change; the first
stable release uses a short product introduction. Update the Homebrew cask after
each published and validated release.

## ADR-012: Optional SSH recovery integrity gate

**Accepted 2026-10-29**, after the documented design interview. This scopes the
flasher dependency exception in ADR-002/007; ordinary stock-device flashing
continues to require neither SSH nor e2fsprogs.

**Context:** Stock query 40 reflects a recovery `uImage` CRC check, but not recovery
rootfs/DTB integrity. Worker completion also does not establish installed bytes.
The user wants additional protection before clearing a working main kernel on
devices that already have administrative SSH access.

**Decision:** Make verification explicitly opt-in. Check prerequisites before
writes, then gate main-kernel invalidation on recovery readback after the existing
normal reboot. Require exact reference-defined rootfs bytes, expected kernel/DTB
file contents, offline filesystem consistency, independent acquisition hashes,
and persisted evidence. Stop on failure or uncertainty, without write retries,
repairs, fallback to unchecked flashing or automatic resume.

Reuse system OpenSSH and bundled e2fsprogs. Use the managed USB route and the
invoking user's SSH identity; cache passwords only in memory through a private
askpass broker. Encrypted keys use an existing unlocked agent. Allow first-seen
and changed host keys with recorded warnings because prior installations can
regenerate volatile keys on reboot. This deliberately does not promise
cryptographic identity continuity; it is for trusted connected devices.

**Consequences:** Verification adds time, temporary storage and optional tool
dependencies. It can reject harmless-looking differences rather than risk a
false pass. It cannot prove recovery bootability, networking, physical-media
durability or household functional acceptance. Private reports survive; raw
images are removed during normal cleanup. Implementation and publication do not
authorize hardware writes. Detailed decisions are in
[SSH-VERIFICATION-DESIGN.md](SSH-VERIFICATION-DESIGN.md).

## ADR-013: Optional stock-runtime MQTT payload

**Accepted 2026-10-31**, after the MQTT-payload design interview and live public
monitor comparison recorded in [ACCEPTANCE.md](ACCEPTANCE.md).

**Decision:** Add an explicitly selected `mqtt` image payload through the existing
builder hooks. Keep the flasher unchanged and SSH independently selectable. Write
small MIT-licensed scripts using stock Python 2.7 and `libmosquitto` via ctypes;
do not redistribute vendor runtime binaries or import the legacy GPL supervisor.
Use the evidenced public loopback monitor on port 20000, not tcpdump or the
single-client internal monitor. Forward raw commands once, in order, through
bounded short-lived connections to loopback port 30006. Do not retry uncertain
delivery or synthesize the caller's door press/release sequence.

Preserve the tested household event/command payloads and configurable-prefix
`tx`, `rx`, `start_date`, `LastWillT` topics (default prefix `Bticino`). The public
monitor is not byte-for-byte equivalent to legacy internal-traffic capture.
Omit administrative JSON/file/shell commands and physical-button reporting.

Require a private build-input object with numeric IPv4 broker address and
username/password. V1 uses explicitly selected plaintext MQTT; TLS and runtime
provisioning are deferred. Configuration changes use another build and flash.
Ordinary events are QoS 0/non-retained; availability/startup information is
retained. Use clean sessions, reject retained command replay, and discard pending
work on detected connection failure. There is no persistent queue or deliberate
replay, but undetected stalls may delay already-transmitted data. No timestamp
protocol, synchronized clocks or HA configuration changes are required.

One instance owns MQTT and monitor readiness, command forwarding and retained
availability. Any connection failure makes the bridge offline and pauses commands
until both paths recover. Manage only bridge resources: no vendor-service restart,
gateway-ping gating, local broker, implicit SSH or reboot. Defaults: 15-second MQTT
keepalive; reconnect delays 1/2/4/8/16/30 seconds, capped at 30; 1 MiB of rotated
volatile raw-event diagnostics with credentials redacted.

**Consequences:** `online` means monitored prerequisites are ready, not physical
acceptance or instantaneous loss detection. The payload verifies installed bytes,
metadata, startup integration and stock prerequisites offline. Target ABI/imports,
fresh-image startup, reconnection and end-to-end household behavior need separate
hardware acceptance. The successful observation used the installed legacy bridge
for MQTT and door commands; it does not validate the new payload. Implementation
authorization covers host-side code, documentation and offline checks, not flashing.

## ADR-014: Explicit main installation from running recovery

**Accepted 2026-11-03**, following a stopped hardware flash and the user's request
to finish recovery on the Mac.

**Context:** Alpha.3 completed recovery integrity verification and acknowledged
main-kernel invalidation, then failed to verify reconnection. Subsequent read-only
probes established matching identity, recovery state `1*0` and an idle worker.
macOS had bound recovery's ECM network function to native `en7`, rather than the
managed helper's `feth` interface. The exact original timeout cause remains
unproven. Vendor `UpdateFrwFullEth` and `DoFileTransfer` support main installation
from recovery using recovery FTP credentials.

**Decision:** Add separate `plan-recovery` (device-read-only) and `recover`
(explicit write) commands. Validate the whole FWZ, require matching recovery
identity and an immediately idle worker, then reuse the existing main filesystem,
kernel, close/settle and verified-normal-reboot sequence. Do not clear the main
kernel again or rewrite recovery. A prior report is not an authorization token;
the operator must establish that this is an appropriate new main installation,
not a retry of an uncertain main write.

For these commands, discover native Ethernet only beneath the fixed C100X USB
VID/PID in IORegistry; reject multiple devices/interfaces, configure `.2/30` and
require the destination route through that interface. If native networking
disappears, start the existing managed helper for normal-mode RNDIS. Keep helper
lifetime and signal cleanup scoped to the command. Ordinary `flash` retains its
normal-state entry. ADR-015 subsequently unifies transport across these commands
and ordinary flashing.

**Consequences:** No generic resume journal, rollback, raw-partition restore,
write retry or cleanup reboot is introduced. Recovery-mode SSH is not required.
The commands initially exist in source only, not installed alpha.3 bundles.
Offline checks and observed live results are recorded separately in ACCEPTANCE.md.

## ADR-015: One managed session for native ECM and helper-backed RNDIS

**Accepted 2026-11-03**, following successful explicit recovery installation and
the user's request to prevent the normal flasher's recovery-reconnection failure.

**Context:** The recovery-only path worked through native ECM and then the helper
after normal reboot, but ordinary `flash` still used a feth-only managed session.
An offline replay through that session and the actual reboot gate reproduced
`Reboot/reconnection was not verified` when recovery used native `en7`, even with
valid recovery identity and reset uptime. The exact original helper trace was
not retained, but this is a confirmed defect matching the observed handover.

**Decision:** Use one managed USB session for `plan`, `flash`, `plan-recovery` and
`recover`. Discover native Ethernet by C100X USB ancestry on each transport check.
Stop/reap the worker before configuring native ECM; start a new worker when no
native interface is available. Worker startup must not block native discovery:
poll feth readiness non-blockingly within bounded parent-side waiting. Preserve
USB-only routing, single-device checks for native discovery, signal cleanup,
expected identity/state, reset-uptime proof and all no-write-retry behavior.

**Consequences:** Both handover directions are supported in source. Mode/interface
changes are logged. No longer timeout or automatic flash retry is needed for this
defect. The standalone developer `usb` command remains the RNDIS helper supervisor;
`--external-usb` callers still own their transport. An uninterrupted hardware
flash with this change is pending; alpha.3 requires a new release to include it.

## ADR-016: Best-effort USB storage unmount before planned reboots

**Accepted 2026-11-03**, implementing GitHub issue
[#1](https://github.com/daniel-sc/bticino-c100x-firmware-tools/issues/1).

**Context:** C100X USB exposes storage alongside networking. Re-enumeration can
disconnect a mounted volume, producing a macOS notification even though firmware
transfers use FTP. Storage preparation must not eject the network device or alter
the researched firmware-write sequence.

**Decision:** A small standard-library host helper uses IORegistry USB ancestry
(`1da4:0056`) to select exactly one whole disk, then `diskutil list -plist` to
check whether it is mounted. Rediscover and compare USB/media registry identities
before ordinary `diskutil unmountDisk`; skip absent/unmounted storage and warn on
ambiguity, command failure or timeout. Use a ten-second total budget and maximum
five-second subprocess waits. No force, eject, persistent settings or dependencies.

Inject the helper only for `flash`/`recover`, at the central planned-reboot boundary.
Refresh the stock command session's 30-second idle timer with a read before the
bounded host work, then recheck transport and sample uptime for reboot proof.
Unmount failures warn and permit the planned sequence to continue; cancellation
still stops before reboot. No command is retried, and error cleanup never invokes
the helper or reboots the device.

**Consequences:** Offline fixtures cover identification, disk renumbering/replacement,
absent/unmounted/ambiguous storage, errors/timeouts, budgets and protocol ordering.
Hardware acceptance must separately show preserved USB control after idle unmount
and notification behavior during all three planned reboot boundaries. Failure of
this optional host step alone does not establish firmware failure.

## ADR-017: The selected SSH payload owns its service lifecycle

**Accepted 2026-11-04**, following the SSH failure investigation and the user's
selection of an independently owned image service.

**Context:** Stock `bt_daemon` starts or stops `/etc/init.d/dropbear` according to
the persistent `configuratore/setup/servizi/abil_ssh` field; an absent field means
stop. Its asynchronous initialization can race with the payload's startup link.
The failing device's saved configuration was byte-identical to its older backup
and lacked this field. Setting only `abil_ssh=1` through the vendor configuration
flow restored SSH on USB and Wi-Fi. The old volatile RSA-key generation versus
the new persistent key provides a plausible ordering change, not observed boot
timing. Selecting SSH must work independently of that persistent configuration.

**Decision:** SSH payload version 2 installs `/etc/init.d/c100x-ssh` and owns
`/var/run/c100x-ssh.pid`. Reuse stock Dropbear and the existing persistent ECDSA
host key/authentication preparation. `/etc/default/c100x-ssh` records whether
password authentication is enabled; key-only mode passes `-s`. Start on port22
on all interfaces in runlevel 5; stop in runlevels 0, 1 and 6, before networking
teardown. Support idempotent start/stop, restart/force-reload and process status.
Bound startup/shutdown waits; a failed stop prevents restart. No crash-restart
supervisor or force-kill escalation is introduced. Status establishes the daemon
process, not authenticated access or full functional acceptance.

Append `NO_START=1` to the image's `/etc/default/dropbear`. The hash-pinned stock
init script checks this before dispatching **both start and stop**, making vendor
SSH control calls no-ops. Keep that script and the daemon binary unchanged, and
do not install the old `S98dropbear` startup link. Our service never sources the
vendor defaults. This disables the vendor control path; a different service name
alone would not establish isolation.

Keep this policy entirely in the SSH image payload. Do not modify the persistent
configuration/data partition, factory defaults or flashing protocol. The selected
payload means SSH is enabled regardless of `abil_ssh`; administrators manage it
through `c100x-ssh`, not the vendor SSH switch. Rebuilding without the payload
omits this policy. No new build option or migration command is needed.

**Alternatives:** Boot-time persistent-configuration provisioning adds ordering,
write and activation responsibilities. Ignoring selected stop calls makes service
semantics ambiguous. A supervisor fights the competing owner; delays or renewed
key generation remain timing-dependent. Vendor binary patches are unnecessary.

**Consequences:** Guard and verify the disabled vendor configuration, independent
service/configuration, PID/key arguments and startup/shutdown links. Offline
checks exercise vendor-before/service-before orderings, repeated vendor calls,
authentication modes and failed startup/shutdown. Image readback checks must
reject later payloads that break ownership. Flashing and fresh-image hardware
acceptance remain separate, explicitly authorized work; the live configuration
repair does not validate the new service.

## ADR-018: Opt-in OTA prevention through coordinated startup configuration

**Accepted 2026-11-05**, following the OTA investigation and design discussion.
Originally implemented as `no-ota` v1; hardware validation is pending. ADR-019's
final approval supersedes its opt-in/main-only selection and recovery-preservation
rules with a default-on dual-image builder policy.

**Context:** Stock cloud and early-boot paths can replace the custom installation.
Deleting the dedicated installer rejects fresh requests, but persisted resume
state causes repeated launch attempts and can obstruct cloud startup. An
executable error stub can leave the manager waiting for status flags. No single
inspected configuration switch disables every normal-firmware OTA path.

**Decision:** Provide an independently selected `no-ota` image payload through
the existing builder. In the private main-filesystem copy:

- Remove `fw_manager` from the vendor application's configured process list,
  preserving other processes and contiguous XML numbering. Verify all selectable
  XML variants and optional daemon INI inputs against reintroducing it.
- Set `[Application Parameters] FwUpdate=0` in `cfg/bt_eliot`, allowing cloud
  startup without waiting for the absent updater service.
- Remove `/etc/rcS.d/S96-dedrifu.sh`, suppressing its early-boot invocation.
- Keep and verify `root/sw/dedrifu/enable=0` in both startup XML variants,
  suppressing the daemon's separate invocation.

Retain the installer binaries and init script. The payload does not delete or
rewrite staged packages or persistent update metadata. Preserve the cloud client,
ordinary household functions and explicit USB flashing. SSH and MQTT remain
independent. Update prompts may remain; download suppression is not a separate
first-version requirement. Stock/no-payload builds retain vendor behavior.

Protection covers manufacturer-initiated installation, including app-approved
and already-staged updates, while the protected normal firmware runs. Preserve
stock recovery: recovery boots and the old-main/recovery phases of initial
installation are outside the guarantee. Re-enabling OTA requires rebuilding
without `no-ota` and explicitly USB-flashing; no runtime toggle is provided.
Retained packages may become actionable in recovery or after removing prevention.

**Consequences:** Guard stock inputs and verify final image configuration so
payload composition cannot silently restore an installation path. Offline image
checks and simulated lifecycle/staged-state scenarios precede separately
authorized hardware checks of boot, cloud/app functions and USB flashing. The
accepted policy is not evidence of a validated prevention feature. Detailed
research, boundaries and implementation checks are in [OTA.md](OTA.md).

## ADR-019: Permit recovery customization for owner wireless updates

**Accepted 2026-11-06 as a design constraint change; complete design approved
2026-11-07.** The amendments below record its evolution. Source implementation and
offline validation are approved; firmware writes and hardware acceptance remain separate.

**Context:** The owner prefers source-owned update coordination over vendor-binary
patching and allows the Mac to remain connected. Stock recovery includes Wi-Fi
and update services, but no owner SSH account/key provisioned by our main-image
payload. Reusing stock OTA continuation instead would retain its signature,
state and failure-handling constraints. The owner explicitly states that leaving
recovery unchanged is not an important requirement.

**Decision:** Permit narrowly scoped customization of a private copy of the pinned
stock recovery filesystem for the owner wireless-update feature, including
administrative SSH access and its startup configuration. Preserve the supplied
originals, stock kernel/bootloader and existing USB update facilities. This
supersedes the byte-identical recovery requirement of ADR-007 and the stock-recovery
preservation choice in ADR-018 for this planned feature; it does not broaden the
implemented `no-ota` protection guarantee or the current flasher's accepted profile.

**Consequences:** The design may provision recovery access in a prepared image
before that access is first needed: the established sequence writes recovery from
running normal firmware. Existing normal-mode SSH can therefore be a candidate
for wireless bootstrap without pre-existing recovery SSH. Builder/admission rules,
recovery reference verification, credential transitions, startup ownership and
continued USB operation need corresponding design and validation. Q10 subsequently
selects the existing Mac flasher as coordinator. See [the interview record](WIRELESS-UPDATE-DESIGN.md) and
[feasibility research](WIRELESS-UPDATES.md).

**Scope clarification, 2026-11-06 (Q8/Q9):** newly built wireless-capable firmware
must prevent manufacturer-initiated installation in both normal and recovery
environments, including staged updates, while retaining the explicit owner-update
protocol. Recovery receives only built-in changes needed for owner access,
updating and prevention; ordinary main payloads such as MQTT and user applications
are not automatically applied there. Minimize complexity through reuse of
established mechanisms. The Q15 clarification below settles the existing-main
bootstrap exception. These are design requirements, not an extension of the
implemented or validated `no-ota` guarantee.

**Architecture clarification, 2026-11-06 (Q10/Q11):** reuse the source-owned Mac
flasher and established vendor sequence through SSH transport in both environments.
Require reference-driven recovery integrity verification before clearing the main
kernel and entering the new recovery environment. Reuse the existing readback
checker; its pass does not establish recovery boot or networking. These decisions
select host coordination instead of the manufacturer's OTA installer continuation;
the complete implementation design and hardware validation remain pending.

**Bootstrap clarification, 2026-11-07 (Q15):** permit the first wireless
installation from supported OTA-enabled main with existing administrative SSH.
Check for known staged manufacturer packages and active installation, rejecting
those observed conditions before starting. The owner accepts the remaining risk
of a competing manufacturer installation during both old-main phases, including
the intermediate reboot; snapshot checks do not guarantee exclusion. Require OTA
prevention in both destination images. Neither pre-installed `no-ota` nor a
separate in-place prevention migration is required. This preserves a simple
wireless bootstrap at the cost of an explicit initial protection gap; it does not
weaken the stop-on-error policy or authorize a device write.

**Policy revision, 2026-11-07 (Q18/Q19):** SSH selection will provision both main
and recovery without a separate wireless-capable build option. Manufacturer OTA
prevention remains independently optional; when selected, it covers both
environments. Wireless flashing may install packages without prevention. The
owner accepts competition risk in all unprotected update phases, with the stated
checks for staged packages and active installation. This supersedes Q8's mandatory
destination-prevention requirement and broadens the bootstrap-only exception of
Q15. Prevention is a firmware policy, not a prerequisite of SSH transport.
Keep the trusted-local-package model and authenticated SSH without introducing
owner firmware-signing infrastructure. Q20 subsequently selects default-on
prevention for customized builds.

**Builder policy clarification, 2026-11-07 (Q20):** customized builds default to
manufacturer OTA prevention in both environments, including builds without SSH.
Provide an explicit positive `--allow-vendor-updates` override and report the
resolved policy. No-payload, stock-preserving builds retain stock behavior.
Expose this as a builder policy option rather than requiring manual selection of
the ordinary `no-ota` payload. Internal reuse of prevention hooks and final checks
is appropriate; the user-facing policy change does not require a new prevention
mechanism. Legacy payload-selection compatibility remains to be specified. This
amends the planned selection model of ADR-018, not its current implementation or
hardware-validation status.

**Default revision, 2026-11-07 (Q27):** apply manufacturer OTA prevention to both
environments by default for every build, including one with no optional payloads.
This supersedes Q20's no-payload/stock-preserving exception. Use the single
`--allow-vendor-updates` opt-in to retain vendor installation behavior; no separate
explicit-block flag is needed. With no other customizations, the default build is
prevention-only; an explicitly allowed build preserves stock contents. This gives
one policy rule instead of defaults conditional on feature selection.

**Recovery-entry scope, 2026-11-07 (Q28):** the first wireless version supports
full updates starting in normal firmware. Existing USB recovery entry remains the
path after an investigated failure; a wireless `recover` entry point is deferred.
The common stop-on-error/no-automatic-retry contract continues to apply.

**Final approval, 2026-11-07:** the owner approved the [consolidated design](WIRELESS-UPDATE-PLAN.md),
including host-tool reuse, for implementation and offline validation. Replace
`--payload no-ota` outright: it was never released and needs no compatibility alias.
Source builds now apply default prevention to both filesystems, provision shared
SSH access when selected, and keep ordinary payloads in main. SSH payload v3 and
internal prevention policy v2 identify the expanded build behavior; the SSH
runtime service is unchanged from v2. Admission pins manifest/kernel and both
filesystem profiles, with additional content/access checks for wireless updates.
`plan`/`flash --transport ssh` use strict phase-specific identities and mandatory
recovery readback. Final SSH verification precedes reporting completion; destination
trust is promoted only after successful verification and completion reporting.
Static recovery analysis supports the same prevention controls. Offline results
are in [ACCEPTANCE.md](ACCEPTANCE.md); hardware acceptance is outstanding.

**Trusted-home simplification, 2026-11-07:** the owner confirmed a trusted-home
network assumption and asked to relax incidental implementation/metadata matching.
Accept existing administrative SSH without requiring the exact `c100x-ssh` service,
configuration bytes or key pathname. Establish continuity by actual authentication
with the original key and credentials across the first planned normal reboot,
before main-kernel invalidation. Missing access or a changed key stops there; no
extra test reboot or permissive key-change handling is introduced. This can admit
other working persistent SSH setups, including vendor-managed ones.

For SSH daemon/init files in prepared images, require regular executable files and
expected contents rather than exact root ownership or `0755` permissions. The
builder keeps its normal output metadata; compatible alternatives such as `0750`
and `0700` are accepted. Destination startup/content and credential admission,
vendor-component/profile evidence, target identity checks, recovery readback and
the no-uncertain-write-retry contract remain requirements. Offline checks cannot
establish future networking or SSH startup; hardware acceptance remains separate.
The daemon must retain root execution identity: non-root setuid metadata is not
an equivalent ownership variation and is rejected. Ordinary executable ownership
and permission variants remain accepted.
