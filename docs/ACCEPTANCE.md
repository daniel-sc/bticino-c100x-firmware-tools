# Validation and release readiness

**As of 2026-11-07:** firmware building, full native USB and wireless SSH flash
sequences, main-system SSH, MQTT and household functions have recorded passes on
C100X Door Entry 1.5.8 using Apple Silicon macOS. Hardware evidence covers
`02*06*0` and community-reported `02*07*0`. The user also confirmed household
tests passed after the SSH flash with vendor-update blocking enabled.

**Evidence follows capabilities, not tool versions.** Passed results carry forward
unless a structural, incompatible or other material change affects the tested
behavior or its assumptions. Revalidate the affected path; other results remain
valid. Exact versions, configurations and attribution are preserved in
[VALIDATION-HISTORY.md](VALIDATION-HISTORY.md). Signed release artifacts still
receive their own packaging and installation checks.

**SSH/OTA hardware result, 2026-11-07:** the user supplied successful read-only
preflight and a complete **10m36s** wireless flash transcript on `02*06*0`.
Recovery readback/hash/filesystem checks passed before main-kernel invalidation;
recovery boot, tunneled main transfers and final destination SSH verification
completed. The destination package was admitted as `vendor_updates: blocked`;
the user subsequently confirmed household tests and a fully working installation.
See the [dated evidence](VALIDATION-HISTORY.md#2026-11-07-complete-wireless-ssh-flash).

**v0.2.0 release preparation:** current usage and release notes describe SSH OTA
flashing, dual-image SSH and default vendor-update blocking. Publication and
artifact-specific checks for the stable tag remain outstanding.

## Supported hardware versus tested hardware

The tool supports C100X Door Entry **1.5.8**, model **`1.0.99`**, hardware family
**`02.*.*`**, using the vendor updater's first-component hardware comparison.
The [protocol evidence](PROTOCOL.md#hardware-family-compatibility-2026-11-07)
establishes the compatibility rule; offline regression checks passed for normal
entry, recovery entry and reboot/reconnection checks.

Hardware flashing and household results are recorded on **`02*06*0`** in the
maintainer's installation and **`02*07*0`** in the
[community report](https://github.com/daniel-sc/bticino-c100x-firmware-tools/issues/6#issuecomment-6710515771).
The latter started from stock and adds stock-to-modified USB coverage. Wireless
coverage is on `02*06*0`. Other family-02 revisions are supported by policy but
have no recorded hardware flash acceptance here.

## Passed

| Area | Observed result |
| --- | --- |
| Distribution pipeline | Published signed/notarized downloads, checksums, all 84 native signatures, relocated smoke checks, real SSH+MQTT firmware builds and Homebrew installation/upgrade checked. Stable v0.2.0 artifacts still need their own checks. |
| Builder | Pinned-stock no-op, SSH and MQTT+SSH builds passed filesystem, payload and final archive checks. |
| Dual-image policy/access (offline) | Prevention-only, stock-preserving override, SSH-key/prevention, SSH-password/vendor-allowed and SSH+MQTT/both-auth/prevention builds passed. Both filesystem checks and applicable destination authentication admission passed; MQTT remains main-only. |
| USB flashing | Completed all four transfers and three verified reboots, including RNDIS → ECM → RNDIS handover, without SSH verification. |
| Wireless SSH flashing | Read-only plan and full four-transfer/three-reboot sequence completed on `02*06*0` using the default `.local` hostname and RSA login key; final destination SSH verification passed. |
| Customized recovery over SSH | Installed recovery readback, independent hashes and filesystem checks passed before main-kernel clear. Recovery subsequently booted with working LAN SSH and tunneled OpenWebNet/FTP for main installation. |
| Stock-to-modified USB / Car-7 (community-reported) | On `02*07*0`, preflight passed and flashing SSH+MQTT firmware completed in about six minutes. Display, outdoor video, door release, Door Entry app, call audio, SSH and MQTT reported working. |
| Main-system SSH | Fresh RSA-key logins over USB/Wi-Fi, password-only login, service restart and vendor start/stop isolation passed. Reboot with vendor `abil_ssh` absent preserved access and host identity. |
| Household functions | Ringing/notification, answering, video, two-way audio, door release, MQTT events and existing MQTT door control passed after the earlier SSH+MQTT installation. After the new wireless flash, the user confirmed completing the household tests and that the installation is fully working with vendor-update blocking enabled. |
| Optional USB recovery verification | Fresh-write SSH readback, stock-content comparison and filesystem checks passed before a later transport stop. Explicit recovery installation subsequently completed. |
| Offline checks | Latest published candidate CI passed all 228 Python tests on macOS/Linux with native MQTT enabled; macOS also passed all 23 USB-helper tests and packaged smoke. Tagged release CI passed; provenance is in the history. |

The maintainer's flashes were **modified-to-modified on `02*06*0`**; the community
report adds **stock-to-modified on `02*07*0`**. Household acceptance is user-reported.
The Car-7 comment supplies no per-stage transcript or independent installed-image
verification. The new wireless result is based on the supplied terminal transcript;
its private verification reports were not independently inspected for this update.
Protocol completion, installed-byte verification and functional acceptance remain
distinct results.

Detailed evidence: [wireless sequence](VALIDATION-HISTORY.md#2026-11-07-complete-wireless-ssh-flash),
[USB and household checks](VALIDATION-HISTORY.md#2026-11-05-alpha6-full-flash-ssh-failure-condition-test-and-functional-checks),
and [USB recovery gate](VALIDATION-HISTORY.md#2026-11-03-stopped-alpha3-flash-and-live-recovery-assessment).

## v0.2.0 release checks

- [x] **Stable release pipeline:** CI accepts stable and alpha tags, marks only
      alphas as prereleases and uses focused release notes. See
      [RELEASING.md](RELEASING.md#release-checklist).
- [x] **Targeted SSH flash evidence:** completed wireless sequence, recovery
      integrity gate and final SSH verification recorded.
- [x] **Release documentation:** current usage and notes prepared for v0.2.0.
- [x] **Local preparation checks:** all 228 offline tests passed with required
      builder tools and native MQTT coverage; documentation links and workflow
      version selection passed.
- [ ] **Release commit CI:** run main CI on the intended stable release commit
      before tagging `v0.2.0`.
- [ ] **Signed publication:** tagged CI, signing/notarization and downloaded
      checksum, signature, provenance, relocated smoke and real build checks.
- [ ] **Stable Homebrew channel:** update `Casks/c100x.rb` with the published
      version/DMG checksum, then verify installation or upgrade and version output.

## Wireless and dual-image hardware coverage

The complete wireless run closes the full SSH sequence, recovery LAN/SSH startup,
tunneled transfers, recovery integrity gate and final destination access checks
for the tested configuration. The default Bonjour hostname was used successfully
across the sequence; no separate DHCP renewal, address-change or mDNS-fallback
scenario was recorded. Post-upload command reconnection appears before all four
writes. The log does not establish that a transient SSH-control timeout occurred.

The installed image has the blocked vendor-update policy. This establishes
successful installation and boot/access with that policy, not observation of a
blocked manufacturer installation. Additional coverage:

- [ ] **Prevention runtime:** read-only confirmation of suppressed vendor updater
      startup paths in both environments; no real vendor write as a blocking test.
- [x] **Household checks under the new policy:** the user confirmed completing
      the household tests after the wireless flash and that everything is working.
      No separate commissioning/reconnection scenario was reported.
- [ ] **USB with customized recovery:** targeted USB operation/handover coverage
      with the dual-image policy installed. The established USB sequence passed
      with stock recovery.

## Follow-up hardware coverage (non-blocking for unchanged released behavior)

These are disclosed coverage gaps, not requirements to reflash for each release.
Carry forward observed acceptance unless a change materially affects the behavior
it established; see [validation policy](RELEASING.md#validation-policy).

- [ ] **USB-storage behavior:** at a convenient idle session, check unmount and
      subsequent read-only USB probing. Observe storage notifications across
      reboot boundaries during the next otherwise-planned flash.
- [x] **Stock-to-modified acceptance (community-reported):** issue #6 reports a
      successful stock 1.5.8 → SSH+MQTT USB installation on `02*07*0`, with
      preflight, completion and functional checks. See
      [ADR-006](DECISIONS.md#adr-006-separate-direct-re-flash-testing-from-stock-device-acceptance).
- [ ] **MQTT resilience:** verify broker/network loss and recovery, availability
      transitions and fresh event/command delivery on the installed payload.
- [ ] **Recommended SSH user-key method:** verify ECDSA P-256 user-key-only login
      with password fallback disabled. RSA user-key and password-only login passed;
      successful ECDSA host-key negotiation is a different check.

These checks can be grouped into planned maintenance. Never deliberately interrupt
a firmware write. Record results only after observation.

## Remaining limits and deferred work

- Manufacturer updates remain enabled in existing unprotected firmware and builds
  with `--allow-vendor-updates`, and can replace custom features. Preflight checks
  for staged packages and active installers do not exclude later competition.
  See [OTA investigation](OTA.md) for the prevention mechanism and evidence.
- Linux/WSL parity and Windows/MyHOME import of generated images are unvalidated;
  the distributed tool targets Apple Silicon macOS 15+.
- An uninterrupted full run combining the optional SSH gate with USB handover
  has not been recorded. The USB gate and ordinary full USB flash passed separately;
  the completed SSH flash includes the mandatory gate.
- General rescue when both Linux environments fail, raw-backup restoration and
  board-level console access are unvalidated; see [RECOVERY.md](RECOVERY.md).
- Custom payloads need their own hardware acceptance. The binary-service example
  is an authoring example, not a validated device service.

## Evidence history

[VALIDATION-HISTORY.md](VALIDATION-HISTORY.md) preserves dated builds, releases,
hardware observations, research acquisitions and earlier test plans. Consult this
page for current status and [FLASHING.md](FLASHING.md) for user instructions.
