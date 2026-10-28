# Architecture decision records

Recorded retrospectively on **2026-10-28** from the implementation and project
discussion. All records below are **accepted**; acceptance describes the design
choice, not successful hardware flashing. Keep these IDs stable and record a
superseding decision if the approach changes.

## ADR-001: Preserve the existing image and restrict compatibility

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
detection, reconnect and cleanup. Pin details are in [../README.md](../README.md).
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
