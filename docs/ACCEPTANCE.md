# Validation and release readiness

**As of 2026-11-07:** the published core build, native USB flash and household workflow has
passed on the tested C100X Door Entry 1.5.8 installation using Apple Silicon
macOS. **Version 0.1.0 is published and validated**, including its signed download
and Homebrew installation. It carries forward alpha.6's full-flash and functional
acceptance for unchanged device behavior.

**v0.2.0-alpha.1 prerelease candidate:** broader hardware-family admission,
dual-image SSH, default manufacturer-update prevention and explicit wireless
transport are implemented. Five private pinned-stock build
cases and their applicable destination-access checks passed offline. Relocated
packaged smoke passed using current source/assets and existing native dependencies.
This is not a newly signed release or hardware wireless acceptance.
The latest offline suite ran **216 tests: OK, with three optional native-MQTT
tests skipped**. See the [dated wireless validation record](VALIDATION-HISTORY.md#2026-11-07-dual-image-policy-and-wireless-implementation-offline-validation)
and [hardware-family regression checks](VALIDATION-HISTORY.md#2026-11-07-hardware-family-compatibility-offline-validation).

## Supported hardware versus tested hardware

The v0.2.0-alpha.1 candidate and source tools support C100X Door Entry **1.5.8**,
model **`1.0.99`**, hardware family
**`02.*.*`**, using the vendor updater's first-component hardware comparison.
Published **v0.1.0 still restricts hardware to `02*06*0`**. The
[protocol evidence](PROTOCOL.md#hardware-family-compatibility-2026-11-07) establishes
the broader compatibility rule; offline regression checks passed for normal entry,
recovery entry and reboot/reconnection checks.

Hardware flashing and household acceptance remain recorded on **`02*06*0` only**.
[Issue #6](https://github.com/daniel-sc/bticino-c100x-firmware-tools/issues/6) reports
a stock `02*07*0` device reaching the old hardware rejection through USB RNDIS;
no flash was performed. Other family-02 revisions are supported by policy but
have no recorded hardware flash acceptance here. Stock-to-modified acceptance
remains open.

## Passed

| Area | Observed result |
| --- | --- |
| Distribution | v0.1.0 signed/notarized download, checksums, all 84 native signatures, relocated smoke checks, real SSH+MQTT firmware build and Homebrew installation checked. |
| Builder | Pinned-stock no-op, SSH and MQTT+SSH builds passed filesystem, payload and final archive checks. |
| Dual-image policy/access (prerelease, offline only) | Prevention-only, stock-preserving override, SSH-key/prevention, SSH-password/vendor-allowed and SSH+MQTT/both-auth/prevention builds passed. Both filesystem checks and applicable destination authentication admission passed; MQTT remains main-only. |
| USB flashing | Alpha.6 completed all four transfers and three verified reboots, including RNDIS → ECM → RNDIS handover, without SSH verification. |
| SSH payload v2 | Fresh RSA-key logins over USB/Wi-Fi, password-only login, service restart and vendor start/stop isolation passed. Reboot with vendor `abil_ssh` absent preserved access and host identity. |
| Household functions | User confirmed ringing/notification, answering, video, two-way audio, door release, MQTT events and existing MQTT door control working after the alpha.6 installation. |
| Optional recovery verification | Alpha.3 passed fresh-write SSH readback, stock-content comparison and filesystem checks before its later transport stop. Explicit recovery installation subsequently completed. |
| Offline checks | v0.1.0 candidate CI passed all 189 Python tests with native MQTT enabled, all 23 USB-helper tests and packaged smoke checks. Tagged release CI also passed. |

The full flash was **modified-to-modified on one installation**. Household
acceptance is user-reported; no separate MQTT capture or per-action timestamps
were collected. Protocol completion, installed-byte verification and functional
acceptance remain distinct results.

Detailed evidence: [alpha.6 hardware checks](VALIDATION-HISTORY.md#2026-11-05-alpha6-full-flash-ssh-failure-condition-test-and-functional-checks),
[v0.1.0 publication and validation](VALIDATION-HISTORY.md#2026-11-05-version-010-publication-and-validation),
and [optional recovery gate](VALIDATION-HISTORY.md#2026-11-03-stopped-alpha3-flash-and-live-recovery-assessment).

## Release checks

- [x] **Stable release pipeline:** CI accepts stable and alpha tags, marks only
      alphas as prereleases and uses focused release notes. See
      [RELEASING.md](RELEASING.md#release-checklist).
- [x] **Publication checks:** intended commit and downloaded signed artifact
      validated; Homebrew tap updated and installation checked.
- [x] **Current candidate checks:** USB-storage child-media discovery correction
      `4ce6b56` is included in v0.1.0 and passed regression, packaged CI and
      downloaded-artifact checks. This bounded, best-effort host-side correction
      did not require another firmware flash for release.

## Wireless and dual-image hardware acceptance (pending)

The source changes materially alter recovery and require separately authorized
validation: recovery Wi-Fi/DHCP and Bonjour, administrative SSH and tunneled
protocol/FTP transfers, prevention in both environments, preserved USB operation,
complete wireless installation and household functions. No device access or writes
were performed during implementation. Failure injection remains simulation-only.

## Follow-up hardware coverage (non-blocking for unchanged released behavior)

These are disclosed coverage gaps, not requirements to reflash for each release.
Carry forward observed acceptance unless a change materially affects the behavior
it established; see [validation policy](RELEASING.md#validation-policy).

- [ ] **USB-storage behavior:** at a convenient idle session, check unmount and
      subsequent read-only USB probing. Observe storage notifications across
      reboot boundaries during the next otherwise-planned flash.
- [ ] **Stock-to-modified acceptance:** the original stock-device case remains
      untested. The completed run began on modified firmware, without SSH
      verification. If this case is exercised later, establish a stock 1.5.8
      baseline, then record managed preflight, all transfers/reboots and household
      checks. This is a one-time coverage goal, not a recurring release gate.
      See [ADR-006](DECISIONS.md#adr-006-separate-direct-re-flash-testing-from-stock-device-acceptance).
- [ ] **MQTT resilience:** verify broker/network loss and recovery, availability
      transitions and fresh event/command delivery on the installed payload.
      Normal household operation passed; reconnect behavior has offline coverage
      but no recorded hardware result.
- [ ] **Recommended SSH user-key method:** verify ECDSA P-256 user-key-only login
      with password fallback disabled. RSA user-key and password-only login passed;
      successful ECDSA host-key negotiation is a different check.

These checks can be grouped into planned maintenance; SSH login and MQTT
reconnection checks need no firmware flash when the installed image is unchanged.
Never deliberately interrupt a firmware write. Record results only after observation.

## Remaining limits and deferred work

- Manufacturer OTA updates remain enabled in v0.1.0 and prerelease/source builds with `--allow-vendor-updates`,
  and can replace the custom installation.
  Offline comparison confirmed the stock updater/configuration in the v0.1.0
  SSH+MQTT image. Read-only SSH on 2026-11-05 confirmed stock updater components,
  enabled settings and no packages at the two known persistent staging paths.
  Missing-installer branches passed 33 isolated ARM-emulation cases; no live OTA
  overwrite or prevention test was performed. The source default policy now covers
  both prepared filesystems (ADR-019), but has not been installed on the tested device. Boot,
  vendor app notifications, remote answering, commissioning/reconnection,
  household functions and explicit USB flashing with this policy still require
  hardware validation. Existing unprotected firmware remains unprotected until replacement.
  See [OTA investigation](OTA.md) and [offline validation](VALIDATION-HISTORY.md#2026-11-05-no-ota-implementation-and-offline-validation).
- Linux/WSL parity and Windows/MyHOME import of generated images are unvalidated;
  the distributed tool targets Apple Silicon macOS 15+.
- An uninterrupted full run combining the optional SSH gate with the fixed USB
  handover has not been recorded. The gate and ordinary full flash passed in
  separate runs.
- General rescue when both Linux environments fail, raw-backup restoration and
  board-level console access are unvalidated; see [RECOVERY.md](RECOVERY.md).
- Custom payloads need their own hardware acceptance. The binary-service example
  is an authoring example, not a validated device service.

## Evidence history

[VALIDATION-HISTORY.md](VALIDATION-HISTORY.md) preserves dated builds, releases,
hardware observations, research acquisitions and earlier test plans. Consult this
page for current status and [FLASHING.md](FLASHING.md) for user instructions.
