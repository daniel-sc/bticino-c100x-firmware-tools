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

**v0.2.0 is published:** the stable release includes SSH OTA flashing, dual-image
SSH and default vendor-update blocking. Release CI, downloaded signed-artifact
checks, a real SSH+MQTT build and stable Homebrew installation passed. See the
[publication record](VALIDATION-HISTORY.md#2026-11-07-v020-publication-and-validation).

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
| Distribution | Stable v0.2.0 signed/notarized download, checksums, all 84 native signatures, relocated smoke, real SSH+MQTT firmware build, dual-image authentication admission and Homebrew installation checked. |
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
- [x] **Release commit CI:** macOS and Linux CI passed for `4ae6480` before
      tagging `v0.2.0`.
- [x] **Signed publication:** tagged CI, signing/notarization and downloaded
      checksum, signature, provenance, relocated smoke and real build checks passed.
- [x] **Stable Homebrew channel:** `Casks/c100x.rb` version/checksum published in
      tap commit `867825d`; preview-to-stable installation, `c100x --version`
      and `builder-doctor` passed.

## Linux package checks (2026-11-10)

On Ubuntu 24.04 x86-64 in Docker, all 331 offline tests passed with builder tools
and native MQTT coverage, without skips. The Linux tarball built successfully;
the extracted, relocated bundle passed smoke tests with networking disabled,
including synthetic firmware builds, payload hooks and simulated SSH updates.
ELF dependency/glibc checks and dependency-source archive hashes passed.
Bundled tools also passed `builder-doctor` in a minimal Ubuntu 24.04 container.
These are local package checks; no new hardware run or release publication occurred.

## Experimental Linux USB (2026-11-12)

Ubuntu 24.04 and 26.04 Desktop x86-64 with default NetworkManager are the agreed
reference targets (ADR-020). A complete USB flash, normal/recovery handover and
cleanup passed on Ubuntu 26.04.1 below; the owner subsequently confirmed household
functionality passed. Ubuntu 24.04 hardware coverage remains open; packaging checks
alone do not establish it.
Use the [focused session checklist](LINUX.md#prepared-hardware-session) for further
validation. A checklist or build does not itself authorize a device write.

Offline worktree checks on 2026-11-12 passed all 347 tests in the Ubuntu 24.04
build container with builder/native-MQTT coverage and no skips. Seven focused
Linux USB tests cover ancestry/ambiguity, temporary-profile restoration (including
uncertain activation), re-enumeration, route conflicts, source/ownership checks,
root admission and cancellation cleanup. Ubuntu NetworkManager 1.46 accepted the
profile arguments using `nmcli --offline`; no host network or device was changed
by that check. The initial workstation run lacked `dropbearkey`; its builder
failure was resolved by running in the existing dependency-complete build container.

The local `0.2.0-alpha.linuxusb` bundle built with dependency sources and passed
ELF/glibc auditing and relocated packaging smoke with networking disabled. Its
bundled `ip` JSON route query and builder tools also ran in a minimal Ubuntu 24.04
container. One smoke attempt hit the existing recovery test's exact mocked-clock
assertion (`120.001` versus `120`); a rerun passed without a code change. These
checks establish packaging/offline behavior, not USB hardware operation. No release
was published.

Independent fresh-context correctness and standards reviews found two cleanup
issues: ambiguous/disappearing interface discovery could skip owned-profile
deletion, and cleanup warnings dropped tool diagnostic notes. Both were fixed
and rechecked by the reviewers. All nine focused Linux USB tests passed after
the fixes, including profile removal despite discovery failure and retention of
cleanup diagnostics without masking the primary operation error.

Review fixes on **2026-11-13** passed all eleven focused Linux USB tests. Two new
reproductions failed before the fixes and passed afterward: a real process-group
SIGINT during simulated profile deletion, and simulated NetworkManager hotplug
lag followed by readiness (plus a persistent-unmanaged timeout). A live read-only
NetworkManager check confirmed the device-list query handles existing and absent
interfaces. These checks changed no host profiles and performed no device access.
An additional real SIGTERM check confirmed ordinary cancellation still kills the
isolated command child. The full worktree suite completed in the network-disabled
Ubuntu 24.04 build container: 348 passed, with three native MQTT tests skipped
because their library was not configured. The host-only run lacked `dropbearkey`.

### Linux read-only hardware probe (2026-11-12)

On Ubuntu **26.04.1**, kernel `7.0.0-43-generic`, NetworkManager `1.54.3`,
USB `1da4:0056` enumerated with native `rndis_host`, `cdc_acm` and `usb-storage`.
Sysfs discovery identified `enx3e4766b22ca8`; NetworkManager already managed an
active connection with host `192.168.129.2`. Both automatic and explicit-source
route queries selected that USB interface for `192.168.129.1`. Source CLI and
local packaged CLI read-only probes passed: firmware 1.5.8, hardware `02*06*0`,
model `1.0.99`, normal status `4*0`, and increasing uptime. The USB-associated
storage device was not mounted.

This validates normal-mode native USB/read-only protocol access on the 26.04
target, not the Ubuntu 24.04 target. The connection existed before the
initial test; managed profile activation/restoration was initially blocked by
unavailable noninteractive sudo.

After the owner enabled sudo, the local packaged interpreter/backend successfully
activated its temporary profile, passed route/source checks and read-only normal
identity, deleted that profile and restored the original active connection UUID.
The complete profile UUID set matched the pre-session set afterward. A second
idle host session received SIGTERM with no device write active: cancellation was
handled, the original connection/profile set returned, and subsequent read-only
identity still passed. Uptime continued increasing (no device reboot).

These establish normal-mode managed activation, ordinary exit and idle-cancellation
cleanup on Ubuntu 26.04.1. No ring/call/audio/door-release, transfer, reboot or
firmware-write command was sent during those initial checks. The subsequently
authorized full flash is recorded below.

### Complete Linux USB flash (2026-11-12)

The owner explicitly authorized flashing the supplied `custom-0.2.0-alpha.1.fwz`
(106027525 bytes, SHA-256
`4052c303a348c7f47504d540526dadc5623b6ede5c73d2aec4f9e764b1202197`).
Local archive inspection and managed read-only preflight passed. Before starting,
read-only identity showed normal `4*0`, uptime over five days and an idle worker;
no preceding write had started. `systemd-inhibit` held sleep, idle and lid-close
blocking throughout the flash. No global flash-kill timeout was used.

The local `0.2.0-alpha.linuxusb` bundle completed all four payload transfers and
three verified reboots on the Ubuntu 26.04.1 host above: recovery filesystem/kernel,
normal reboot, main-kernel clear and recovery boot, main filesystem/kernel, final
normal boot. Native USB interface names changed at every reboot; the managed
session discovered and configured each new interface. The recovery gzip differs
from stock (SHA-256 `1fedd776384d92cda1374c8c8dc5a74f3b0ffd4dfabe111e05d9f4b973d539ac`),
so this run adds customized-recovery USB handover coverage. Recovery's bound host
driver was not separately captured; the sequence establishes working recovery
networking, not an observed `cdc_ether` driver identity.

After completion, an independent read-only probe reported firmware 1.5.8,
hardware `02*06*0`, model `1.0.99`, normal `4*0`, uptime 41 seconds and idle worker.
Final main used `rndis_host`; no `c100x-usb-*` profiles remained. NetworkManager
had an ordinary active wired connection for the new interface incarnation.
Private inspection, preflight, flash and final-state logs are under
`.local/usb-hardware-20261112/`.

No ring/call/audio/door-release commands were sent by the automated validation.
The owner subsequently confirmed household functionality passed after this flash.
This adds owner-reported functional acceptance to the observed full USB
protocol/transport completion. Individual household test steps were not supplied;
post-flash SSH/MQTT acceptance and full installed-byte readback are not established
by that report. No uncertain write was retried.

## Wireless and dual-image hardware coverage

**PR #8 additions:** the generalized 1.5.7 source-profile, regenerated-key and
SSH resume/recovery paths have not been hardware-validated. The contributor
reports a successful 1.5.7 → 1.5.8 update using earlier device-specific code;
the 1.5.7 hashes come from that device, not an official image comparison.
This does not extend the passed results below.

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
- [x] **USB with customized recovery:** the 2026-11-12 Ubuntu 26.04.1 flash above
      completed recovery boot/networking and the full USB sequence using the supplied
      customized recovery. This does not establish its vendor-blocking runtime behavior.

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
- Linux firmware building and SSH updates are available, with limited
  hardware validation (see [Linux](LINUX.md)). Linux USB is experimental;
  release bundles target Apple Silicon macOS 15+ and x86-64 Linux with glibc 2.39+.
  WSL and Windows/MyHOME import of generated images remain unvalidated.
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
