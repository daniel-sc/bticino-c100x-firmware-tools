# Architecture decision records

Recorded retrospectively on **2026-10-28** from the implementation and project
discussion. All records below are **accepted**; acceptance describes the design
choice, not successful hardware flashing. Keep these IDs stable and record a
superseding decision if the approach changes.

## ADR-001: Preserve the existing image and restrict compatibility

**Status update, 2026-10-28:** firmware-creation scope and whole-archive admission
are superseded by ADR-007. Original preservation and device checks still apply.

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
detection, reconnect and cleanup. Pin details are in [FLASHING.md](FLASHING.md).
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
this implementation. There is no recovery-skip or main-only shortcut. The six
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
