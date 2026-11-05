# Validation history through 2026-11-05

Historical evidence and test plans. For current passed/open items, use
[ACCEPTANCE.md](ACCEPTANCE.md). Pending statements, commands and checklists below
describe their recording date; later entries may supersede them. Use
[FLASHING.md](FLASHING.md) for current instructions.

**Status through 2026-11-05:** alpha.6 completed an uninterrupted full native USB
flash with RNDIS → ECM → RNDIS handover. The new SSH-v2 service accepts RSA-key
logins over Wi-Fi and survives vendor start/stop calls, including fresh connections
afterward. Fresh USB and Wi-Fi SSH logins also passed after removing the vendor
SSH-enable setting and rebooting, with unchanged host identity. Password-only
authentication and own-service restart also passed. The user confirmed the
MQTT/household checklist working. This validates the tested modified-to-modified
installation; stock-device acceptance and broader resilience checks remain separate.

The entries below are dated evidence and maintainer test plans, not current setup
instructions. Older commands describe earlier workflows; use [FLASHING.md](FLASHING.md)
for the current one.

## 2026-11-05: Version 0.1.0 release preparation

- Added stable tag publication alongside alpha prereleases. Stable tags select
  GitHub's latest release; alpha tags retain prerelease status without replacing
  latest. Replaced alpha-specific notes with a short first-release introduction
  and documented concise, user-facing notes for future releases.
- Exercised the workflow's actual shell blocks with valid/invalid version tags
  and a stubbed GitHub command: stable/alpha selection and release-note arguments
  passed without publishing. Current offline results are recorded below.
- Hardware acceptance is carried forward under ADR-011. No new device flash is
  required for the current documentation, publication and best-effort host-storage
  changes. Candidate CI and published-artifact results will be recorded after
  observation.

## 2026-11-05: Release-readiness documentation and offline checks

- Rechecked the current source with `mise run test`: **189 tests, 186 passed,
  3 optional native MQTT tests skipped**. Ran `test_mqtt_runtime.py` separately
  with the existing host libmosquitto 1.4.14 fixture: **7 passed, no skips**,
  including the three native tests.
- GitHub has no open issues, but its latest successful package/release runs are
  for alpha.6 commit `a833f9e`. The subsequent storage fix has no recorded packaged
  CI run. The workflow still accepts alpha tags only and publishes prereleases.
- Consolidated current passed/open items in [ACCEPTANCE.md](ACCEPTANCE.md) and
  removed completed investigation steps from the user-facing flash guide.
  No device access, unmount, firmware write or reboot was performed.
- User clarified release policy: trivial changes should not require repeated
  device flashes. Recorded change-based validation in ADR-011 and RELEASING.md;
  existing acceptance carries forward for unchanged behavior. Live storage,
  stock-to-modified and additional MQTT/SSH coverage remain disclosed follow-ups.

## 2026-11-05: USB storage discovery correction

- Read-only host inspection found the C100X volume mounted, but the existing
  `ioreg -a -r -c IOUSBHostDevice` output omitted child media's `Whole` and
  `BSD Name` properties. A replay reproduced the helper silently skipping unmount.
- Storage discovery now requests child properties with `-l`; incomplete media
  identity warns rather than being treated as absent storage. Two regression tests
  failed before the fix and pass afterward, including the observed whole-disk mount
  layout and command-dependent property visibility.
- `mise run test`: **189 tests, 186 passed, 3 optional MQTT native ABI tests skipped**.
  No actual unmount, firmware write or reboot was performed. Preserved networking
  after unmount and notification behavior across all three reboots remain pending.

## 2026-11-05: Alpha.6 full flash, SSH failure-condition test and functional checks

- User supplied alpha.6 build/preflight/flash output for `custom-alpha6.fwz`,
  SHA-256 `11c16ecac3c160126832914dfca3141ef7e872f553f984156a6efd8bfb99b48e`.
  SSH payload v2 and MQTT payload v1 passed final offline verification.
- Preflight reported expected hardware/model, normal state `4*0`, matching image
  hash and no firmware writes. Ordinary flash (without optional SSH recovery
  verification) completed all four transfers and three reboot boundaries, with
  helper `feth0` → native ECM `en7` → helper `feth0` handover and final sequence
  completion. This establishes uninterrupted protocol completion, not full
  installed-filesystem readback or household acceptance.
- Wi-Fi login as `root2` reported UID/GID 0. Installed defaults report
  `PASSWORD_AUTH=1`, vendor `NO_START=1`, and `c100x-ssh` status reports running.
- Vendor `/etc/init.d/dropbear stop` and `start` both left the independent service
  running. After each call, a fresh batch-mode RSA-key SSH connection succeeded
  with strict checking against the newly recorded host key. Observed fingerprint:
  `SHA256:5NzBl4hqMriVNAsu2Mx+Kk1mCVckZp23VnY1a87ihJU`.
- The initial observations above are user-provided terminal output. This was
  modified-to-modified flashing, not stock-device acceptance.
- Subsequent maintainer checks authenticated over USB with the same strictly
  checked host key. A fresh checksum-verified export contained `abil_ssh=1` and
  exactly matched runtime XML. Prepared/readback-verified a configuration archive
  removing only that field, preserving every other XML byte, and applied it once
  through the evidenced vendor flow. Begin/apply/normal-close all ACKed.
- The immediate post-apply export still contained the old setting; after the
  application persisted the change, a subsequent verified export exactly matched
  the prepared XML with `abil_ssh` absent. Runtime XML also matched, and fresh
  RSA-key logins on USB and Wi-Fi still reported `c100x-ssh: running` with the same
  host key and unchanged boot ID. No full reboot was sent during this step.
  Private backups, prepared archive, one-shot journal and readback evidence are
  under `.local/ssh-diagnosis-20261104/absent-ssh-policy-6cohq2g7/`; final saved
  export is `live-config-2f3bm08r/` beside it.
- User then requested a normal reboot and reported a successful strict-host-key
  RSA login over Wi-Fi with service running and uptime 89.45 seconds. Boot ID
  changed from `e2033585-c416-41f9-b0e5-a8bfb00bc02a` to
  `82a2cefc-4efe-413a-a08b-95536cf9d0d3`.
- Independent fresh RSA-key connections over USB and Wi-Fi confirmed the same
  new boot ID, running service and unchanged host key. Post-reboot runtime XML
  exactly matches the prepared configuration with `abil_ssh` absent. This passes
  the original disabled-policy boot-condition test and host-identity persistence
  for this image. Private results are in `after-reboot.json` in the prepared
  directory above.
- User verified password-only authentication with public-key authentication
  disabled and strict host-key checking: UID/GID 0 and service running. A key-
  authenticated invocation of `/etc/init.d/c100x-ssh restart` reported the old
  listener stopped and service running afterward. A subsequent fresh password-
  only login again succeeded, establishing listener availability after restart.
- In response to the final checklist (doorbell/ringing and usual notification,
  answering/video/two-way audio, door release, fresh MQTT events and existing MQTT
  door control where used), the user reported **"its all working"**. Record this
  as user-confirmed functional acceptance of this installation; no separate MQTT
  capture or per-action timestamps were collected. Broader MQTT disconnect/reconnect
  behavior and stock-to-modified acceptance were not exercised in this walkthrough.

## 2026-11-04: Alpha.6 publication and downloaded-bundle validation

- Committed/pushed the independently reviewed changes as
  `a833f9e92316f698bd5853e79e860c5e0b3668f9`. Main CI `41908753233` passed
  offline tests, USB helper build/tests and candidate packaged checks. Tagged
  `v0.1.0-alpha.6` at that commit; release CI `41910819831` passed signing,
  notarization, stapling and publication at **21:05:47 UTC**.
- Downloaded all published assets and verified every SHA-256. DMG SHA-256:
  `77f12ca0fdfed25b080f549f7eea0abd286519b97b5dca6be842d36068da954e`.
  Gatekeeper accepted Notarized Developer ID; the stapled ticket validated.
  Copied the bundle from a read-only DMG and detached it.
- All **84 native files** passed strict Developer ID signature/team checks.
  Manifest matches the release commit, arm64 and macOS **15.0** minimum. CLI
  reports alpha.6; shipped SSH-v2 payload files match the reviewed source. Bundled
  guides include SSH lifecycle verification. Relocated packaged smoke passed.
- The actual downloaded CLI built an SSH-v2 image from pinned stock successfully,
  including filesystem and final archive/payload readback checks. Private result:
  `.local/ssh-diagnosis-20261104/alpha6-bundled.fwz`, SHA-256
  `da10ee3d9d23642c08623bc99888a364e4a9e077c561c8d35eeefd5f99609ea9`.
- Updated/pushed Homebrew cask version/checksum in tap commit `fdf626a`.
  Strict audit/style passed. Because the user's alpha.5 cask was installed,
  verified installation through a temporary renamed smoke cask and app directory:
  PATH-linked alpha.6 version, builder tools, launcher signature and SSH-v2 assets
  passed. Removed that test installation/cask; the user's alpha.5 was preserved.
- Release verification was host-only. No new image has been flashed; failure-state
  boot verification and household checks remain pending. Keep working vendor
  `abil_ssh=1` through the old-image/recovery stages; exercise the disabled setting
  only after verifying the new image's independent service.

## 2026-11-04: Independently owned SSH image service (offline)

- Implemented SSH payload version 2 and ADR-017: `c100x-ssh` owns its defaults,
  PID file and runlevel-5 startup/runlevel-0/1/6 shutdown. The unchanged stock
  Dropbear init script is disabled for both start and stop through image-local
  `NO_START=1`. Persistent device configuration is not edited by this payload.
- The full native-MQTT-enabled offline suite passed **187 tests, no skips**.
  Shell lifecycle tests execute the new script with simulated process control:
  vendor/service ordering, repeated vendor calls, idempotent start/stop, restart,
  key-only/password flags, missing-key/launch failure and bounded failed stop.
  Synthetic image tests cover all authentication modes and reject later payloads
  that reenable vendor control or remove the shutdown link.
- Also replayed the actual hash-pinned vendor init script with rebased paths and
  mocked process effects. Both startup orderings and repeated vendor
  start/stop/restart calls preserved the independent service. A negative control
  changing `NO_START` back to zero reached process control and was detected by
  the isolation assertion. No ARM binary or live device was used in these checks.
- A real offline SSH-v2 build from pinned stock passed filesystem checks, payload
  verification and final archive reopen/readback. Generated FWZ SHA-256:
  `8cdc2632459f09905b1de8d59573e752b24c9e1f7b6316e82827a754c8db2ade`.
  Private image/report/log remain under
  `.local/ssh-diagnosis-20261104/owned-service*`; this key-only validation image
  has not been flashed.
- Two fresh, independent standards/spec reviewers reported no actionable findings.
  Each independently passed the four SSH lifecycle tests and 29 builder tests;
  neither accessed hardware or edited project files.
- Fresh-image boot, actual BusyBox process matching, lifecycle behavior across
  vendor application restarts, authentication and a full reboot remain hardware
  acceptance work. The earlier live configuration repair validates a different
  startup arrangement.

## 2026-11-04: SSH restored through vendor configuration

- User authorized restoring SSH on the current device and started managed USB.
  A fresh checksum-verified configuration export matched the earlier backup.
  Prepared an encrypted `conf.zip` adding only `<abil_ssh>1</abil_ssh>` under
  `configuratore/setup/servizi`; all existing XML bytes were preserved. Verified
  archive encryption/compression and decrypted readback before device access.
- After matching identity/state `4*0` and idle-worker checks, used the evidenced
  vendor configuration sequence: begin `#30`, FTP upload, length/POSIX-checksum
  apply `#32`, worker-readiness query and normal close `#33`. All commands ACKed;
  no write was retried. No firmware write or explicit reboot/restart was sent.
- Both USB and Wi-Fi then returned `SSH-2.0-dropbear_2017.75`. The existing RSA
  identity authenticated as `root2` with UID/GID 0 over both interfaces, ignoring
  user SSH configuration and strictly checking the host key derived from the image.
  Firmware-copy flag was `1`; uptime continued without a full device reboot.
- A subsequent checksum-verified export exactly matched the prepared XML. Runtime
  `/var/tmp/conf.xml` also contains `abil_ssh=1`; listeners exist on IPv4 wildcard
  and IPv6 wildcard port22. This demonstrates that changing the vendor SSH policy
  restores access. The earlier boot-race ordering itself remains inferred.
- Private backups, prepared archive, no-repeat apply journal and login evidence
  are under `.local/ssh-diagnosis-20261104/enable-ssh-695luyyw/`; fresh pre/post
  exports are `live-config-1a7a9xcb/` and `live-config-n_h84oj2/` beside it.
  Password authentication, persistence across a later full reboot and household
  functional checks were not exercised in this repair. The builder payload still
  needs a general lifecycle fix for devices with stock SSH-disable configuration.

## 2026-11-04: SSH refusal and saved-configuration export

- Wi-Fi TCP22 refusal was independently reproduced at the router-confirmed device
  address. The user then observed USB TCP22 refusal with managed RNDIS ready;
  a subsequent direct USB check reproduced it. Authentication was never reached.
- Traced the vendor configuration-export sequence through matching device code
  and MyHOME BTESUXP. With user-authorized USB access, verified matching normal
  identity/state `4*0` and idle worker, requested export, retrieved `conf.zip`,
  verified device-reported length/POSIX checksum and received export-close ACK.
  This stages a temporary file and starts/stops FTP; it is not a strictly
  side-effect-free query. No configuration apply, firmware write or reboot was sent.
- The exported configuration XML is **byte-identical to the October 27 backup**;
  `configuratore/setup/servizi/abil_ssh` is absent. Post-export uptime advanced
  normally, state remained `4*0`, worker remained idle and USB TCP22 still refused.
- Matching vendor code defaults an absent `abil_ssh` to zero and requests SSH
  stop during initialization. Its asynchronous startup races with `S98dropbear`.
  An offline replay of the real init script with mocked service effects confirmed
  order-dependent listener state. The new persistent key skips legacy volatile
  RSA-key generation, providing a plausible timing change. Actual boot ordering
  and runtime logs remain unobserved; the export reads saved configuration, not RAM.
- Offline analysis found a valid ECDSA key, compatible key encoding and compiled
  ECDSA support, wildcard port22 configuration and firewall rules allowing SSH.
  The stock ARM executable was not executed. Missing SSH is the likely explanation
  for the old alpha.4 preflight failures, whose discarded stderr remains unavailable.
- Private image analysis, reproducer and acquisition helper remain under
  `.local/ssh-diagnosis-20261104/`; verified export/report are in
  `live-config-8hdh_loq/` beneath it. These contain private device configuration.

## 2026-11-04: Alpha.5 publication and downloaded-bundle validation

- Tagged **v0.1.0-alpha.5** at reviewed commit
  `adf4df91db8f0ffdfccdd737e774596194083aab` after main CI passed. Tagged
  workflow `41836811783` passed offline tests, helper build/tests, package checks,
  Developer ID signing, notarization and stapling. Published the
  [alpha.5 prerelease](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.1.0-alpha.5)
  at **13:26:30 UTC**.
- Downloaded all assets; every SHA-256 checksum matched. Published DMG SHA-256:
  `33a08dc2123bbf5d8426a714c476775a2909189eab2c0f119fe1150b56618ba2`.
  Gatekeeper accepted Notarized Developer ID and the stapled ticket validated.
  Mounted read-only, copied the bundle, and detached the DMG.
- All **84 native files** passed strict Developer ID signature/team checks.
  Provenance matches the reviewed commit, arm64 and minimum macOS **15.0**.
  Copied CLI reports alpha.5; Python modules match the checkout. Bundled README
  and guides include diagnostics and Homebrew installation instructions.
- The downloaded copy passed relocated `packaging/smoke.py`, including diagnostics,
  SSH, USB/storage, updater and CLI simulations. A real missing-file CLI invocation
  also confirmed `--debug` traceback/error output. Assets and copied bundle remain
  private under `.local/downloaded-alpha5/`.
- Updated the public Homebrew tap to alpha.5 and the published DMG checksum in
  `4029328`. Strict cask audit/style passed. Installed into a temporary application
  directory, verified PATH-linked `c100x --version`, builder-doctor capabilities
  and launcher signature, then removed the test install and temporary PATH link.
  The existing `/Applications/C100X` installation was preserved.
- No hardware access, storage unmount on the intercom, firmware write or reboot
  was performed. Uninterrupted flashing, USB-storage notification observations,
  detailed functional acceptance and the earlier SSH failure diagnosis remain pending.

## 2026-11-04: Alpha.5 independent review and candidate checks

- Two fresh, independent standards/spec reviewers found a USB worker regression:
  a builder-doctor local named `text` shadowed the diagnostic formatter used by
  the worker callback. An actual worker-entry regression reproduced the failure;
  renaming the local fixed normal diagnostic/readiness and exception JSON output.
- The spec reviewer also found that truncated SSH acquisition could hide the
  process exit status. Failure annotations now retain the available status before
  teardown; a fake SSH process confirms exit 7, short output and `dd` stderr all
  survive together.
- Both reviewers verified the fixes and reported no remaining actionable findings.
  Each independently ran 32 CLI, SSH and diagnostics tests successfully. The full
  native-MQTT-enabled suite passed **183 tests, no skips**. Packaged smoke includes
  the shared diagnostics tests and actual worker-entry regression.
- Alpha.5 notes and the existing Homebrew setup/release documentation were reviewed
  against the implementation and public tap. Candidate/release publication and
  downloaded-bundle verification are recorded separately after completion.
- Committed and pushed the reviewed candidate as
  `adf4df91db8f0ffdfccdd737e774596194083aab`. Main CI `41835761805` passed
  offline tests, the pinned helper build/tests and relocated packaged smoke checks.
- A real offline no-payload build from pinned stock passed all checks. Its main
  filesystem SHA-256 remains
  `80f04c61a9a34032e397d1dc6a1209ad029162a59d08981d7fd9f81348264354`;
  generated FWZ SHA-256 is
  `4b729d4700fcdc4609c999b2fea3f924ab396270691e292480f7c4303d4edd96`.
  Private image/report/log remain under `.local/alpha5-noop*`.
- No hardware access or device-changing operation was performed during this review.

## 2026-11-04: Failure diagnostics (offline)

- Implemented shared cause/note/traceback diagnostics across CLI, SSH, recovery
  verification, FTP/update polling, USB supervision/storage, downloads, archive
  validation and builder tools/hooks. Recovery failure reports and explicitly
  requested build failure reports retain stacks independently of `--debug`.
- Added five focused tests for shared formatting, CLI traceback behavior and USB
  diagnostic forwarding; extended existing SSH, FTP, build/report and recovery
  tests to check retained details and known-password removal. The full offline
  suite with the native MQTT fixture library passed **182 tests, no skips**.
- Manually exercised source CLI failures with missing input paths, `--debug`
  before/after the command, an unavailable localhost probe (observed timeout),
  and an intentionally failing host-tool fixture. Confirmed its build failure
  report contains stage/traceback, is mode 0600, creates no image, and cannot be
  overwritten by a later attempt.
- Executed the SSH prerequisite script through local `/bin/sh` with simulated
  UID and firmware-copy reads; both failures retained exit 1 and named the exact
  failed check. Temporary fixtures were removed. `git diff --check` passed.
- No intercom access, firmware write, reboot or hardware acceptance was performed
  for this change. The two earlier live SSH preflight failures remain undiagnosed;
  their original stderr cannot be reconstructed from the old reports.

## 2026-11-04: Homebrew cask installation and upgrade

- Published `daniel-sc/homebrew-tap` with the alpha.4 signed-DMG cask.
  Homebrew strict audit and cask style checks passed.
- Installed through the public tap into a temporary application directory and
  verified the PATH-linked `c100x --version`. Installed alpha.3, then successfully
  upgraded through Brew to alpha.4; bundled `builder-doctor` checks and strict
  launcher signature verification passed after the upgrade.
- Validation used host-only commands. The existing `/Applications/C100X` manual
  installation was preserved; no device connection, write or reboot was performed.

## 2026-11-03: Alpha.4 publication and downloaded-bundle validation

- Pushed reviewed implementation at
  `64f05c27a88714addf87c782cb9d2d4148766cb4`. Main CI run `41724341757`
  passed the full offline suite, pinned helper build/tests, relocatable package
  assembly and expanded packaged smoke checks.
- Tagged **v0.1.0-alpha.4** at that commit. Release CI run `41725306574`
  passed, including signed-bundle smoke tests, Developer ID signing, notarization
  and stapling. Published the
  [alpha.4 prerelease](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.1.0-alpha.4)
  at **21:57:35 UTC**, with the DMG, dependency sources, provenance and checksums.
- Downloaded all assets and verified every SHA-256 checksum. DMG SHA-256:
  `4a05039e1da0202a049d5de18e2c42e45ec22c05542eb3c230115bce86101ee4`.
  Gatekeeper accepted it as Notarized Developer ID and its stapled ticket passed
  validation. Mounted read-only, copied out the bundle and detached the DMG.
- All **84 native files** passed strict signature verification and the expected
  Developer ID team check. Copied CLI reports `v0.1.0-alpha.4`; provenance points
  to the reviewed commit, minimum macOS **15.0**, architecture arm64. Changed
  implementation modules match the checkout, and the bundled guide includes
  installed recovery-command usage.
- The downloaded bundle passed `packaging/smoke.py`: relocated path with spaces,
  fresh HOME/system-only PATH, shipped tools/hooks/SSH IPC and the new USB,
  storage-unmount, updater and CLI simulations. Downloads and the copied bundle
  are private under `.local/downloaded-alpha4/`; `/Applications/C100X` was not
  replaced. No device connection, storage unmount, firmware write or reboot was
  performed during release validation.
- Pending hardware work remains the uninterrupted full flash, idle-storage
  unmount/network check, notification behavior across three reboots and detailed
  functional acceptance. Issue #1 has the implementation and validation update;
  its hardware observations remain open for the next authorized run.

## 2026-11-03: Alpha.4 pre-release review and issue #1

- Two independent, initially unprimed reviewers found the same cancellation gap:
  a signal during live helper handover could interrupt `ExitStack` teardown.
  A regression failed for SIGINT/SIGTERM/SIGHUP before the fix and passed after
  deferring cancellation until bounded worker cleanup completes. The reviewer
  verified the fix and found no remaining substantive issue in that change.
- Implemented issue #1's USB-associated, dynamic, ordinary best-effort storage
  unmount with a ten-second total budget. Tests cover identification, ambiguity,
  disk changes, absent/unmounted media, command failures/timeouts, cancellation
  and ordering at each planned reboot. User documentation and ADR-016 record the
  warning-only policy and hardware limits.
- With USB disconnected, observed that `ioreg -a -r -c IOUSBHostDevice` can emit
  empty output instead of a plist. Both discovery paths now treat that as absence;
  network discovery then waits for transport rather than failing plist parsing.
- A fresh independent release review found only the then-missing issue #1 user
  documentation, now added. The full suite with the native MQTT fixture library
  passed **177 tests, no skips**. Packaged smoke checks now also run USB handover,
  storage, updater and CLI simulations using the relocated bundled interpreter.
- Hardware was disconnected before storage-helper work. **Pending:** idle-device
  unmount followed by read-only USB probing; notification observation across all
  three reboots in a separately authorized full flash. No hardware unmount,
  firmware write or reboot was performed for this issue's implementation/review.

## 2026-11-03: Main installation completed; unified USB handover regression

- The user supplied successful source `plan-recovery` output for the same image
  SHA-256 `b22897d4c69f504ef0f91d3974f9967b4b1407a32152c261489dd302cb8c9cf8`.
  It records matching recovery state `1*0`, uptime 17:15, an idle worker and
  `device_writes: false`.
- The subsequent user-run `recover` log records main filesystem upload/write,
  kernel upload/write, reboot, managed helper readiness and **Update sequence
  completed**. That message is emitted only after verifying normal identity/state
  `4*0` and reset uptime. The main filesystem came from the selected custom FWZ;
  the shared kernel remains the stock-pinned component by design.
- This establishes protocol completion across the original stopped flash plus
  explicit recovery entry, not a successful uninterrupted alpha.3 flash or a
  full main-filesystem readback. The user reports "all good"; individual calling,
  audio/video, door-release and new SSH/MQTT checks have not been reported.
- An offline replay through the real `NetworkDevice.reboot_and_wait` and managed
  USB session reproduced the exact original error with a valid recovery reply
  and the observed native `en7` route. The feth-only session rejects the native
  route. Unified transport handling now discovers native ECM while the helper is
  waiting, stops/reaps the old helper before using ECM and starts a fresh helper
  when normal RNDIS returns. Identity, route, reset-uptime and no-write-retry
  requirements remain in force (ADR-015).
- Regression tests cover the complete RNDIS → ECM → RNDIS handover, worker
  cleanup, exactly one reboot request and ECM appearing before a helper reports
  any feth interface. The fix was tested offline; no additional device write or
  reboot was performed to test it. Installed alpha.3 remains unchanged.
- Final `mise run test`: **165 tests, 162 passed, 3 optional MQTT native ABI tests
  skipped**. The previously failing handover replay passes with exactly one
  reboot request and both helper processes reaped. `git diff --check` passed.

## 2026-11-03: Stopped alpha.3 flash and live recovery assessment

- User ran installed alpha.3 against `~/klingel-fw/custom.fwz` with optional
  existing-SSH verification. Image SHA-256 is
  `b22897d4c69f504ef0f91d3974f9967b4b1407a32152c261489dd302cb8c9cf8`;
  a subsequent complete offline source inspection passed with the same hash.
- The supplied log records recovery filesystem/kernel transfers, a verified
  normal reboot, successful SSH readback, acknowledged main-kernel invalidation,
  then failure to verify the reboot/reconnection into recovery. No main upload
  appears in that sequence.
- Private report `~/klingel-fw/c100x-verification-20261103T205438Z-i754cv4k/report.json`
  records passed preflight and integrity verification, matching rootfs/kernel
  contents, independent partition hashes and filesystem checks, with update outcome
  `stopped` at `entering recovery: rebooting`. Raw copies were removed. Its changed
  SSH host-key warning did not block the integrity check.
- Subsequent live read-only probes returned device 200, firmware 1.5.8, hardware
  `02*06*0`, model `1.0.99`, state `1*0`, and advancing recovery uptime (first
  observed 5:26). A later query 42 ACK established an idle update worker.
- Host IORegistry shows USB `1da4:0056` with an AppleUserECM Ethernet interface,
  native `en7` at `192.168.129.2/30`; the device route uses that interface. This
  establishes recovery boot/control availability after the failed reconnection
  gate. The exact cause of the earlier timeout is not yet proven.
- Added source-only `plan-recovery`/`recover` under ADR-014. Offline simulations
  cover main-only ordering/credentials, wrong state/identity, busy entry,
  disconnection at each step, native USB ancestry/routing and transition to the
  existing helper. `mise run test`: **163 tests, 160 passed, 3 optional MQTT native
  ABI tests skipped**. No write/reboot was sent during this follow-up assessment;
  running the recovery command and functional acceptance were pending at this point.

## 2026-10-31: Alpha.3 publication

- Pushed implementation/review fixes at
  `abf6e689f2e0abeb0ff43ab5ef97e9b7b432629f` and tag **v0.1.0-alpha.3**.
  Main CI run `41242378564` passed the offline suite, native MQTT fixture tests,
  pinned helper build/tests, package assembly and relocated smoke checks.
- Tagged release run `41242378394` also passed, including Developer ID signing,
  notarization and stapling. Published
  [alpha.3](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.1.0-alpha.3)
  at **21:16:23 UTC**, with the arm64 DMG, dependency sources, provenance and checksums.
- Downloaded all published assets and checked SHA-256, version and source commit.
  DMG SHA-256:
  `bf58bd3a120195c6f2ecdaa5a3a5fb6cbfa754ee8ca862df2a66ff8fd9839787`.
  Stapler validation passed; Gatekeeper accepted it as Notarized Developer ID.
  Mounted read-only, copied the bundle and detached the image. All **84 native
  files** passed strict signature and expected Developer ID team checks.
- The downloaded bundle passed relocated smoke checks with system-only PATH,
  including bundled MQTT assets and host configuration code. Minimum OS is
  **macOS 15.0**, arm64. Private downloads are in `.local/downloaded-alpha3/`.
- The downloaded CLI, with system-only PATH, built a real pinned-stock MQTT+SSH
  image using disposable credentials. Filesystem checks, payload verification,
  packaging and reopened-image verification all passed. Output
  `.local/alpha3-image-validation/mqtt-ssh.fwz` has SHA-256
  `3cb8084e7bfdfc80461ac94ffeed46e27deb8538bd988d9bc7bdfdab163ba407`;
  an independent reread matched its report. Output mode is 0600 and the original
  stock hash remained unchanged. No intercom or household-broker connection,
  firmware write or reboot occurred during these release checks.

## 2026-10-31: Optional MQTT payload — offline implementation validation

- Implemented the explicitly selected `mqtt` payload under ADR-013, with private
  build-time configuration, stock-runtime ctypes bindings, public-monitor events,
  serialized commands, bounded queues, retained availability and bridge-only
  supervision. The builder checks stock prerequisites, installed bytes/metadata,
  startup links and final/reopened image results.
- Native fixture tests passed with host-built **libmosquitto 1.4.14** under both
  mise Python **3.14.9** and host Python **2.7.18**. The seven Python-2-compatible
  tests cover framing/coalescing, credential redaction/log rotation and logging
  failures, MQTT wire flags/callbacks, retained-command rejection, bounded queues,
  publication stalls, ordered command exchanges and monitor-loss cleanup.
  Host Python 2 required Apple Silicon configure/system-libffi build adjustments;
  this establishes host compatibility, not the stock ARM ABI.
- Additional offline tests exercise input privacy, configuration validation,
  command expiry/partial writes/uncertain delivery, generation disposal, capped
  retry delays and actual fork/signal/flock supervision. Synthetic ext4 builds
  passed MQTT+SSH composition in both orders, prerequisite rejection and
  final/reopened verification failures after deliberate fixture tampering.
  The final full `mise run test` run passed **150 tests**, with native tests enabled
  and no skips. A new CLI test initially leaked its process umask into a recovery
  fixture; the test now restores it and the complete suite passes.
- A real pinned-stock MQTT+SSH build with disposable broker/login settings passed
  filesystem checks, payload readback, packaging and reopened verification:
  `.local/mqtt-image-validation/mqtt-ssh.fwz`, SHA-256
  `9f1894448128bf6f30b4a74bcf0ff32e3ed1e24a960af93a33a2d3616610ddb9`.
  The output hash was independently reread and matched the private build report.
  The original stock hash was unchanged on reread; output permissions are 0600.
- Independent standards/correctness and spec reviews identified one logging
  exception mismatch between Python 2 and 3. It was fixed and reproduced by a
  passing Python-2 regression test. The spec review found no violations.
  A subsequent fresh correctness review found no actionable findings and
  independently reran all 150 offline tests and seven Python-2 runtime tests.
- No candidate code was installed on the intercom or connected to household MQTT.
  Target imports/ABI, fresh-image startup, reconnect behavior, retained availability,
  existing notifications, calls/audio/video and door control still require
  separately authorized hardware acceptance. Firmware and test inputs stay private.

## 2026-10-31: Public monitor event coverage — live observation

- With user authorization, opened an IPv4-loopback OpenWebNet monitor session
  on the existing modified C100X 1.5.8 and observed it alongside a temporary
  loopback tcpdump capture using the legacy traffic exclusions. Both were ready
  at **20:19:06 UTC**. Private evidence:
  `.local/mqtt-monitor-probe/20261031T201904Z/`.
- Both sources observed exactly two `*8*1#1#4#21*10##` doorbell events, at about
  **20:21:22** and **20:24:57 UTC**. Host-receipt differences were approximately
  52 ms and 118 ms; these are comparative observations, not latency guarantees.
  The user confirmed the first ring's existing notification arrived.
- The user answered the second call and hung up after approximately 3–5 seconds.
  The monitor carried subsequent call-state frames, including
  `*8*2#1#4*10##` and `*8*3#1#4*410##`; exact physical-action timing was not measured.
- At **20:26:52–53 UTC**, both sources observed the existing HA door-control pair
  `*8*19*20##`, `*8*20*20##`. The user confirmed the door opened normally.
- The monitor and capture are not byte-for-byte equivalent streams: capture
  includes internal ACKs/repeated observations, while monitor adds application
  state notifications. This establishes coverage of the tested household events,
  not every possible legacy raw message or duplicate-free delivery.
- Notifications and commands still used the installed legacy MQTT bridge. No
  candidate MQTT payload was installed or published to MQTT by the observers.
  Fresh-image startup, MQTT-library binding, reconnection and full household
  acceptance of a new payload remain unvalidated.
- Temporary observers stopped at **20:28:04 UTC**, with the cleanup marker and
  SSH exit 0 recorded. A separate check confirmed the temporary tcpdump PID was
  absent. The user's SSH master remained available.

## 2026-10-29: Published alpha and signed-download validation

- Published [v0.1.0-alpha.1](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.1.0-alpha.1)
  from commit `8afb96c4631bbbcb825bd5780841c25c13abc2aa`. Release workflow
  `40774991846` completed successfully after Apple membership renewal and a
  retry of a transient network failure during stapling. The earlier signing and
  notarization blockers recorded below are resolved.
- Downloaded the published DMG, dependency sources, provenance and checksums;
  all SHA-256 checks passed. DMG SHA-256:
  `9cdfe8314c5324d6c1c970ec0c89c5ae21d720af3e87f2d756d5a44602e2fced`.
  Gatekeeper accepted it with `source=Notarized Developer ID`.
- Mounted the DMG read-only, copied out `C100X`, and detached it. All 84 native
  files passed strict signature verification with team `D8635J9XS3`. The copied
  bundle passed relocation smoke tests, including shipped tools and Python hooks.
  The audited minimum is **macOS 15.0, arm64**; local execution was on macOS 27.0.1.
- The downloaded signed CLI built a real SSH-enabled image with a disposable
  ECDSA P-256 login key plus password, running as an ordinary user with system-only
  PATH. Filesystem checks, payload verification, packaging and reopened-image
  verification passed. Output `.local/alpha1-downloaded-ssh.fwz` has SHA-256
  `a04a0a835a9e95c1218b6f232a4b3eec44544aee152b811ae94aef6d79aa2068`.
- Independent rereads matched the output report and unchanged pinned stock hash;
  output permissions are 0600. Firmware, credentials and generated keys remain
  private. The build took 3543.34 seconds elapsed, 138.70 user CPU seconds and
  1.46 system CPU seconds; the wall-clock gap was not diagnosed.
- No device operations were performed for release validation. Native flashing,
  generated-image boot/SSH behavior and functional acceptance remain pending.

## Completed without firmware writes

- [x] Preserve and hash the original stock and selected modified 1.5.8 archives.
- [x] Validate the complete selected archive, gzip trailers, nested kernel ZIP,
      payload SHA-256 and POSIX checksums.
- [x] Establish the vendor C100X recovery-first sequence from installer and
      device code; verify normal/recovery FTP credentials offline.
- [x] Read type, firmware, hardware, status, uptime and normalized object model
      from the existing intercom through the research SSH tunnel.
- [x] Build pinned TetherKit; its 23 CTest entries passed. This run does not
      establish privileged or C100X hardware coverage.
- [x] Pass 36 Python tests: framing, archive rejection/integrity, sequence and
      failure at each simulated step, lost write ACK, FTP failures, stale reboot
      replies, USB reconfiguration and signal-driven helper cleanup.

## Native read-only preflight — passed

Use the commands in [FLASHING.md](FLASHING.md), before restoring stock:

- [x] Record Mac OS version, TetherKit revision and device USB enumeration.
- [x] Start `usb` with terminal sudo; record the system-side feth interface.
- [x] Verify `.2/30` and that the route to `.1` uses this interface.
- [x] Run `probe`; require type 200, firmware 1.5.8, hardware 02*06*0,
      model 1.0.99, status 4*0 and valid uptime.
- [x] Run `plan` for the selected image; require the expected archive hash and
      `device_writes: false`.
- [x] While completely idle, disconnect/reconnect only USB, keeping device power
      stable. Verify interface reconfiguration and a second successful probe.
- [x] Stop the supervisor with Ctrl-C while idle; verify its feth pair is removed.

These checks do not start firmware transfer or enter recovery. The supervisor is
currently stopped; start it again before subsequent native device checks.

### 2026-10-27: USB enumeration

- macOS 27.0.1 (26A434).
- TetherKit revision `1ded051fd243c547fd6e250a898f0164cc30561d`.
- Native enumeration found `1da4:0056`, bus 000/device 001, control interface 0,
  data interface 1, RNDIS signature `02/02/ff`.
- Research SSH access was restored. Before terminal sudo was started, no feth
  interface existed and the route to `192.168.129.1` used the ordinary LAN
  default route (`en0`). Native probe/plan had not yet run at this point.

### 2026-10-27: Native USB probe and plan passed

- User started the supervisor with terminal sudo. System-side `feth0` is active
  at `192.168.129.2/30`, paired with driver-side `feth1`.
- Route to `192.168.129.1` uses `feth0` and subnet `192.168.129.0/30`.
- Direct native `probe` returned type 200, firmware 1.5.8, hardware 02*06*0,
  status 4*0, extended identity 99*6*1*0 and normalized model 1.0.99.
- Direct native `plan` validated the selected archive, vendor profile and device,
  returning the expected archive hash and `device_writes: false`.
- Uptime advanced from 1 day 00:30:48 during probe to 1 day 00:31:33 during plan.
  Neither command used the SSH tunnel or sent firmware-write/reboot commands.
- At this point, physical idle reconnect and supervisor cleanup checks were
  still pending, alongside native FTP transfer, recovery-mode networking and
  actual flash acceptance.

### 2026-10-27: Idle USB reconnect passed

- User disconnected/reconnected USB with the supervisor running. Afterward,
  `feth0` was active at `.2/30`, paired with `feth1`, and the device route still
  used `feth0`.
- A fresh direct USB probe succeeded with the same expected identity/status.
  Uptime was 1 day 00:33:37, consistent with uninterrupted device power.
- macOS reported “disk not ejected properly”. The intercom also exposes a
  52.4 MB external physical disk named `C100X` (disk7 during this check).
  This storage interface is separate from the RNDIS update transport; the CLI
  has not written firmware or files to that volume. Its filesystem integrity
  has not been checked. Eject the C100X volume before future idle cable removal.
- Supervisor Ctrl-C cleanup was the remaining idle transport check at this point.

### 2026-10-27: Supervisor cleanup passed

- User stopped the supervisor with Ctrl-C while the device was idle and USB
  remained connected.
- Both `feth0` and `feth1` disappeared from the macOS interface list.
- The USB subnet route was removed; lookup for `.1` now falls back to the
  existing LAN default route through `en0`/`192.168.0.1`.
- No matching TetherKit CLI or Python USB supervisor process remained.
- Native read-only preflight is complete. FTP transfer, recovery-mode networking
  and stock-to-modified flash acceptance remain pending.

## 2026-10-27: Plain partition backups completed

At the user's request, raw uncompressed images of the main firmware and
configuration/data partitions were acquired over LAN SSH into the Git-ignored
directory `research/backups/20261027T201641Z/`:

- `mmcblk2p6.img`: 1,073,741,824 bytes. The source filesystem was mounted
  read-only. Local reread SHA-256 matched the received stream and an independent
  device-side SHA-256 read of the partition.
- `mmcblk2p7.img`: 2,567,962,624 bytes. Local reread SHA-256 matched the received
  stream. The source remained mounted read-write, so this is an unquiesced live
  copy, not a guaranteed consistent filesystem/application snapshot.
- `manifest.json` records acquisition details and verification results;
  `SHA256SUMS` records the image hashes. No partial files remained.
- The backup directory has mode 0700 and both images have mode 0600. Images
  contain private device data and credentials and remain outside Git.
- No device writes, filesystem freezes or service stops were requested. These
  images do not include bootloader/kernel/recovery partitions, are not FWZ
  packages, and have not been restore-tested.

## Stock-to-modified acceptance — pending

- [ ] Make the previously successful Windows/MyHOME setup available.
- [ ] Restore stock 1.5.8 with that established method and confirm normal boot.
- [ ] Check baseline calling, audio/video and door release.
- [ ] Reconnect to macOS; run native `probe` and `plan` again.
- [ ] Run the explicit `flash` command without SSH. Keep the Mac awake, device
      powered and the command's terminal open throughout.
- [ ] Record all four payload stages and all three verified reboot boundaries.
- [ ] Confirm final normal state 4*0 and firmware 1.5.8.
- [ ] Verify incoming call/ring and answering.
- [ ] Verify audio in both directions and video.
- [ ] Verify door release.
- [ ] Verify SSH access supplied by the selected modified image, using the
      existing credentials interactively without recording them.
- [ ] Confirm the managed transport exits and removes its interfaces afterward.

Never deliberately interrupt an actual write to test failure handling. On an
unexpected stop, record the last stage and error, keep power stable and assess
the observed state before any further update. Windows availability is not proof
of recoverability from every interrupted state.

Record outcomes and timestamps here after the hardware run. Until then there is
no claim of a successful native USB flash or completed functional acceptance.

## 2026-10-28: Local builder validation

Authorized scope: code/dependency changes, offline tests, verified stock download
and local image builds. No device connection, transfer, reboot or flash was
performed in this session.

- Manufacturer download completed and matched the stock size **106240356** and
  SHA-256 `bca0dd7e407c2406d6f8c696f0a9e50bc1e795c8e4700c89e83f09ff96c3efb2`.
  Subsequent named-stock builds reused and rehashed the local cache.
- Host tools: mise Python 3.14.9, 7zip 26.05, Homebrew e2fsprogs 1.47.4,
  Dropbear keygen package 2026.94, OpenSSL 4.1.0. No filesystem was mounted.
- Stock main-rootfs baseline passed `e2fsck -f -n` with exit 0. No repairs or
  vendor-inconsistency exceptions were necessary.
- A synthetic debugfs batch with a missing source file returned **0**, emitted
  errors on stderr, and executed the following mkdir. The wrapper rejects that
  observed failure even when process status is 0.
- Real no-op round trip passed filesystem checks, pinned-component checks,
  complete main-filesystem hash comparison and final archive reopening:
  `.local/noop-c100x-1.5.8.fwz`, SHA-256
  `d9a5948b5483c3a6e87f05a726ea01896ee84eb500d4fc931b20084ca430c92e`.
- Real SSH build with the user's supplied default **RSA public key** passed
  critical-result checks and final archive readback:
  `.local/ssh-c100x-1.5.8.fwz`, SHA-256
  `ccbc10ae001999acc3fb27faab67ff7f65f6d3d877e66d3901d9c0ad5b97213c`.
  This image uses key-only login and a fresh ECDSA host key. RSA **user**
  authentication still requires the legacy OpenSSH signature exception with
  stock Dropbear; the host-key choice does not remove that separate limitation.
- Both builds have private mode-0600 artifacts and optional redacted `.build.json`
  reports. User SSH credentials and host private keys are not included in tracked files.
- A third real stock build with a disposable **ECDSA P-256 login key plus
  password** passed the final pipeline, including layout checks and repeated
  verification on the reopened filesystem:
  `.local/ssh-ecdsa-test-c100x-1.5.8.fwz`, SHA-256
  `7b5f9cea1c17670792a8b506d11958d1b713b39558d754f60999ac6594aaee62`.
  Its test credentials are private under `.local/ssh-ecdsa-validation/`; neither
  successful login nor boot behavior has been tested. Artifact mode is 0600.
- **68 offline tests passed** with no skips on this Mac. Coverage includes all
  three SSH preparation modes, binary/config/service packaging, readback of
  bytes/metadata/symlinks, xattr/hardlink replacement rejection, failed batch/full
  image, baseline filesystem errors without repair, malformed ZIPs, legacy/vendor
  ZIP variants, conflicts, duplicate payloads, input preservation, publication
  failures, download corruption/cancellation, bounded subprocesses, and actual
  SIGTERM/SIGHUP cleanup in synthetic builds.
- Final reread of the user's original stock archive retained its original
  SHA-256. All three published FWZ hashes were reread locally and matched their
  reports. No unpublished builder workspace remained.
- The new SSH FWZ passed the flasher's `inspect-fw` path with PATH restricted to
  `/usr/bin:/bin`. A synthetic regression test also blocks imports of builder,
  ext4 and host-tool modules while inspecting a valid FWZ.
- The previously selected modified FWZ still passes full inspection with its
  original SHA-256 and payload hashes/checksums. This checks the old-image
  regression as admission moves from archive hashes to a fixed profile.

### Remaining acceptance

- [ ] Run the same synthetic matrix on Linux before claiming parity; test WSL
      separately before documenting it as supported.
- [ ] Import generated output with the existing Windows/MyHOME application.
- [ ] Separately authorize native flashing; complete the existing transfer,
      recovery networking, reboot and functional checks above.
- [ ] Verify SSH with a clean modern client configuration: ECDSA host negotiation,
      ECDSA user-key-only authentication and password-only authentication tested
      independently. Force the intended method so fallback cannot hide failure.
- [ ] Confirm host identity survives a normal reboot, then check door release,
      doorbell behavior and the existing intercom functions.
- [ ] Validate a real supplied MQTT/service binary and configuration on hardware;
      the binary-service example's offline readback is not integration acceptance.

## 2026-10-28: Installer-free CLI validation

- Extracted the C100X profile from the existing MyHOME Suite 3.5.38 installer
  locally, validating provider, object model and recovery-selection fields.
  Recorded the source installer SHA-256 in [PROTOCOL.md](PROTOCOL.md).
- Compared both bundled FTP credential pairs with the validated extraction;
  they match exactly. Shared vendor settings are now bundled under ADR-010.
- **72 offline tests passed**, with no skips. New CLI simulations exercise
  `plan` and `flash` with just a firmware path, credential selection for all four
  transfers, redacted output, and rejection of invalid images/incompatible devices.
- `plan`, `flash`, `inspect-fw` and `usb` help all ran with Python `-S` (site
  packages disabled); obsolete installer/key-source options are absent.
- These checks used simulated device I/O only. Native transfer, recovery networking
  and hardware flashing/functional acceptance remain pending.

## 2026-10-28: Bundled CLI preparation

- **78 offline tests passed**, with no skips. Managed USB tests exercise bounded
  readiness, malformed/dead workers, LAN-route rejection, route timeout and
  cleanup on errors. They use subprocess fixtures and mocked routing, not USB.
- The local arm64 bundle passed relocation smoke checks in a directory containing
  spaces, with a fresh HOME and system-only PATH. Checks covered CLI help/doctor,
  bundled debugfs/e2fsck, encrypted ZIP round-trip, ECDSA key generation,
  SHA-512-crypt, and Python payload hooks importing TLS/SQLite/ctypes/compression.
- CPython 3.14.9 links to OpenSSL 3 after the initial OpenSSL 4 `_ssl` import failed.
  Native-library auditing found no external library references or rpaths. Local
  Homebrew bottles raise this candidate's minimum to **macOS 27.0**; the CI
  artifact's minimum will be determined separately from its shipped binaries.
- Signing, notarization, GitHub publication and downloaded-artifact checks are
  still pending at this point. No hardware operations were performed.
- The complete local package build then passed, including hashed dependency
  source archives and license collection. Source notices supplement bottles
  that omit them (notably 7zip); pip bootstrap wheels/development scripts are
  excluded from the runtime bundle.
- A real no-payload firmware build using the bundled CLI and system-only PATH
  passed all offline checks. Its main filesystem retained the stock hash
  `80f04c61a9a34032e397d1dc6a1209ad029162a59d08981d7fd9f81348264354`.
- GitHub Actions run `40774118641` passed the Python suite, pinned helper build
  and CTest suite, complete package build, relocated smoke tests and candidate
  DMG creation. This run produced an ad-hoc CI artifact, not a signed release.

### Downloaded GitHub candidate

- Run `40774991941` passed on commit `8afb96c`. Downloaded its candidate DMG,
  dependency sources and provenance; every published SHA-256 checksum matched.
- Mounted the downloaded DMG read-only, copied its `C100X` folder locally, and
  detached it. The copied bundle passed the same relocation smoke checks with
  system-only PATH. Its audited minimum is **macOS 15.0**, arm64. Local execution
  was on macOS 27.0.1; CI exercised it on macOS 15.
- The downloaded CLI fetched stock firmware into a fresh cache over HTTPS and
  verified the pinned size/hash without developer tools on PATH.
- Tagged alpha run `40774991846` built successfully but stopped at signing:
  the imported P12 did not contain a valid Developer ID Application identity.
  No GitHub release was published. Credential correction, notarization and
  signed-download validation remain pending.

### 2026-10-29: Real build with the downloaded CI executable

- The downloaded CLI built an SSH-enabled image using a disposable ECDSA P-256
  login key plus password, with PATH restricted to system tools. Bundled Python
  hooks, e2fsprogs, key generation, password hashing, packing and final reopened
  image verification all passed.
- Output `.local/ci-downloaded-ssh.fwz` has SHA-256
  `f1600cb6b7b61aca20dee34237dbb1889d7ecde7c9fdf273ee0c900d28fcd626`.
  Independent rereads verified both this hash and the unchanged stock input hash;
  output permissions are 0600. Credentials and firmware remain private.
- The first attempt reached compression but exceeded the harness's 20-minute
  execution limit without publishing an output. A rerun without that limit
  completed: 5613.42 seconds elapsed, 169.53 user CPU seconds and 1.59 system CPU
  seconds. The long wall-clock gap was not diagnosed; this is not a build-speed
  benchmark. No device operations or hardware acceptance occurred.

### 2026-10-29: Signing passed; Apple agreement blocks notarization

- After correcting the uploaded P12, the CI signing check found the expected
  Developer ID Application identity and signed/verified a test executable.
- Alpha run `40774991846`, rerun with the corrected credentials, signed all
  shipped native code and passed the signed-bundle relocation smoke tests.
- Apple rejected the notarization submission with HTTP 403: a required team
  agreement was missing or expired. Account-holder action is required before
  retrying. No signed alpha release has been published yet.

## 2026-10-29: Read-only bootloader and rescue investigation

- User reopened the research SSH session. Read the existing modified device's
  environment, storage layout, CPU/device-tree identity and boot messages.
- Independently read the 4 KiB environment: CRC32 passed and its entries matched
  `fw_printenv`. The installed script tries recovery after normal kernel/image
  checks or DTB loading fail; it does not test later rootfs/application health.
- Acquired both 4 MiB eMMC boot regions and the first 1 MiB of the user area into
  private mode-0600 files. Local reread hashes and independent device-side
  read/hashes matched for all four regions, including the environment.
- Boot0 contains vendor U-Boot 2015.04; boot1 is all zero bytes. The saved
  recovery test loads kernel and DTB from the recovery kernel partition; embedded
  default-environment text instead loads the recovery DTB from the main kernel
  partition. Resetting defaults is not a validated repair.
- Public C100X 1.5.8/MyHOME 3.5.38 driver-recovery reports were reviewed. One
  reports a completed update after RNDIS driver correction; another remains
  unresolved. Neither establishes recovery when both Linux environments fail.
- Targeted offline bootloader decompilation subsequently completed. It supports
  explicit kernel header/data checks, keyed serial interruption, a shell/parser
  path after autoboot returns, and serial binary-loading commands. The running
  device tree identifies UART3 and its SoC pin mux; physical PCB access, voltage,
  console interruption and RAM-boot rescue remain untested.
- No firmware/environment writes, reboot, serial-console test, ROM download or
  rescue test was performed. Full native flash and functional acceptance remain
  pending. Evidence and remaining hardware prerequisites are in
  [RECOVERY.md](RECOVERY.md).

## 2026-10-29: Installed kernel and recovery integrity — read-only

- At the user's request, acquired `/dev/mmcblk2p2` (recovery kernel/DTBs,
  52428800 bytes), `p3` (recovery filesystem, 157286400 bytes) and `p5` (normal
  kernel/DTBs, 52428800 bytes) over the existing research SSH session between
  **20:43:58 and 20:48:18 UTC**. All three were unmounted; mount checks included
  kernel major/minor numbers to account for device aliases. Local image hashes
  matched independent device-side partition read/hashes.
- Rehashed the original cached stock FWZ against its existing SHA-256 pin, then
  extracted and verified the pinned recovery gzip and shared kernel ZIP.
- Both installed kernel partitions contain exactly the stock set of **21 files**.
  Every file's length and SHA-256 matches stock: `uImage` and all 20 DTBs,
  including `shark_dig2_car6.dtb` for the observed hardware.
- Read-only `e2fsck 1.47.4 -f -n` returned **0** for all three acquired partition
  images and the extracted stock recovery filesystem. Image hashes before/after
  checking and kernel extraction were unchanged. No filesystem was mounted or
  repaired on the host or device.
- The stock recovery filesystem occupies **153600000 bytes** (150000 blocks of
  1024 bytes); the partition has a further **3686400 bytes** outside that extent.
  Comparison used the filesystem extent rather than treating the larger partition
  as an equal-length stock image.
- The recovery filesystem is **not byte-identical** to stock: 18384 byte
  positions differ across 103 filesystem blocks. Every changed block was
  classified: 1 superblock, 1 group-descriptor block, 2 inode bitmaps, 44 inode
  table blocks, 2 directory blocks and 53 journal blocks. Existing inode changes
  are limited to timestamps and directory versions; no existing regular-file
  content changes were found.
- Two newly allocated symlinks are present:
  `/var/lib/dhcp/dhcp` -> `/var/volatile/tmp/dhcp` and
  `/var/lib/opkg/opkg` -> `/var/volatile/tmp/opkg`. These are consistent with
  the unchanged stock `/etc/volatile.cache` link-creation commands acting on
  existing directories. No inodes were deallocated. The observed differences
  support prior startup activity, not a claim of an exact stock filesystem copy.
- Private mode-0600 acquisitions, checksums, tool output and difference reports
  are in `.local/recovery-integrity-20261029T204358Z/`. No device writes, reboot,
  recovery-mode boot or recovery-networking test occurred. This establishes an
  integrity baseline for the **currently installed** components; the native flash
  sequence will rewrite recovery, so its later boot/write outcome remains untested.

## 2026-10-29: Stock USB verification search — offline

- Decompiled stock-matching `bt_daemon` and `libcommon.so.0.0` locally. Reconfirmed
  the analyzed daemon and `bt_device` are byte-identical to files in stock main
  firmware. Traced startup recovery-kernel checks through query-40 status handling.
- Found installed recovery `uImage` magic/header/data CRC checks on normal non-NFS
  startup. The existing flasher's state-4 requirement after its first verified
  reboot indirectly gates the main-kernel clear on this check. Rootfs and DTBs
  are outside its coverage; this is not stock-hash readback or filesystem checking.
- Inspected configuration/extra export paths, checksum queries, stock FTP/startup
  configuration and public discussions. No suitable full recovery readback over
  stock USB services was established. Query 44 remains rebooting and unsuitable
  for read-only preflight.
- All work in this search was offline/public-source research. No device commands,
  reboots, firmware writes or flasher implementation changes occurred. The
  checksum behavior has not been exercised by deliberately corrupting hardware.
  Detailed evidence is recorded in [PROTOCOL.md](PROTOCOL.md).

## 2026-10-29: Optional SSH verification — implementation checks

- Implemented an opt-in recovery-integrity gate after the first verified normal
  reboot and before clearing the main kernel. Preflight, deadlines, independent
  read/hashes, exact reference comparisons, read-only fsck and evidence publication
  fail closed. Ordinary flashing remains independent of SSH/e2fsprogs.
- `mise run test`: **130 offline tests passed** after review fixes, including synthetic ext4
  corruption/content/metadata differences, mount aliases, acquisition failures,
  deadline/cancellation behavior, report-save failures, gate ordering, later
  update failure, CLI isolation, private cleanup and memory-only askpass IPC.
- A separate offline exercise used the actual pinned stock recovery filesystem
  expanded into a synthetic partition and the previously acquired stock-matching
  recovery kernel partition. Verification passed. Substituting the previously
  acquired recovery rootfs with known metadata differences was correctly rejected.
  All source artifacts were read-only; no device connection was involved.
- The tests exposed a trailing blank line in real `debugfs ls -p /` output; the
  parser was corrected before the successful runs above.
- Independent standards/spec/correctness reviews found two issues: returning to
  a previously observed host key did not warn, and legacy RSA host-key negotiation
  lacked its separate OpenSSH exception. Both were corrected with regression
  coverage, including inspection of actual system OpenSSH's resolved configuration.
- A subsequent fresh review identified the stock OpenWebNet 30-second idle
  timeout. The updater now reconnects/rechecks state 4 after SSH preflight and
  readback, with simulated connection expiry and failed-reconnect coverage.
- USB SSH authentication, sudo-to-user execution on a live connection, the
  post-reboot SSH gate and fresh device-write equality remain hardware-unvalidated.
  No firmware writes, device reboots or hardware fault injection were performed
  for this implementation. Alpha publication does not close those acceptance items.

## 2026-10-29: Alpha.2 publication

- Pushed implementation/review fixes at `8966d6be78789ab3afa8702ff0833bdeb5ed5526`
  and tag **v0.1.0-alpha.2**. Four fresh reviewers covered standards, spec and
  correctness; reported defects were fixed and re-reviewed before publication.
- Main CI run `40963527559` and tagged release run `40963527650` both passed.
  Release CI completed offline tests, native helper build/tests, relocated bundle
  smoke checks (including the shipped askpass helper), Developer ID signing,
  notarization, stapling and prerelease publication.
- [Alpha.2](https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases/tag/v0.1.0-alpha.2)
  was published at **22:15:17 UTC** with the signed arm64 DMG, dependency sources,
  provenance manifest and checksums. It includes optional SSH recovery verification
  and the Applications drag-and-drop shortcut. Hardware acceptance remains pending.
- Downloaded all published assets; SHA-256 checks, release version and source
  commit matched. DMG SHA-256:
  `43568dd80e3ea4c1812a1367b2b39dcdeb6ff1c8eba3de6fa336b56cafe53bee`.
  Stapler validation passed and Gatekeeper accepted the DMG as Notarized Developer
  ID. Read-only mounting confirmed the Applications shortcut.
- All **84 native files** in the copied bundle passed strict signature verification
  with the expected Developer ID team. Relocated packaged smoke checks passed,
  including the shipped password helper/IPC tests. Minimum OS is **macOS 15.0**.
  An additional `spctl --type execute` assessment of the bare CLI returned
  "the code is valid but does not seem to be an app"; the notarized DMG assessment,
  native signature checks and actual CLI/tool execution above passed.
- Private downloaded artifacts are in `.local/downloaded-alpha2/`. No intercom
  connection, write or reboot occurred during release validation.
