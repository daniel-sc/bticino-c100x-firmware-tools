# Owner-controlled wireless updates: feasibility research

**2026-11-05–06 — C100X Door Entry 1.5.8, hardware `02*06*0`.**

**Conclusion:** wireless installation is technically credible, but neither the
existing USB workflow nor the stock OTA installer can install our current custom
packages over Wi-Fi unchanged. The main obstacle is authorized update execution
in recovery, rather than transferring a file over Wi-Fi.

This preserves the dated research findings. The subsequently approved design is
in [WIRELESS-UPDATE-PLAN.md](WIRELESS-UPDATE-PLAN.md), source usage in
[FLASHING.md](FLASHING.md#wireless-updates-source-builds), and observed validation
in [ACCEPTANCE.md](ACCEPTANCE.md). It complements [manufacturer OTA prevention](OTA.md),
[the USB protocol](PROTOCOL.md) and [boot/recovery limitations](RECOVERY.md).

**Design update, 2026-11-06:** the owner has explicitly permitted scoped recovery
filesystem customization for this feature (ADR-019). Stock recovery preservation
below is a researched alternative, not a continuing hard design requirement.
The [design interview](WIRELESS-UPDATE-DESIGN.md) concluded with approval on
2026-11-07. Source implementation now provisions recovery SSH and supports explicit
wireless transport; hardware acceptance remains pending.

## Findings at a glance

| Question | Result | Evidence level |
| --- | --- | --- |
| Can we reach the running custom firmware over Wi-Fi? | Public-key administrative SSH works; device-local read-only OpenWebNet queries work through it. | Observed on the device |
| Can the Mac use the update ports directly over Wi-Fi? | Stock firewall blocks OpenWebNet and FTP on Wi-Fi. Direct TCP connection timed out. | Running firewall + offline stock main/recovery scripts |
| Does recovery contain Wi-Fi support? | Yes: driver/firmware, ConnMan startup, WPA supplicant and shared saved profiles. | Offline stock recovery inspection; actual recovery association remains untested |
| Does our SSH installation also exist in recovery? | No. Stock recovery has neither the custom account/key nor the independently owned SSH service. | Offline image inventory |
| Can stock OTA install the current custom FWZ? | A fresh normal-mode installation requires manifest/component signatures absent from our four-member package. | ARM branch emulation + inspection of actual signed vendor package |
| Can we retain the vendor manifest signature and sign only our changed filesystem with our own key? | Not with the unchanged verifier: it caches the first successful certificate for subsequent checks. | Three isolated ARM certificate-selection scenarios |
| Does the device have room to stage a package? | About 2.10 GiB was available on shared persistent storage at observation time. | Read-only device snapshot; not a reserved capacity guarantee |

## 1. Wi-Fi exists in stock recovery

The stock recovery image contains:

- `brcmfmac.ko`, `brcmutil.ko` and the Broadcom 43430 firmware files.
- `/etc/init.d/wifi.sh`, which loads the driver. Recovery's application-start
  script attempts driver recovery if `/sys/class/net/wlan0` is absent.
- `/etc/rc5.d/S02dbus-1` and `/etc/rc5.d/S05connman`, with runlevel 5 selected by
  `/etc/inittab`.
- The same `connmand` and `wpa_supplicant` binaries as stock main firmware, plus
  the D-Bus activation service for WPA supplicant.
- ConnMan configuration excluding `usb0` and `eth0`, not `wlan0`.
- `/var/lib/connman` linked to
  `/home/bticino/cfg/extra/72/connman/`, on the shared persistent p7 partition.

The recovery startup XML enables Wi-Fi and includes `bt_dbus_manager` in the
minimal-mode process set. That binary differs between the images; the presence
of matching ConnMan/supplicant binaries does not establish identical complete
network behavior. Recovery's explicit ConnMan startup link is also a difference
from the main image.

The running device had one saved Wi-Fi profile with `Favorite=true`,
`AutoConnect=true`, DHCP and a nonempty passphrase. Inspection returned these
properties only, not the SSID or passphrase. Its ConnMan path resolved to the
same shared directory.

**Interpretation:** there is substantial evidence that recovery is intended to
reconnect to configured Wi-Fi. A recovery boot and actual association/IP observation
are still needed to establish this on hardware. Recovery was not booted during
this investigation.

## 2. Network access is the first concrete barrier

Both stock images have the same
`/etc/network/if-pre-up.d/iptables` (SHA-256
`737cf33df612f090c54505a6bdb283dd27a4d8df623837bee4d9941855235b0b`).
It permits loopback, accepts the OpenWebNet ports on USB and drops other incoming
connections to those ports. It also drops Wi-Fi connections to FTP ports 20, 21
and 11111. SSH port 22 is allowed, but a firewall allowance does not start or
authenticate an SSH service.

Read-only `/usr/sbin/iptables -S` on the running device confirmed those rules.
OpenWebNet was listening on all IPv4 addresses, but the Mac's direct LAN TCP
connection to port 20000 timed out. A device-local connection to
`127.0.0.1:20000`, executed through public-key Wi-Fi SSH, completed the command
handshake and all existing read-only identity/status queries. It reported normal
state `4*0`, expected firmware/hardware/model and an idle update worker.

OpenWebNet has a separate authentication boundary: loopback and the configured
USB host address are trusted; arbitrary LAN addresses are not thereby trusted.
Opening firewall ports alone would not establish an authenticated flashing path.

An SSH tunnel is therefore a credible transport for normal firmware. FTP would
need both control and passive-data forwarding, rather than just one OpenWebNet
forward. FTP was not started or transferred during this investigation.

### Why the same tunnel cannot simply continue in recovery

Our builder modifies the main filesystem only. Stock recovery has:

- No `root2` account or `/home/root/.ssh/authorized_keys`.
- No `c100x-ssh` service or ordinary `S98dropbear` startup link.
- A vendor Dropbear service whose startup can depend on saved configuration;
  our current saved configuration has no `abil_ssh` field.

Even enabling the vendor SSH service would not provision our custom account and
public key in recovery. Administrative access to normal firmware is not evidence
of administrative access to recovery.

## 3. The vendor OTA package is different from the USB package

The public vendor OTA artifact linked from
[upstream issue 44](https://github.com/fquinto/bticinoClasse300x/issues/44#issuecomment-3154130569)
was downloaded to private local research storage:

`https://eliotdmstrg.blob.core.windows.net/bs-classe100x/C100X_010508.tar.gz`

| Artifact | Size | Observed SHA-256 |
| --- | ---: | --- |
| OTA tar.gz | 106258796 | `02502a1d591b34acee89620caa78c21bd32f5f4b4b08c38a2a74aa1888cfb464` |
| Contained `C100X_010508.bin` | 106242072 | `08620d360b16b0a6972f38128abfc3e81005f003c9de01c5ea4e4acc31927e8b` |

The `.bin` is an encrypted ZIP/FWZ. It contains the four familiar files plus
four 256-byte `.sha1.sig` files: one each for the manifest, main filesystem gzip,
recovery filesystem gzip and kernel ZIP. Host OpenSSL verified **all four**
against the stock `/home/bticino/certs/public_cert.pem`. This certificate and the
other bundled certificate are identical regular files in main and recovery.

The manifest, recovery gzip and kernel ZIP match the project's stock pins.
The expanded main filesystem also matches the pinned stock rootfs hash
`80f04c61a9a34032e397d1dc6a1209ad029162a59d08981d7fd9f81348264354`.
Thus this is the same stock firmware content with the additional OTA signatures,
not evidence that a different firmware version is required for OTA.

Our custom package omits these signatures. Copying the vendor signatures into a
modified package cannot authenticate a changed filesystem. The public archive
password provides decryption, not authority to produce a valid signature.
The current flasher's exact four-member package profile also does not admit this
eight-member OTA ZIP as-is.

### Installer validation and certificate selection

Offline ARM execution, with all external calls and writers intercepted, checked
23 manifest/component/dispatch/version/writer cases. Fresh normal-mode installation
rejects
missing or invalid manifest signatures and rejected component validation before
reaching a firmware writer. Separate host cryptographic verification checked the
actual vendor signatures; the emulator's crypto outcomes were simulated.

Three additional ARM scenarios checked certificate selection. On the first
successful verification, the installer retains the certificate path. Later checks
reuse that certificate rather than trying every installed certificate again:

- Vendor-signed manifest followed by vendor-signed component: accepted by the
  simulated crypto results and actual selection/control branches.
- Vendor-signed manifest followed by owner-signed component: rejected even with
  both certificates available in the simulated certificate directory.
- Owner-signed first file followed by owner-signed component: accepted when that
  owner certificate is available.

Consequently, adding an owner certificate only to main firmware and retaining the
vendor manifest signature is insufficient. Consistently owner-signed packages
would also need a working manifest-trust path when stock recovery resumes, or a
different explicitly designed validation/continuation mechanism. Recovery parses
the manifest again; its resumed branch does not repeat the entire fresh-install
component-validation gate. Importantly, the resumed dispatcher **ignores the
manifest-check return value**. The failed-manifest dispatch case reaches a
main-writer stub; this does not prove a malformed or unauthenticated package can
actually install, because parsing, extraction and writing were not exercised
together. These are state-dependent checks, not a complete security audit or a
fail-closed recovery authentication guarantee. Altering persisted stages to skip
validation is not an established update procedure.

The local installer's version check accepts `1.5.8` to `1.5.8`, confirmed in ARM
emulation. Cloud discovery's equal-version filtering is therefore distinct from
the local installer's version gate. It is not the principal obstacle to repeated
custom builds based on 1.5.8.

### A possible main-only coordinator, retaining stock recovery

There is a narrower design opportunity than replacing recovery's trust store:

1. Preserve the exact vendor-signed manifest, stock recovery and stock kernel.
2. Have an owner-controlled coordinator in normal firmware authenticate the
   custom main payload and verify the complete staged package.
3. Follow the evidenced recovery-first lifecycle, with an explicit continuation
   mechanism for the intermediate normal boot.
4. Let stock recovery resume from that legitimate installation state. It can
   verify the unchanged vendor-signed manifest; the inspected resumed main-write
   path does not independently recheck the main component signature.

The actual ARM main-write routine was exercised with extraction/storage calls
stubbed: it reached filesystem and kernel writer stubs without component-signature
verification. This supports the design opportunity; it does not validate an
end-to-end installation or justify seeding arbitrary resume flags.

**This needs a new or adapted normal-side coordinator.** Simply adding a key and
calling the unchanged installer still fails its cached-certificate behavior.
The coordinator would need to establish staged-byte integrity, coherent state,
exclusive ownership, reboot continuation and failure handling, including its
interaction with `no-ota`. A dedicated executable or carefully reviewed adaptation
would itself require validation. The stock installer's weaker resumed checks must
not be mistaken for end-to-end owner authentication.

This is a potentially useful route **without modifying the recovery image**.
It is an unimplemented research candidate, not a reason to claim custom recovery
is fundamentally required for every possible wireless design.

The initial and first-reboot coordinator must already exist in the **old main
firmware**; the uploaded replacement is installed only afterward. The new main
image must also provide authorized final cleanup. Package-path continuity is
unresolved: the vendor manager uses `extra/FW/UPGRADE.fwz`, while recovery's
early-boot script uses `extra/UPGRADE.fwz`. Recovery retains both launch paths.
Selecting one path and excluding competing installation owners is part of the
design, not supplied by the certificate patch.

## 4. Autonomous installation adds lifecycle responsibilities

The stock installer already stages data on shared persistent storage and tracks
progress across main/recovery reboots. That makes a fully uploaded, locally
executed wireless update a plausible long-term design. The running device had
2,257,965,056 available bytes on p7; staging feasibility must still be checked
for each package and its extraction workspace.

There are important integration differences from our current updater:

- The stock OTA state machine can reboot and retry its main-write routine.
  ADR-004's rationale concerns uncertain host-command delivery; it does not by
  itself establish that every internally managed retry is equivalent. Nevertheless,
  stage-6 replay can follow an interrupted attempt, not only a reported local
  failure. Reusing it requires an explicit failure-contract decision. A strict
  prohibition on all installer retries/error reboots is incompatible with this
  unchanged recovery path, and a normal-only patch cannot change that behavior.
  Stage 5 to 6 resets the counter; with functioning persisted metadata, one initial
  attempt plus up to five retries is possible. Missing/unreadable counter data
  returns zero, and increment ignores the persistence result, so this is not an
  unconditional bound under storage failure. Presetting the counter in normal
  firmware is not an established solution.
- The `no-ota` startup policy suppresses the manager and early-boot launcher that
  normally resume installation. A manual update needs its own explicitly
  authorized continuation across the intermediate normal boot, recovery boot
  and final cleanup. Retaining the installer binary alone is insufficient.
- `no-ota` v1 pins the original installer and status library, so an in-place patch
  fails final image verification. A separately named adapted executable can
  preserve those pins, but its new startup/continuation code needs its own
  prevention analysis. Passing the existing verifier does not validate arbitrary
  wrapper behavior. The existing prevention guarantee excludes stock recovery.
- A shell process launched through SSH does not survive a reboot. Uploading first
  solves transfer interruption, not recovery execution or boot continuation.
- The vendor installer's `TEST` argument is **not a dry run**. ARM analysis shows
  writer paths remain reachable and the reboot is merely delayed. No installer
  invocation, including `TEST`, was performed on the device.
- Existing boot fallback checks kernel/DTB loading, not late application/network
  health. Wireless updating would not automatically provide health-based rollback.

Further static analysis found a write-error classification concern. On the
inspected C100X board path, the filesystem HAL writer returns `system()` status
directly (`liblghal.so.0.0.c:1455–1467`), but the installer rejects only negative
results (`dedrifupdater.c:367–371`). A positive shell failure status therefore
follows its apparent-success branch. This needs targeted validation; neither a
local return nor the installer's process exit establishes installed-byte success.
The retry branch also covers extraction and mounting failures, not exclusively
confirmed media-write failures. Counter persistence is at
`libdedrifupdater.so.c:480–555`, with replay transitions at `:786–805`.

### Keeping the Mac connected

The design interview permits the Mac to remain online throughout installation;
autonomous completion is not a requirement. This can simplify normal-mode
coordination and reconnection, but no complete owner-authenticated host-control
path through unchanged recovery has been established.

Recovery honors the saved vendor SSH-enable switch, but no owner-key/account
provisioning hook was found in the inspected startup/configuration paths.
`/home/root` is an ordinary directory in its read-only rootfs, not shared p7
storage; the volatile `/var/lib` handling does not change that. The script named
`set_overlay.sh` configures display framebuffers, not a rootfs overlay.

The daemon has a persistent SDK application mechanism in normal mode, but its
construction is outside recovery initialization and its `working_mode=0` entry
is skipped in recovery. The inspected internal MQTT broker binds to loopback;
cloud messaging has not supplied an owner-accessible Mac firmware-control API.
These are bounded negative findings, not proof that every possible diagnostic
interface is absent. Evidence: `bt_daemon.c:1707–1738,2683–2696,3033–3042,
4754–4764,6208–6211,6250–6289`; stock recovery `etc/fstab`,
`etc/init.d/read-only-rootfs-hook.sh`, `etc/init.d/set_overlay.sh` and
`etc/mosquitto/mosquitto.conf:133–136`.

## Practical direction

### SSH transport and recovery customization audit — 2026-11-06

The source-owned Mac sequence remains a credible candidate. Three loopback SSH
forwards cover its used channels: OpenWebNet 20000, FTP control 21 and passive
FTP data 11111. Passive transfers do not need port 20. Python 3.14's default
IPv4 FTP client uses the control peer's address rather than the PASV-advertised
address, but retains the advertised data port. Dynamic local data ports therefore
need explicit client handling. Current FTP control uses fixed port 21, CLI
flashing owns a USB session, and the existing SSH reader disables forwarding;
these need endpoint/session changes rather than simply passing a LAN address.
Evidence: `updater.py:84–188,207–260`, `__main__.py:198–233`, `ssh.py:160–249`.

Recovery includes the same Dropbear binary, inspected direct dependencies and
service utilities as main, with approximately 76.7 MiB of free filesystem blocks.
Five of the six SSH payload stock-file pins match; its shadow file differs.
Preserve recovery's vendor account records and use recovery-specific guards.
The service approach appears reusable, but recovery startup, authentication,
forwarding and Wi-Fi still need hardware proof. See `payloads/ssh/common.py:9–25`
and the private recovery inventory/dependency records.

The existing recovery integrity gate derives reference contents from the package,
so much of it is reusable after package admission and transport changes. It reads
200 MiB to the Mac and another 200 MiB on-device for independent hashes. Fixed
partition/extent and 21-file kernel assumptions remain. Current package admission
rejects customized recovery; merely dropping that pin without a recovery geometry
contract would be insufficient. This gate verifies bytes and filesystem
consistency, not recovery boot/network operation (`recovery.py:24–120,190–219,
300–360`; `firmware.py:27–34,166–184,257–261`).

Recovery's editable OTA configurations match main, but its application-start
script, cloud binary and some file ownership differ from `no-ota` v1's guards.
Recovery-specific checks and analysis of its cloud startup are needed. Suppression
in destination images does not cover the two phases running old main firmware.

SSH identity also needs an explicit LAN contract: old-main credentials apply
before and after the first reboot, then destination recovery credentials, then
destination main credentials. Existing builds generate fresh host keys; applying
the current hook independently to both images would generate two keys. The USB
verifier's warning-only host-key policy is not authenticated LAN identity
continuity, and the model/version/status queries are not a unique device identity.
Key transitions, package binding, credential changes and endpoint continuity are
still design decisions. No tunnel transfer or recovery boot was tested by this
offline audit.

### Changing-address discovery audit — 2026-11-07

Both extracted images include matching Avahi daemon/config/init files and a
runlevel-5 `S99avahi-daemon` link. The configuration selects IPv4, `wlan0`,
`host-name=Bticino-Classe100X` and workstation publication; both firewalls permit
UDP 5353. No static service-advertisement directory was found. This makes existing
`.local` name resolution a candidate for reconnecting after DHCP changes, not a
validated endpoint contract. The generic name can collide. Evidence: recovery
`etc/avahi/avahi-daemon.conf:21–50`, `etc/init.d/avahi-daemon:111–135`,
`etc/network/if-pre-up.d/iptables:36–40`, and both filesystem inventories.

Matching Wi-Fi driver/firmware, ConnMan and shared profiles support likely WLAN
MAC continuity, but no recovery observation proves it. A compiled-in firmware
MAC is not the individual device identity; any MAC enrollment should read the
actual WLAN address through authenticated existing SSH. Both images have a common
static hostname and `AllowHostnameUpdates=false`; vendor code can conditionally
change the runtime hostname (`bt_daemon.c:4456–4488`,
`liblghal.so.0.0.c:4050–4135`). DHCP client identifier/options and router DNS
registration are not established by these files.

MAC-based rediscovery needs more than an ARP-table lookup: that table is a cache,
not an inventory. Unknown-address discovery needs bounded active probing or
another address source, interface/subnet selection and ambiguity handling. Direct
MAC matching normally needs same-link neighbor visibility; routing, proxy ARP,
client isolation and VPN/interface overlap limit it. mDNS also normally requires
local multicast reachability. Either approach must reject stale/unresponsive
candidates and authenticate SSH with the expected phase key. MACs and advertised
names are locators, not authentication. A host key shared by several devices using
the same package is not a unique physical-device identity either.

The current host code has no LAN scanning or mDNS browsing facility. macOS `arp`
shows cached neighbors; raw BPF probing adds permission/interface work. Apple's
`dns-sd` manual discourages scripting its text output. Re-resolving a supplied
hostname may avoid adding a service browser; a dedicated service would need new
image configuration and bounded host discovery. Packaged macOS local-network
permission behavior and actual recovery mDNS publication still need validation.
These findings are offline only. On 2026-11-07, Q17 selects the configured
`Bticino-Classe100X.local` name as the wireless flasher/preflight default, with one
`--host` override accepting a hostname or IP and fresh resolution on reconnect.
The owner declines builder hostname customization. MAC scanning is deferred;
actual mDNS behavior still requires hardware validation.

### Remaining SSH workflow audit — 2026-11-07

Existing credential handling can be reused with distinct existing-main and
destination configurations: old credentials apply through the normal reboot and
readback; destination credentials apply in recovery and new main. Password mode
already uses a private askpass broker and in-memory reuse for reconnects; the
invoking user's key/agent context survives sudo. A package offering both methods
does not require the client to use both (`ssh.py:37–79,95–158,242–249,291–315`).

The current SSH reader does not support user-config aliases: it uses `-F /dev/null`
and a fixed destination (`ssh.py:160–184`). DNS hostnames and SSH aliases are
different features. Supporting aliases by loading SSH config also admits proxy,
command and connection-sharing semantics and needs a deliberate boundary.

Current known-hosts files are recreated empty for every read. Reports retain
fingerprints, not persistent trust records (`ssh.py:186–211,228–236`). Strict LAN
identity therefore needs enrollment/import and reusable trust state. An
application-owned store and isolated phase-specific files are a candidate, not a
selected design. Existing-main key continuity across its reboot is required by
Q14; an installation that regenerates unpredictable keys cannot qualify without
an evidenced next identity. Destination trust promotion and its timing remain
decisions. Do not infer that the documented research alias establishes a trusted
entry for the proposed default hostname.

The existing `Ext4` boundary supports bounded read-only inspection needed for
package admission (`ext4.py:28–59,72–120`); wireless already needs e2fsprogs through
Q11. Both images need bounded private expansion. Current stock-recovery admission
must be replaced by a supported geometry/features contract while retaining
manifest/kernel pins. Extract standalone content checks from builder-context SSH
verification for accounts, authentication, metadata, startup and dependencies.

Host public-key extraction is a concrete gap: the image stores a Dropbear private
key, and the current final verifier only checks its algorithm-name prefix. There
is no existing parser/cryptographic extraction API. A bounded parser would be new
code; the shipped `dropbearkey` executable is a reuse option but adds an explicit
wireless tool dependency. Validate the key and the service's configured key path,
not just an advertised fingerprint (`payloads/ssh/verify.py:45–47`,
`prepare.py:67–75`; `packaging/build.py:228`).

Offline checks can match a supplied public key or password to destination access
configuration, but cannot prove actual recovery authentication. Password-hash
verification is not implemented; the existing OpenSSL hashing path uses a helper
whose stdin is backed by a temporary file (`host.py:33–46`). That helper is not
suitable for a memory-only login-password contract without changes. An agent's
advertised key does not guarantee future signing availability either.

Recovery prevention still needs a targeted trace of its different cloud binary's
startup dependency on the absent manager. Preserve recovery's own application
startup script. Validate both filesystems after repacking, staged-state and
composition cases, custom builds without SSH and explicit vendor-update allowance.
These are offline prerequisites; broad caller/tunnel research need not be repeated.

### Recovery prevention applicability resolved — 2026-11-07

Direct comparison and disassembly establish that recovery supports the same
four-part startup suppression policy as main. Its `bt_eliot` differs in exactly
21 bytes: 20 GNU build-ID bytes and one release-log constant (file offset 0x7068,
ELF VA 0x17068). All other bytes match, including the inspected startup/status
instructions. Recovery `fw_manager` is byte-identical to main. Private provenance,
comparison and annotated disassembly are in
`.local/recovery-cloud-startup-20261107/FINDINGS.md`.

Recovery ELF addresses establish:

- `0x173a0–0x173c4`: read `FwUpdate` into the application state.
- `0x1c2a0–0x1c318`: zero bypasses initial manager status coordination and schedules
  cloud startup.
- `0x2d330–0x2d338,0x2d734–0x2d794`: zero also bypasses the connected-network
  pending firmware-status dependency.
- `0x20708–0x20778,0x208dc–0x20990`: errors/zero status retry; nonzero states
  proceed toward cloud startup. Persistent metadata does not override `FwUpdate`.

The manager still has fresh-install and persisted-stage resume routes independent
of that cloud setting. Therefore retain all four controls: remove manager startup,
set cloud `FwUpdate=0`, remove early Dedrifu startup and retain daemon Dedrifu
disablement. Preserve recovery's own application startup script and Wi-Fi fallback;
no additional script replacement or binary patch is indicated. Use recovery-aware
file hashes/ownership in the verifiers. This closes the static applicability gap,
not hardware validation of recovery Wi-Fi, SSH, cloud operation or prevention.

### Existing-main prevention audit — 2026-11-06

The selected Mac-driven sequence runs old main both before and after writing
recovery (`updater.py:218–260`). Requiring an already-installed, known `no-ota`
main is a bounded first-version eligibility option: its prevention persists
across that reboot. It excludes the documented current installation, which has
SSH but still permits manufacturer OTA. This was a proposed restriction, not a
validated live eligibility check; the owner subsequently selected the exception
described below instead.

The offline verifier supplies exact policy references: main XML/cloud settings,
reduced XML, launcher/component pins, absent daemon INI override and absent
installer boot links (`payloads/no-ota/common.py:8–34,48–72`, `verify.py:5–10`).
Installed-file checks alone do not establish loaded process configuration. The
daemon reads volatile XML followed by an optional INI (`bt_daemon.c:3632–3641`);
configuration is loaded into memory during initialization (`:2188–2212`). Relevant
custom/persistent startup influences also need bounded treatment. No generic
attestation interface for arbitrary earlier custom firmware was established.

Runtime inspection must distinguish the manager, installer and launcher children
from the protocol update worker. Query 42 checks only `bt_device`'s own child PID
(`bt_device.c:800–813,5966–5980`); the manager launches its installer separately
(`fw_manager.c:377–398`). Absent packages, flags or processes are snapshots, not
continuous exclusion. Checks after the intermediate reboot cannot protect its
earlier rcS installer launch.

No already-evidenced persistent SSH-applied inhibition covers every route without
changing the main-image startup policy. Cloud settings, download/network blocking,
the stock daemon disable flag, stopping the manager and runtime XML changes do not
establish complete reboot-persistent prevention (`OTA.md:300–370`). A temporary
service stop is therefore not an established bootstrap solution.

Requiring known protected main would simplify routine wireless eligibility, but
installing it first is a separate bootstrap operation. USB transport itself does
not prevent manufacturer installation; the existing USB workflow excludes these
initial transition windows from its prevention guarantee (ADR-018). Protected
migration from an OTA-enabled main remains unresolved if that starting state must
be admitted. This audit used existing offline evidence only.

**Decision update, 2026-11-07 (Q15):** the owner accepts the first-installation
competition window while OTA-enabled old main runs. Check for known staged
packages and active manufacturer installation before starting and reject those
observed conditions; do not treat the checks as continuous exclusion. Both
destination images must prevent manufacturer installation. Pre-installed
`no-ota` and a separate persistent in-place suppression mechanism are not required.
This accepts the gap rather than establishing protected migration. No device
write or complete implementation design has been approved.

**Policy revision, 2026-11-07 (Q18):** the owner subsequently accepts competing
manufacturer-installation risk for later unprotected update phases too. SSH
selection provisions both environments; prevention remains independently optional
and applies to both when selected. Thus wireless installation does not require
protected destination images. The staged-package/activity checks remain snapshots.
Q20 subsequently accepts default-on prevention for custom builds; Q27 extends
the default to every build, including one with no optional features. The explicit
`--allow-vendor-updates` option retains manufacturer behavior and, with no other
customizations, stock contents. The policy stays independent of wireless transport.

| Candidate | Assessment |
| --- | --- |
| Point today's flasher at the Wi-Fi IP | Blocked by firewall/authentication and recovery access. |
| Upload today's FWZ and launch stock OTA | Blocked by package signatures; continuation also conflicts with OTA prevention. |
| Authenticated SSH transport in both environments, retaining the existing vendor protocol | Reuses the researched write sequence, but requires provisioned recovery access, reconnect/identity handling and FTP forwarding. |
| Main-only owner coordinator with the vendor-signed manifest and stock recovery continuation | Promising candidate for preserving stock recovery; requires new/adapted normal-side validation and fully established lifecycle/state handling. |
| Consistently owner-signed autonomous OTA through the vendor installer | Requires owner trust wherever its manifest is parsed, plus continuation, failure-policy and OTA-prevention integration. |

One possible product shape is **USB bootstrap followed by owner-authorized Wi-Fi
updates**. USB is not inherently required for bootstrap when administrative SSH
already works in normal firmware: the established recovery-first sequence could
install prepared SSH-enabled recovery through normal-mode control before recovery
SSH is first needed. Q15 now accepts the old-main prevention gap for initial
wireless installation with the stated checks. The interview also selects
Mac-driven SSH transport and mandatory recovery integrity verification (Q10/Q11),
with prepared recovery customization permitted by ADR-019. The currently
implemented package profile still pins stock recovery. The complete implementation
design remains unapproved.

Before implementation approval, establish an integrated offline lifecycle model:
old/new-main launchers, exact package path, persisted transitions, staged-byte
integrity across reboots, stale/conflicting flags, competing launchers and failure
behavior. The isolated ARM cases are not an integrated three-reboot simulation.

Recovery Wi-Fi association and reachability remain hardware evidence gaps for a
network-controlled design. A fully staged autonomous design need not depend on
recovery networking; its immediate blockers are lifecycle, integrity and failure
policy. Connectivity can be observed during an otherwise-planned maintenance
session with USB available. A full wireless flash and functional acceptance would
be separate later validation after an implementation exists.

## Evidence and reproduction

Live snapshot: **2026-11-05 21:36 UTC**, public-key SSH, UID 0, normal firmware,
Wi-Fi up and USB network down. Runtime updater/network binary hashes matched the
stock files inspected offline. Known OTA staging paths and update flags were
absent. Only reads and read-only protocol queries were performed; no firmware,
configuration, service or reboot operation was requested.

Private evidence is in `.local/wireless-research-20261105/`:

- `gather.py`, `offline.json`, `live.json`, `live-firewall.json`: image comparison,
  profile-property/storage inspection, listeners, read-only queries and rules.
- `package.py`, `package.json`: vendor download, bounded archive inspection,
  component hashes and host OpenSSL signature verification. The expanded-main
  hash was added by a separate streaming gzip/SHA-256 check.
- `emulate_installer.py`, `installer-emulation.json`: 23 ARM branch cases.
- `emulate_cert_cache.py`, `certificate-cache-emulation.json`: three certificate
  selection scenarios using actual verifier instructions and simulated I/O/crypto.

Run private analysis with mise-managed Python; ARM scripts use the existing
research `.venv` with Unicorn, Capstone and pyelftools. Vendor files, downloaded
firmware and private evidence remain Git-ignored. No firmware installer or writer
was invoked on the device. Analyzed ARM code executed only inside the emulator,
with all external effects intercepted.

Key local decompilation references:

- `dedrifupdater.c`: manifest gate `0x131b4`, signature verifier `0x12bb4`, component
  gate `0x13420`, dispatcher `0x13684`, main/recovery writers `0x12638`/`0x128ec`,
  manifest parser `0x15448`/`0x14d84` and persistent extraction path `0x13abc`.
- `libdedrifupdater.so.c`: `StatusMachine::next_step` at Ghidra address `0x1258c`
  (shared-library ELF address `0x258c`), for reboot transitions and attempt limits.
- `bt_daemon.c`: recovery initialization `0x1b910`, process startup `0x1f8a0`
  and configuration/service decisions; `openserver.c:5301–5343` for loopback and
  trusted-source authentication.
