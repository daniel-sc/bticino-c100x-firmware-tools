# Hardware acceptance record

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
