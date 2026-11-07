# Owner wireless update: design interview

**Status: approved and implemented, 2026-11-07.** A subsequent complete SSH flash
and user-confirmed household tests passed; see [current coverage](ACCEPTANCE.md).
Pending statements below retain the interview's original context. Product choices
are recorded below; the [consolidated plan](WIRELESS-UPDATE-PLAN.md) collects their
current meaning and implementation details. The owner approved implementation and
offline validation, except that the unreleased `--payload no-ota` spelling is
replaced outright without a compatibility alias. Device writes remain separately authorized.
Evidence is in [WIRELESS-UPDATES.md](WIRELESS-UPDATES.md).

## Agreed requirements — round 1

- **Q1 — Initiation:** the owner explicitly selects a locally built package and
  initiates installation. Manufacturer OTA prevention was initially required;
  Q18 subsequently makes it an independent build policy. Automatic package
  discovery and scheduled installation are outside the first version.
- **Q2 — Compatibility:** support the current C100X 1.5.8-based custom builds.
  Migration to another vendor release requires separate research and support.
- **Q3 — Host availability:** the Mac may be required to remain connected for the
  whole upgrade. Autonomous completion after host disconnection is not required.
  Introduce a scoped sleep assertion only if the selected workflow needs it;
  neither a sleep assertion nor a persistent host connection guarantees delivery
  or eliminates uncertain outcomes.
- **Q4 — Physical access:** remove USB from successful routine updates. An initial
  USB bootstrap, if needed, and physical/USB investigation after a failed update
  are acceptable. Unattended remote rescue is outside the first version.

## Agreed requirements — round 2

- **Q5 — Authentication accepted:** require already-working administrative SSH,
  allowing either public-key authentication or username/password credentials.
  Public-key-only access is not a requirement. Ordinary USB flashing remains
  SSH-independent.
- **Q6 — Implementation ownership:** prefer a source-owned owner update
  coordinator, reusing established vendor mechanisms where suitable. Binary
  patches require a specific justification and separate agreement; none is
  approved. Initial implementation cost is accepted in exchange for clearer
  behavior, maintainability and testing. This does not require rewriting storage
  drivers or the bootloader. Q10 subsequently selects Mac-based coordination;
  authenticated recovery access remains a hardware-validation requirement.

## Agreed requirements — round 3

- **Q7 — Recovery customization:** the recovery filesystem need not remain
  byte-identical to stock. Permit narrowly scoped, prepared-image customization
  for owner access while preserving stock kernel/bootloader and USB update
  facilities. This scoped policy change is accepted in ADR-019. It is not approval
  to perform a device write or to implement an otherwise unsettled design.

## Agreed requirements — round 4

- **Q8 — Prevention in both environments, amended by Q18:** when selected,
  suppress manufacturer-initiated installation in both normal and recovery,
  including already-staged updates, while preserving the explicit owner-update
  protocol. The original requirement to select prevention for every wireless
  package is superseded by Q18. Q15 accepted the initial old-main prevention gap;
  Q18 extends risk acceptance to subsequent unprotected update phases.
- **Q9 — Focused recovery:** recovery receives only built-in changes needed for
  owner access, updating and OTA prevention. Ordinary main-system payloads such
  as MQTT and user applications are not automatically applied to recovery.
- **Simplicity:** minimize implementation and operational complexity. Prefer
  reusing established mechanisms and avoid adding capabilities without a concrete
  need. This preference does not itself settle verification or failure policy.

## Agreed requirements — round 5

- **Q10 — Coordinator placement:** reuse the existing source-owned Mac flasher
  and established vendor sequence, carrying control and file transfers through
  SSH in normal and recovery firmware. A second on-device coordinator is not
  required by this design. Recovery networking and tunneled transfers still
  require validation.
- **Q11 — Recovery integrity gate:** require the existing reference-driven recovery
  readback/checks before clearing the main kernel and entering recovery for a
  wireless update. This adds about 200 MiB of network
  readback and another 200 MiB of device hashing; it does not establish boot or
  networking success. It reuses the existing verifier rather than introducing
  another checking mechanism.

## Agreed requirements — round 6

- **Q12 — Failure behavior:** keep the existing stop-on-error contract, with no
  automatic write retry, resume or cleanup reboot; permit bounded read-only
  reconnection after expected reboots.
- **Q13 — Destination authentication:** use one owner SSH account/authentication
  configuration for both destination environments, supporting keys, password or
  both. It may differ from existing main access; collect required access inputs
  before the first write. Server host-key lifecycle is a
  separate decision from login credentials.
- **Q14 — Server identity:** require a trusted host key for existing main and bind
  expected destination host keys to the selected locally built package; reject
  unexpected identities rather than warning and continuing.
  Q16 and Q24 subsequently settle shared destination keys and enrollment UX.

## Agreed bootstrap exception — 2026-11-07

- **Q15 — First wireless installation from OTA-enabled main:** accept option 2.
  A supported existing main installation with administrative SSH need not already
  contain `no-ota`. Check for known staged manufacturer packages and active
  installation before starting; reject those observed conditions. These checks
  are snapshots, not an exclusive lock against manufacturer installation.
- The owner accepts the remaining competition risk during both old-main phases,
  including a manufacturer installation starting after the checks or during the
  intermediate normal reboot. The risk is not limited to a newly pushed package;
  retained/resumed installation was discussed. Its likelihood is not established.
- At acceptance, both destination environments still required OTA prevention
  (Q8), ending the exception when protected recovery ran. Q18 subsequently makes
  prevention optional and extends competition-risk acceptance to later unprotected
  phases. The stop-on-error contract (Q12) is unchanged.
- Pre-installed prevention and a separate persistent in-place SSH modification
  are not required for this bootstrap. Existing normal-mode SSH can therefore
  support the first wireless installation without prior recovery SSH or a policy
  requirement for USB. Hardware validation remains outstanding.

The original Q15 restriction and the alternative in-place prevention migration
were not selected. Accepting this risk did not authorize an actual firmware write;
final approval subsequently covered implementation and offline validation only.

## Round 7 — host identity and endpoint

- **Q16 — Destination host-key lifecycle accepted:** generate one new SSH server host key
  per build and use it in both destination main and recovery, with expected
  transitions bound to the selected package (Q14). This
  retains per-build generation while avoiding separate identities for the two
  environments. A new build intentionally changes the expected server identity.
  Explicitly confirmed in round 10 on 2026-11-07.
- **Q17 — Network endpoint accepted, 2026-11-07:** the wireless flasher and its
  read-only preflight default to `Bticino-Classe100X.local`. A single `--host`
  override accepts a hostname or IP address. Re-resolve hostnames during
  reconnection so a DHCP address change can be followed. A fixed IP or DHCP
  reservation is an available fallback. Do not add MAC-based subnet discovery
  for the first version. Name publication, collision behavior and recovery
  resolution still need hardware validation. An SSH alias whose HostName is a
  fixed IP does not provide dynamic resolution.

### Q17 scope

Connection targeting belongs to the flasher, not the offline builder. The owner
explicitly declines builder hostname customization; retain the firmware's existing
name configuration. The default is a configured mDNS name, not an automatically
discovered unique device identity. Expected SSH host-key checks remain required
(Q14). This accepted UX does not establish working recovery mDNS.

## Round 8 — build selection and package trust

- **Q18 — Independent access and update policy accepted, 2026-11-07:** selecting
  SSH adds the same owner access to both main and recovery, making these builds
  usable for wireless flashing without a separate wireless build switch. Keep
  `no-ota` independently optional; when selected it applies to both environments.
  Wireless updates may install packages without prevention. The owner accepts
  competing-manufacturer-installation risk in subsequent unprotected phases as
  well as initial bootstrap, with the stated staged-package/activity checks.
  This amends Q1/Q8 and broadens Q15. Shared login configuration (Q13), main-only
  ordinary payloads (Q9) and stop-on-error behavior (Q12) remain. Verify access
  capabilities and any selected prevention policy from image contents.
- **Q19 — Package trust accepted:** retain the trusted-local-package model: the owner
  selects a locally built package; the flasher validates its supported contents,
  derives expected destination host keys from it and uses authenticated SSH for
  transport, without introducing a separate owner firmware-signing key/service.
  Integrity checks are not proof of an untrusted package's
  provenance; local package trust is an explicit prerequisite.

## Agreed requirements — round 9

- **Q20 — Manufacturer-update default accepted, 2026-11-07:** default to
  prevention for customized builds (SSH, MQTT or other custom payloads), with
  a positive `--allow-vendor-updates` override and a visible policy in the build
  summary/report. Q27 subsequently extends this default to every build, replacing
  the original no-payload/stock-preserving exception. This is a
  user-facing builder policy option rather than a requirement to select the
  ordinary `no-ota` payload manually. It remains independent of SSH selection and
  flashing transport. The final source implementation includes Q27's revision.
- **Implementation reuse:** the builder may internally reuse the existing
  prevention hooks/checks, extending them to both filesystems. Promoting policy
  selection into the builder does not require rewriting its implementation. Resolve
  the selected policy consistently and verify it after payload composition.
  Final approval rejects legacy `--payload no-ota` compatibility;
  prevention-only builds are now the default when no other features are selected
  (Q27).

## Agreed requirements — round 10

- **Q16 — Final confirmation:** one fresh server host key per build, shared by
  destination main and recovery, with expected changes authenticated against the
  selected package. Explicitly confirmed on 2026-11-07.
- **Q21 — Transport selection:** extend existing preflight/flash commands with
  an explicit `--transport ssh` selection, retaining USB as their default.
  `--host` selects the wireless endpoint. Do not silently
  fall back between transports during an update; shared sequencing remains Q10.
  This CLI syntax was subsequently approved and implemented.
- **Q22 — Host sleep:** while wireless flashing is active, hold a scoped macOS
  idle-sleep assertion and release it when the run ends,
  using the built-in facility rather than persistent settings or a new service.
  Display sleep remains possible. This addresses idle sleep, not lid closure,
  explicit sleep, shutdown or network failure.
- **Q23 — Completion evidence:** require the final verified normal reboot,
  expected vendor identity/state and authenticated SSH with the destination key
  before reporting update completion, while retaining separate manual household
  acceptance (call, audio/video, door release and selected features).
  A connection or version string alone is insufficient;
  neither these observations nor protocol completion imply functional acceptance.

The focused offline audit is complete. Current credentials/askpass handling is
reusable, but trust files are ephemeral and user SSH-config aliases are bypassed.
Q24–Q26 settle enrollment, trust persistence/promotion and credential-transition
UX. The consolidated plan's host-key extraction and offline password checks were
approved; its compatibility-alias proposal was rejected. Q27 resolves prevention-only selection. Evidence is in
the remaining SSH workflow audit in `WIRELESS-UPDATES.md`.

## Agreed requirements — round 11

- **Q24 — Trust enrollment and persistence:** reuse an existing trusted host-key
  entry when available; otherwise show the initial fingerprint for explicit
  owner confirmation before credentials/device writes. Keep invoking-user-owned
  tool trust records and strict per-phase checking; after successful final
  verification, remember the destination key for subsequent invocations without
  automatically editing the user's general SSH known-hosts file.
  Unexpected changes to an already trusted identity still
  stop the run. Expected package-derived changes are automatic during the run;
  a failed update is not evidence for promoting its destination as current main.
- **Q25 — Credential convenience:** reuse existing-main login settings for the
  destination by default, with explicit destination overrides for rotation. Check
  the selected destination authentication against both images before writing,
  keep login passwords in memory for the run and do not persist them.
  Offline compatibility checks do not prove service startup
  or future agent availability; actual authentication is checked at each phase.
- **Q26 — SSH configuration scope:** in v1 accept actual DNS/mDNS hostnames or
  IPs through `--host` and explicit login options plus the SSH agent, without
  interpreting arbitrary user SSH-config aliases, proxies or jump hosts.
  Alias support would add configuration semantics beyond
  today's SSH reader, which explicitly bypasses user config.

## Agreed requirements — round 12

- **Q27 — Universal prevention default, revised and accepted:** block manufacturer
  updates in both environments by default for every build, including builds with
  no selected SSH, MQTT or custom payloads. This supersedes Q20's stock-preserving
  exception and makes an extra `--block-vendor-updates` flag unnecessary. A build
  with no optional features is now prevention-only; a stock-preserving build
  explicitly selects `--allow-vendor-updates` and no custom payloads. The owner
  prefers this uniform rule to conditional defaults. Final approval explicitly
  rejected a compatibility alias for the unreleased `--payload no-ota` spelling;
  source implementation now rejects that selection.
- **Q28 — Wireless recovery scope:** limit v1 wireless commands to full updates
  starting in normal firmware, retaining existing USB recovery entry for
  investigated failures rather than adding a wireless `recover` entry point.
  Accepted for initial scope. Physical/USB fallback is accepted (Q4);
  adding explicit wireless recovery later would need its own current-recovery
  identity/admission contract. This does not change Q12's stop-on-error behavior
  or make a failed report an authorization to retry.

Recovery-specific cloud startup under prevention has been traced offline. Its
relevant control flow matches main, so the same four-part suppression policy
applies with recovery-specific verifier pins and its own startup script retained.
Hardware validation remains separate from implementation approval: confirm recovery Wi-Fi,
SSH, Bonjour, selected prevention, USB operation and household functions in
authorized maintenance, with failure injection restricted to simulation.

## Design closure and implementation follow-through

Q1–Q28 and the consolidated plan are approved, including the later amendments and
host-tool reuse. The owner rejected retaining the unreleased `--payload no-ota`
spelling; no compatibility alias is provided. Exact source interfaces, input
bounds and tests are implementation work within that plan. If validation exposes
a need to change agreed behavior, return to the affected decision rather than
silently expanding scope.

### Clarified bootstrap dependency

The researched vendor sequence writes recovery while normal firmware is running.
Consequently, the host-driven wireless implementation can start with SSH
access to **normal firmware only**, install a prepared SSH-enabled recovery image,
then use recovery SSH after the transition. Recovery SSH need not pre-exist the
update. Initial USB installation is not an inherent protocol prerequisite when
usable normal-mode administrative SSH already exists; it remains a bootstrap
option when access is absent and a means of hardware validation/recovery.

The existing-main audit found no evidenced persistent temporary inhibition
covering its two phases. Q15 accepts admission of supported OTA-enabled main with
the stated checks and prevention gap; pre-installed `no-ota` is not required.

This is a design inference from the established sequence, not a validated wireless
bootstrap. Recovery customization is now permitted by Q7/ADR-019, but actual
device changes have not been authorized. Both normal and recovery access are
needed at their respective phases. Source tools now implement this path; hardware
acceptance remains pending.

- **Access and implementation prerequisites**
  - SSH authentication methods and connection/configuration UX are settled.
  - Source-owned coordination is preferred; binary adaptation is not the default.
- **Execution architecture**
  - Mac-driven vendor protocol over SSH is selected (Q10); transport session
    lifetime, service readiness and reconnection are implemented in source.
  - Recovery customization is limited to owner access, updating and prevention,
    with ordinary payloads kept in main.
- **Failure contract**
  - Host stop-on-error behavior is preserved (Q12). The selected path
    does not use the stock OTA installer's continuation/retry state machine;
    that research no longer blocks a retry-policy decision for this architecture.
- **Trust and transaction ownership**
  - Trusted local packages without additional signing infrastructure are accepted
    (Q19); exact content admission checks, key lifecycle and staged-byte integrity
    are implemented and exercised offline as specified in the consolidated plan.
  - Shared destination login configuration and host-identity binding are settled
    (Q13/Q14), as is per-build shared host-key lifecycle (Q16). Credential reuse,
    initial host enrollment, trust persistence and SSH config scope are settled
    by Q24–Q26. Q17 settles endpoint selection; runtime behavior remains to be
    validated.
  - Competing vendor launchers and composition with `no-ota`; the Mac owns the
    explicit sequence and uses the existing per-file transfer mechanism.
  - Prevention is optional and, when selected, covers both destination environments
    (Q18), defaulting on for every build (Q27). Exact supported-main eligibility
    and staged/active manufacturer-installation detection are specified in the
    consolidated plan and exercised offline.
- **User workflow and evidence**
  - Preflight/start/result interface, bootstrap eligibility and destination-image
    requirements; bounded host transport/reconnection and scoped idle-sleep handling.
  - Offline integrated lifecycle evidence and separately authorized hardware
    validation; completion evidence and functional acceptance.
  - Recovery integrity verification is mandatory (Q11); its evidence remains
    distinct from recovery boot verification.

ADR-019 supersedes the recovery-preservation constraint and records final approval.
Source implementation now includes these changes, retaining the stop-on-error
contract. [ACCEPTANCE.md](ACCEPTANCE.md) distinguishes offline results from pending
hardware evidence.

### Post-implementation simplification — trusted home network

The owner requested relaxing exact implementation/metadata checks. Existing-main
SSH may use another working startup arrangement; actual administrative access and
same-key reconnection after the planned normal reboot establish eligibility.
SSH daemon/init metadata may vary while remaining executable regular files with
expected contents. Target identity, recovery readback, destination access checks
and no uncertain-write retries remain required. The consolidated plan and ADR-019
record this revision.
