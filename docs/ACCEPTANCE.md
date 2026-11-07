# Validation and release readiness

**As of 2026-11-07:** firmware building, native USB flashing, main-system SSH,
MQTT and household functions have passed on C100X Door Entry 1.5.8 using Apple
Silicon macOS. Hardware evidence covers `02*06*0` and community-reported `02*07*0`.

**Evidence follows capabilities, not tool versions.** Passed results carry forward
unless a structural, incompatible or other material change affects the tested
behavior or its assumptions. Revalidate the affected path; other results remain
valid. Exact versions, configurations and attribution are preserved in
[VALIDATION-HISTORY.md](VALIDATION-HISTORY.md). Signed release artifacts still
receive their own packaging and installation checks.

**Community hardware result, 2026-11-07:** a stock `02*07*0` unit successfully
installed SSH+MQTT firmware over USB. The reporter confirms preflight, flash completion and
working display, outdoor video, door release, Door Entry app, call audio, SSH and
MQTT. This adds stock-to-modified coverage; see the
[attributed record](VALIDATION-HISTORY.md#2026-11-07-community-reported-car-7-stock-to-modified-acceptance).

**v0.2.0-alpha.2 candidate:** adds FTP greeting readiness, command-session refresh
after uploads and transient SSH-control timeout handling. The FTP greeting fix
passed authorized transfer-start-only hardware checks; follow-up fixes passed
offline regressions. Final local testing passed all 228 tests, including native
MQTT ABI coverage. Release CI and downloaded-artifact validation are pending.
Full wireless installation remains pending hardware acceptance.

**v0.2.0-alpha.1 publication evidence:** broader hardware-family admission, dual-image
SSH, default manufacturer-update prevention and explicit wireless transport are
included. The signed/notarized download passed checksum/signature checks,
relocated packaged smoke, a real SSH+MQTT build and dual-image authentication
admission. Homebrew's `c100x` tracks stable v0.1.0; `c100x@preview` tracks
v0.2.0-alpha.1, with installation and version output verified.
Both macOS and Linux candidate CI passed **all 216 tests**, including native MQTT;
tagged release CI also passed. These are host/offline results; hardware acceptance
of wireless transport and customized recovery remains pending because those
introduce new transport and startup behavior. Existing USB and main-system
functional evidence carries forward for unchanged behavior. See the
[publication record](VALIDATION-HISTORY.md#2026-11-07-v020-alpha1-publication-and-validation),
[wireless validation](VALIDATION-HISTORY.md#2026-11-07-dual-image-policy-and-wireless-implementation-offline-validation)
and [hardware-family checks](VALIDATION-HISTORY.md#2026-11-07-hardware-family-compatibility-offline-validation).

## Supported hardware versus tested hardware

The v0.2.0 prereleases and source tools support C100X Door Entry **1.5.8**,
model **`1.0.99`**, hardware family
**`02.*.*`**, using the vendor updater's first-component hardware comparison.
Published **v0.1.0 still restricts hardware to `02*06*0`**. The
[protocol evidence](PROTOCOL.md#hardware-family-compatibility-2026-11-07) establishes
the broader compatibility rule; offline regression checks passed for normal entry,
recovery entry and reboot/reconnection checks.

Hardware flashing and household results are recorded on **`02*06*0`** in the
maintainer's installation and **`02*07*0`** in the
[community report](https://github.com/daniel-sc/bticino-c100x-firmware-tools/issues/6#issuecomment-6710515771).
The latter started from stock and adds stock-to-modified coverage.
Other family-02 revisions are supported by policy but have no recorded hardware
flash acceptance here.

## Passed

| Area | Observed result |
| --- | --- |
| Distribution | v0.1.0 and v0.2.0-alpha.1 signed/notarized downloads, checksums, all 84 native signatures, relocated smoke checks, real SSH+MQTT firmware builds and Homebrew installation/upgrade checked. |
| Builder | Pinned-stock no-op, SSH and MQTT+SSH builds passed filesystem, payload and final archive checks. |
| Dual-image policy/access (offline only) | Prevention-only, stock-preserving override, SSH-key/prevention, SSH-password/vendor-allowed and SSH+MQTT/both-auth/prevention builds passed. Both filesystem checks and applicable destination authentication admission passed; MQTT remains main-only. |
| USB flashing | Completed all four transfers and three verified reboots, including RNDIS → ECM → RNDIS handover, without SSH verification. |
| Stock-to-modified USB / Car-7 (community-reported) | On `02*07*0`, `plan` passed and flashing SSH+MQTT firmware completed in about six minutes. Display, outdoor video, door release, Door Entry app, call audio, SSH and MQTT reported working. |
| Main-system SSH | Fresh RSA-key logins over USB/Wi-Fi, password-only login, service restart and vendor start/stop isolation passed. Reboot with vendor `abil_ssh` absent preserved access and host identity. |
| Household functions | User confirmed ringing/notification, answering, video, two-way audio, door release, MQTT events and existing MQTT door control working after installation. |
| Optional recovery verification | Fresh-write SSH readback, stock-content comparison and filesystem checks passed before a later transport stop. Explicit recovery installation subsequently completed. |
| Offline checks | v0.2.0-alpha.1 candidate CI passed all 216 Python tests on macOS/Linux with native MQTT enabled; macOS also passed all 23 USB-helper tests and packaged smoke. Tagged release CI passed. |

The maintainer's full flash was **modified-to-modified on `02*06*0`**; the
community report adds **stock-to-modified on `02*07*0`**. Household acceptance is
user-reported. The Car-7 comment supplies no per-stage transcript or independent
installed-image verification; its post-install backup/layout observations are
recorded separately. Protocol completion, installed-byte verification and
functional acceptance remain distinct results.

Detailed evidence: [alpha.6 hardware checks](VALIDATION-HISTORY.md#2026-11-05-alpha6-full-flash-ssh-failure-condition-test-and-functional-checks),
[v0.1.0 publication and validation](VALIDATION-HISTORY.md#2026-11-05-version-010-publication-and-validation),
and [optional recovery gate](VALIDATION-HISTORY.md#2026-11-03-stopped-alpha3-flash-and-live-recovery-assessment).

## Release checks

- [x] **Stable release pipeline:** CI accepts stable and alpha tags, marks only
      alphas as prereleases and uses focused release notes. See
      [RELEASING.md](RELEASING.md#release-checklist).
- [x] **Publication checks:** intended commit and downloaded signed artifact
      validated; Homebrew tap updated and installation checked.
- [x] **v0.2.0-alpha.1 checks:** intended commit `1ac1140`, signed download and
      real offline build/admission validated. Tap commit `deb3df9` published;
      `brew upgrade --cask daniel-sc/tap/c100x` and `c100x --version` passed.
- [x] **v0.1.0 checks:** USB-storage child-media discovery correction
      `4ce6b56` is included in v0.1.0 and passed regression, packaged CI and
      downloaded-artifact checks. This bounded, best-effort host-side correction
      did not require another firmware flash for release.

## Wireless and dual-image hardware acceptance (pending)

**2026-11-07 FTP startup diagnosis:** two v0.2.0-alpha.1 wireless attempts stopped
at the first FTP greeting, before login/upload or any payload-write request.
Authorized transfer-start-only diagnostics reproduced an FTP-readiness race and
verified the source correction through a successful greeting after initial EOF.
The device remained in normal state with an idle worker. This validates the
greeting fix, not firmware transfer or the full wireless sequence. The published
alpha lacks the correction. See the [diagnosis record](VALIDATION-HISTORY.md#2026-11-07-wireless-ftp-startup-race).

Source also refreshes the command session after FTP uploads and tolerates
transient local SSH-control readiness timeouts. Their follow-up regression checks
are offline; hardware coverage of long uploads and reboot-time SSH polling remains
pending.

Customizing recovery, adding wireless transport and suppressing vendor-update
startup paths materially change the installation. Targeted hardware validation
is needed for recovery Wi-Fi/DHCP and Bonjour, recovery SSH and tunneled transfers,
OTA prevention in both environments, USB operation with customized recovery,
complete wireless installation and household functions under the new startup
policy. The established USB sequence, main-system SSH and MQTT results remain
evidence for their unchanged behavior. Failure injection remains simulation-only.

## Follow-up hardware coverage (non-blocking for unchanged released behavior)

These are disclosed coverage gaps, not requirements to reflash for each release.
Carry forward observed acceptance unless a change materially affects the behavior
it established; see [validation policy](RELEASING.md#validation-policy).

- [ ] **USB-storage behavior:** at a convenient idle session, check unmount and
      subsequent read-only USB probing. Observe storage notifications across
      reboot boundaries during the next otherwise-planned flash.
- [x] **Stock-to-modified acceptance (community-reported):** issue #6 reports a
      successful stock 1.5.8 → SSH+MQTT installation on `02*07*0`. Preflight,
      completed flash and functional results are reported; individual
      transfer/reboot logs were not supplied. This coverage carries forward for
      the established USB workflow.
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
