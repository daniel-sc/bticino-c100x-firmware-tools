# Validation and release readiness

**As of 2026-11-05:** the core build, native USB flash and household workflow has
passed on the tested C100X Door Entry 1.5.8 installation using Apple Silicon
macOS. Version 0.1.0 carries forward alpha.6's full-flash and functional acceptance
for unchanged device behavior. This release snapshot precedes publication checks;
subsequent artifact results are recorded in the online validation history.

## Passed

| Area | Observed result |
| --- | --- |
| Distribution | Alpha.6 signed/notarized download, checksums, native signatures, relocated smoke checks, real firmware build and Homebrew installation checked. |
| Builder | Pinned-stock no-op, SSH and MQTT+SSH builds passed filesystem, payload and final archive checks. |
| USB flashing | Alpha.6 completed all four transfers and three verified reboots, including RNDIS → ECM → RNDIS handover, without SSH verification. |
| SSH payload v2 | Fresh RSA-key logins over USB/Wi-Fi, password-only login, service restart and vendor start/stop isolation passed. Reboot with vendor `abil_ssh` absent preserved access and host identity. |
| Household functions | User confirmed ringing/notification, answering, video, two-way audio, door release, MQTT events and existing MQTT door control working after the alpha.6 installation. |
| Optional recovery verification | Alpha.3 passed fresh-write SSH readback, stock-content comparison and filesystem checks before its later transport stop. Explicit recovery installation subsequently completed. |
| Offline checks | On 2026-11-05, `mise run test` passed 186 tests with 3 optional native MQTT tests skipped; a separate native-enabled runtime run passed all 7 tests, including those 3. |

The full flash was **modified-to-modified on one installation**. Household
acceptance is user-reported; no separate MQTT capture or per-action timestamps
were collected. Protocol completion, installed-byte verification and functional
acceptance remain distinct results.

Detailed evidence: [alpha.6 hardware checks](VALIDATION-HISTORY.md#2026-11-05-alpha6-full-flash-ssh-failure-condition-test-and-functional-checks),
[downloaded release](VALIDATION-HISTORY.md#2026-11-04-alpha6-publication-and-downloaded-bundle-validation),
and [optional recovery gate](VALIDATION-HISTORY.md#2026-11-03-stopped-alpha3-flash-and-live-recovery-assessment).

## Remaining release preparation

- [x] **Stable release pipeline:** CI accepts stable and alpha tags, marks only
      alphas as prereleases and uses focused release notes. See
      [RELEASING.md](RELEASING.md#release-checklist).
- [ ] **Publication checks:** validate the intended commit and downloaded signed
      artifact, then update and verify the Homebrew tap.
- [ ] **Current candidate checks:** source commit `4ce6b56` corrects USB-storage
      child-media discovery and is newer than alpha.6. Regression tests pass;
      include it in the release's packaged CI and downloaded-artifact checks.
      This bounded, best-effort host-side correction does not require another
      firmware flash for release.

## Follow-up hardware coverage (non-blocking)

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
