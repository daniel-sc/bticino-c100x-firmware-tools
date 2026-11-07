# Manufacturer OTA updates

## Current status

Builds **block manufacturer installation in both main and recovery by default**.
`--allow-vendor-updates` opts out. This is independent of SSH selection and
flashing transport.
See [usage](BUILDER.md#ota-prevention) and [implementation details](BUILDER-REFERENCE.md#ota-prevention-implementation).

On 2026-11-07, a blocked-policy image completed a full wireless SSH flash,
installed recovery verification and final SSH verification; the user confirmed
post-flash household tests passed. Runtime inspection of prevention and USB
flashing with customized recovery remain follow-up coverage; no live manufacturer
installation was triggered as a blocking test. See the
[hardware record](VALIDATION-HISTORY.md#2026-11-07-complete-wireless-ssh-flash).
Existing unprotected firmware remains outside its protection until replacement.
The owner accepts competing-installation risk in unprotected phases, with
staged-package/activity checks. See ADR-019 and
the [wireless design](WIRELESS-UPDATE-PLAN.md). The sections below preserve the
dated v1 investigation; its main-only scope was subsequently expanded. Historical
pending statements below describe that investigation, not the current status above.

## Original finding — 2026-11-05

**The v0.1.0 SSH/MQTT firmware does not prevent manufacturer OTA updates.**
The stock cloud/update machinery remains enabled. A successful manufacturer
update replacing the main filesystem can remove the installed SSH account, keys,
services and MQTT bridge/configuration. Building from 1.5.8 does not provide
protection against a later vendor release.

This conclusion comes from source review, read-only image comparison and offline
vendor-binary analysis. No OTA installation was triggered or observed on our
device during this investigation. Vendor rollout timing and server-side consent
policy were not established.

## What was verified

The builder starts from pinned stock and applies only selected payloads
(`classe100x/builder.py`). The bundled SSH and MQTT payloads modify their accounts,
configuration, services and startup links; neither changes vendor OTA behavior.
SSH's `NO_START=1` applies only to the vendor Dropbear init service, not updates.
Arbitrary user-authored payloads may behave differently.

The SSH-v2 + MQTT-v1 image built by the downloaded **v0.1.0** release during
[release validation](VALIDATION-HISTORY.md#2026-11-05-version-010-publication-and-validation)
was reopened and compared with the hash-verified stock rootfs:

| Checked contents | Result |
| --- | --- |
| `bt_eliot`, `fw_manager`, `dedrifupdater`, `bt_daemon`, `bt_device` binaries | Byte-identical to stock |
| `libdedrifupdater.so` | Byte-identical to stock |
| `cfg/bt_eliot`, `cfg/fw_manager`, both `stack_open` XML files, `sp/dbfiles_ws.xml` | Byte-identical to stock |
| `dedrifu.sh`, `dedrifu_env.sh`, `bt_daemon-apps.sh`, `bt_hosts.sh` | Byte-identical to stock |
| Dedrifu early-boot links and vendor application startup link | Same targets as stock |

Paths under `cfg`, `sp`, `bin` and `lib` above are beneath `/home/bticino`;
init scripts are beneath `/etc/init.d`, and `bt_hosts.sh` is beneath `/bin`.
The image contains both custom services. Its unchanged vendor configuration has:

```ini
[Application Parameters]
FwUpdate=1
autoDownload=1
autoDownloadMinutesRange=120
```

`stack_open.xml` retains `bt_eliot` and `fw_manager` with `working_mode=1`.
The preserved version metadata still identifies stock 1.5.8.

## Vendor update path

Offline decompilation of the stock 1.5.8 binaries establishes:

1. **Cloud control:** `bt_eliot` registers Azure IoT Hub desired-state and direct
   method callbacks. Desired firmware metadata includes `firmwareId`, `version`,
   `firmwareUri` and `fileSize`. Download hosts can therefore come from cloud
   metadata rather than one fixed hostname.
2. **Automatic download:** when firmware becomes available and the updater is
   ready, `autoDownload=1` schedules a download with a randomized delay (configured
   range up to 120 minutes). This is distinct from installation.
3. **Installation:** the cloud `firmwareUpdate` method accepts the downloaded
   state and sends the internal `gateway.fwInstall` request. `fw_manager` launches
   `dedrifupdater` with `/home/bticino/cfg/extra/FW/UPGRADE.fwz`.
4. **Replacement:** the installer includes a main-filesystem update through
   `update_fs`, not preservation/merging of our added files. The separate early-boot
   `dedrifu.sh` also launches the installer when
   `/home/bticino/cfg/extra/UPGRADE.fwz` exists.

The application reports “Pending user consent for installation” after download,
but the cloud method can advance installation. This does not establish whether
the vendor requires fresh app consent for each rollout. Uninstalling the mobile
app does not remove the device's own cloud client.

Normal discovery compares the advertised version against the running version
and treats an equal version as up to date. **Repeated 1.5.8-to-1.5.8 overwriting
was not established.** Already-staged updates and other entry paths need separate
analysis; an unchanged version or failed SSH connection alone proves neither an
update nor its absence. This project previously diagnosed a separate vendor
SSH-service race, addressed by SSH payload v2 (ADR-017).

### Local evidence references

These ignored research artifacts contain vendor code and are not distributed:

- `research/device/bt_eliot.c`: configuration at lines 117–122; auto-download
  scheduling at 5180–5213; cloud methods at 8295–8480; desired metadata at
  10484–10680; callback registration at 10877–10896; version comparison in
  `FUN_00036a64`; download/install message construction at 14280–14358.
- `research/device/fw_manager.c`: topic registration at 939–942; install dispatch
  at 1606–1608; downloaded-state gate in `FUN_000167d8`; installer launch in
  `FUN_00013db8`.
- `research/device/dedrifupdater.c`: main filesystem/kernel replacement in
  `FUN_00012638`; `research/device/liblghal.so.0.0.c`: `update_fs` at `0x1b8b4`.
- `.local/ota-research-20261105/compare.py` and `comparison.json`: read-only
  comparison procedure and per-file hashes. The checked FWZ SHA-256 is
  `1c9105933c5832a11b10ee19be67bf581f20b40c0878d65b2cfacba2719690d3`.

## What the upstream reports establish

Issue [fquinto/bticinoClasse300x#44](https://github.com/fquinto/bticinoClasse300x/issues/44)
contains user reports of modified C100X 1.5.7 automatically updating to 1.5.8 and
losing access. A later comment suspects an equal-version overwrite but supplies
no verification. The thread does not demonstrate a reliable prevention method.

The inspected upstream checkout, revision
`55d2dab9538e8c89e6c3efd559845c344b910327`, implements its legacy “no new firmware
notifications” choice in `legacy/main.py:954–963` by adding localhost mappings for:

- `prodlegrandressourcespkg.blob.core.windows.net`
- `blob.ams25prdstr02a.store.core.windows.net`

It does not disable the installer. In contrast,
[issue #35's device-download report](https://github.com/fquinto/bticinoClasse300x/issues/35#issuecomment-2264923223)
identifies `eliotdmstrg.blob.core.windows.net/bs-classe100x/C100X_010507.tar.gz`.
Issue #44 links the corresponding 1.5.8 URL. Those localhost mappings do not cover
that hostname, and download blocking cannot prevent an already-staged install.

## Prevention status

The optional `no-ota` payload combines the startup controls described below.
Its hardware behavior is not yet validated.
Neither `autoDownload=0`, `FwUpdate=0` nor a hostname blocklist has been established
as a complete installation barrier. The inspected `FwUpdate` checks affect startup
status coordination; they do not demonstrate a guard around every cloud install
method or the early-boot installer.

The policy covers both cloud-initiated and already-staged installation paths and
retains explicit USB handlers; vendor app/calling behavior requires hardware
validation. Offline checks simulate update paths rather than trigger a real
vendor write. Moving outside 1.5.8 also exceeds this tool's current compatibility
profile; reinstalling our image after a newer OTA is not a validated workflow.

## Accepted prevention design — 2026-11-05

The requirements and mechanism below are agreed in
[ADR-018](DECISIONS.md#adr-018-opt-in-ota-prevention-through-coordinated-startup-configuration).
Implementation is complete; hardware validation is pending.

- **OTA prevention** blocks manufacturer-initiated installation, including
  app-approved updates and previously staged packages, while the protected normal
  firmware runs. Stock recovery and the old-main/recovery phases of installing
  the protected image are outside the guarantee. Explicit USB flashing remains
  available; vendor fixes require a deliberate manual update.
- Vendor app notifications, remote answering and calling must remain functional.
- Prevention is independently selected through `--payload no-ota`,
  with no SSH or MQTT dependency. Stock/no-payload builds retain vendor behavior.
- Re-enabling vendor OTA requires rebuilding without `no-ota` and explicitly
  USB-flashing that image; no runtime toggle is planned.
- Vendor firmware-update prompts may remain visible. Preserving normal app
  functions and blocking installation take priority over prompt suppression.
- Existing staged packages and vendor update-status data are left untouched.
  Downloads may continue in the first version; retained packages can become
  actionable in stock recovery or after removing prevention.

The selected mechanism suppresses the updater's configured launch paths while
retaining its binaries and script. See the implementation checks below and
[domain vocabulary](../GLOSSARY.md).

### Mechanism findings

Further offline inspection found that refusing execution of `dedrifupdater` is a
candidate common barrier for the inspected main-firmware installation paths.
USB update workers in `bt_device` call the filesystem/kernel writers directly
(`FUN_0001e55c`), independently of that executable.

A replacement executable that simply exits with an error is not equivalent to
refusing execution: `fw_manager` records successful process creation and then
waits for persistent update flags, without observing that child's exit status.
Its resume path also invokes the installer (`FUN_00014018`). Spawn refusal and
its app/status consequences require separate consideration; the caller-side
failure branches have now been checked as described below.

Read-only comparison of stock main and recovery images confirmed the same
installer and early-boot `dedrifu.sh` route in both, with access to the shared
persistent data partition. A main-only payload therefore cannot enforce prevention
while stock recovery runs, or during the old-main/recovery phases of its initial
USB installation. Re-enabling the installer may also expose retained packages and
status. The agreed first-version scope excludes these recovery/transition windows;
preserving stock recovery is part of the current fixed package profile (ADR-007).

### Installed-file caller inventory

Both complete stock image namespaces were enumerated and their reachable regular
files scanned: **5,555 main files (981 ELF binaries/libraries)** and **3,283
recovery files (599 ELF binaries/libraries)**, plus all symlinks. Image hashes
were unchanged. Each image has exactly one installer executable, script and
installer-status library, with no alternate hardlink, identical-content copy or
executable symlink alias found.

The discovered launch routes are:

| Caller | How it reaches the installer | Gate |
| --- | --- | --- |
| `fw_manager` | Direct spawn for a new request or persisted resume; `extra/FW/UPGRADE.fwz` | Its own state machine |
| `rcS` → `S96-dedrifu.sh` | Early-boot script; `extra/UPGRADE.fwz` | Package exists; no OTA configuration check |
| `bt_daemon` → `dedrifu.sh` | Detached script invocation | `root/sw/dedrifu/enable`, already zero in stock |
| `bt_eliot` | Indirect `gateway.fwInstall` request to `fw_manager` | Metadata and downloaded state; not `FwUpdate` |

The boot script backgrounds its test-and-launch expression. Host-shell simulation
of its control flow returned script status `0` even when the background executable
was missing (`127`), non-executable (`126`), or exited with an error. It has no
wait, fallback, retry or reboot. It unconditionally removes `DEDRIFU_RUNNING`
before attempting installation. The daemon's `call_daemon` helper detaches the
script; eventual installer failure is not propagated back to the daemon.

Only `bt_device` and `dedrifupdater` import the four inspected main/recovery
filesystem/kernel HAL writers. `libdedrifupdater.so` contains status/platform
machinery, not a second writer. Peripheral Cortex-M0/DSP update scripts do not
replace the Linux firmware. The protocol writers used by our USB workflow remain
independent of the OTA installer; the vendor handlers themselves are not
intrinsically restricted to the electrical USB interface.

This inventory establishes installed-file/reference coverage, not arbitrary
privileged-code behavior or every possible network input. A separate generic Qt
update-control sender was also found; it sends an OpenWebNet request rather than
executing a writer. Follow-up tracing found no functioning stock installation
route for its WHO130/WHAT2 command: static `openserver` routing has no WHO130
destination, `fw_manager` only logs ordinary OpenWebNet frames, and `bt_device`
rejects WHO130. The discovered WHO130 consumer in `bt_answering_machine` handles
dimension-1 firmware-status broadcasts by updating LEDs, not installing firmware.

WHO130 evidence: `openserver.c:6267–6359,11684–11742`, `fw_manager.c:1002–1049`,
`bt_device.c:862–874,4664–4667,7635–7636,8189–8196`; answering-machine ELF
addresses `0x3ba7c` → `0x36050` → `0x1ed60` (`ledlghal::manage_scenario`).
Detailed routing and numeric-consumer analysis is private in
`.local/ota-caller-research-20261105/WHO130-FINDINGS.txt`.

Reproduction, per-file hashes, reference inventories, shell simulation and
startup details are private in `.local/ota-caller-research-20261105/FINDINGS.md`
and its companion scripts/results. No persistent device-data partition was
copied for this inventory.

### Missing-installer behavior: caller-side verification

The stock `fw_manager` ARM instructions were disassembled and executed in an
isolated Unicorn emulator with all external calls intercepted. Process creation,
flag reads, logging and messaging were simulated; no vendor program was launched
on the host or device. The 33 cases cover fresh requests, successful creation,
all three active procedure values with persisted stages 1–9, and a spawned stub
that never produces update flags. This verifies caller branches, not the target
OS, cloud service or app UI.

- **Fresh install request:** `g_spawn_async` failure is returned through
  `FUN_00013db8` and `FUN_000167d8`. The dispatcher publishes JSON error `-32000`
  on the request's reply topic and retains downloaded state `8`. It does not
  enter installing state `9`. The caller discards the detailed spawn error.
- **Persisted resume:** in initial state `0`, an active procedure and stage 1–9
  cause the timer callback to spawn the installer. Failure leaves state `0` and
  returns true to keep the timer active. The timer is registered at one-second
  intervals; repeated callbacks make repeated failed launch attempts and log
  `Start DeDriFu`. No failed-spawn backoff or retry cap appears in this path.
- **Executable error stub:** successful creation moves a fresh request to state
  `9`, even if the child immediately exits. Without procedure flags it remains
  there on subsequent callbacks. This is why `exit 1` is not a clean substitute
  for a missing/non-executable installer.

Exact machine-code references: launch/result at `0x13e2c–0x13e50`; propagation
at `0x16824–0x16830`; request error branch at `0x15ba4–0x15bc8`; resume launch at
`0x14270–0x142dc`; repeating callback return at `0x14050–0x14068`; one-second
timer registration at `0x1596c–0x15994`. `libdedrifupdater.so`'s `reload_flags`
establishes that the fields tested are procedure and stage, not child exit status.
Private reproduction scripts, annotated disassembly and results are under
`.local/ota-research-20261105/` (`disassemble.py`, `emulate_fw_manager.py`,
`fw-manager-emulation.json`).

### Cloud response and startup coupling

`bt_eliot` initially acknowledges an accepted cloud `firmwareUpdate` method with
status `200` and `Installing`, before receiving the internal installation result.
On the internal `fwInstall` error it queues reported firmware states
`Error installing`, then `Pending user consent for installation`. Its downloaded
state remains `8`; another cloud request can therefore be accepted. This branch
does not itself schedule an installation retry. Actual app presentation and cloud
delivery order were not exercised.

With `FwUpdate=1`, initial cloud connection is coordinated with
`gateway.getFwStatus`. An absent manager produces a five-second internal request
timeout followed by a two-second status-query retry. A manager reporting state
`0` also causes a two-second query retry. A missing installer combined with
persisted resume state can therefore obstruct initial cloud startup, not merely
produce an update error. `FwUpdate=0` bypasses that dependency, but does not stop
the manager's own repeated resume attempts.

Evidence: `bt_eliot.c:2946–2964,5363–5387,5516–5565,8454–8480,8559–8569,
11099–11114`; stock `libjel.so`'s `mqtt_publish` selects a five-second response
timeout and synthesizes error `-32000` when unanswered. Its private decompilation
is `.local/ota-config-research-20261105/libjel.c:362–666`.

### Configuration audit

No inspected configuration key disables every normal-firmware installation path.

| Setting | Established effect | Why it is insufficient alone |
| --- | --- | --- |
| `bt_eliot`: `FwUpdate=0` | Bypasses initial updater-status/cloud-startup coordination | Cloud callbacks, internal status subscriptions, direct methods, manager resume and early-boot installation remain |
| `bt_eliot`: `autoDownload=0` | Waits for download consent instead of scheduling automatic download | Explicit requests and already-staged packages remain |
| `bt_eliot`: `autoDownloadMinutesRange=0` | Falls back to 120 minutes | Zero does not disable the timer |
| Startup XML: `root/sw/dedrifu/enable=0` | Suppresses the daemon's own `dedrifu.sh` call; already zero in stock | Independent rcS startup and `fw_manager` ignore this setting |
| `fw_manager`: `UnpackFwToExtras` | Selects unpacking/storage behavior | No installation-enable semantics |
| Process `working_mode=0` | Classifies lifecycle behavior; still permits normal startup | Not a process-disable switch |
| Process `secure_mode` | Chooses ordinary versus unprivileged launch | Permission changes are not a clean update policy |

The daemon's Dedrifu parser treats exact `0` or an empty value as disabled; the
string `false` is not equivalent. No process-level XML `enable` field was found.
Removing the `fw_manager` process entry requires keeping the numbered `p0`, `p1`,
etc. entries contiguous, including renumbering subsequent entries.

Configuration precedence matters:

- The daemon parses `/var/tmp/stack_open.xml`, normally linked to the main
  `stack_open.xml`. Vendor startup can select `stack_open_reduced.xml` instead.
  Reduced stock omits both updater and cloud client; selecting it wholesale
  would violate the cloud-function requirement.
- An optional `/home/bticino/cfg/bt_daemon` INI can override/add process entries.
  It is absent in stock; a payload verifier must account for composition that
  introduces it.
- The persistent `.bt_eliot/bt_eliot` file restores association and firmware
  metadata, not overrides for `FwUpdate` or `autoDownload`. Local updater state
  starts at zero and is subsequently populated by status messages.

Evidence: `bt_eliot.c:81–132,199–216,616,6425–6575,5180–5213`; `bt_daemon.c:
2379–2383,3632–3641,4745–4828,4931–4969,5195–5240,5947–5970,6494–6522,6709–7116`;
`fw_manager.c:88–114,1913–1979`. Targeted ARM inspection confirmed the
`working_mode` predicate at `bt_daemon:0x1f97c–0x1f9d4`.

### Selected mechanism: coordinated startup suppression

`fw_manager` is a persistent service, not a one-shot boot task. The daemon's
configured process list governs initial launch, application-stack relaunch and
working-mode transitions. It also drives heartbeat supervision; merely killing
the process can trigger a board reboot when watchdog handling is enabled.
Removing the process entry avoids retaining that expectation. No independent
direct launcher was identified in the inspected stock files. Evidence:
`bt_daemon.c:575–635,2017–2059,2732–2752,4745–4788,4881–4892,4930–4969`.

The accepted image policy is to:

1. Omit `fw_manager` from normal application startup, preserving other processes
   and valid numbering; verify all selectable XML/optional INI inputs.
2. Set `FwUpdate=0` so cloud startup does not wait for that absent manager.
3. Disable the independent rcS Dedrifu invocation.
4. Keep and verify daemon `dedrifu/enable=0` in both startup XML variants.

Disabling the rcS invocation here means removing its startup link, with the script
otherwise retained. Making the whole script inert was considered but not
selected. Commenting out only its installer command would still leave the
preceding `DEDRIFU_RUNNING` deletion active, contrary to leaving staged update
data alone.

This retains the installer binary, cloud client, USB update handlers and staged
data, while suppressing the inspected updater startup routes and resume loop.
The complete installed-file caller inventory and additional WHO130 trace found
no further functioning stock OTA installer route contradicting this approach.

**Rationale:** prefer this coordinated startup policy over deleting the installer
alone. Deletion would block the discovered
execution paths, but can leave resume retries and cloud-startup coupling;
an executable error stub introduces its own stuck-state problem. No single
configuration switch supplies the full policy.

This design is implemented but not hardware-validated. Vendor app notifications,
remote answering, commissioning/reconnection and explicit USB flashing require
targeted hardware validation. The update-specific topics registered by `fw_manager` support
separating that process from ordinary cloud operation, but do not alone prove
functional independence. Stock recovery remains outside the agreed guarantee.

### Implementation checks

The payload uses existing preparation, debugfs application and mandatory final
readback-verification hooks. All changes stay in the private main-filesystem copy;
the flasher and preserved recovery/kernel package profile remain independent.

The implementation/validation contract is:

- Guard the researched stock inputs; preserve the remaining process definitions,
  cloud settings and installer file contents while enforcing the four policy controls.
- Reject conflicting final startup inputs, including later payload changes that
  reintroduce the manager, either script-launch path, or cloud-startup dependency.
- Verify standalone `no-ota` and composition with SSH/MQTT, including final
  reopened-image checks and malformed/conflicting-input failures.
- Exercise absent and retained update-package/state scenarios in simulation,
  including boot, application-stack relaunch and working-mode changes. Establish
  that the updater is neither launched nor included in heartbeat supervision.
- Validate cloud/app notifications, remote answering, household functions,
  commissioning/reconnection and explicit USB flashing on hardware only as a
  separately authorized step. Never trigger a real vendor write as a blocking test.
- Document payload selection, rebuild-without-payload re-enablement, retained
  packages, and the normal-firmware-only protection boundary. Keep current usage
  and acceptance claims bounded by the observed offline/hardware evidence.

The implemented verifier pins the two edited outputs and unchanged reduced XML,
requires the optional daemon INI to remain absent, and checks the researched
launcher/installer/cloud/USB files. It rejects restored or renamed direct updater
links in the SysV runlevels. These are composition checks for trusted payloads,
not a sandbox or proof against arbitrary new startup code.

Real-stock standalone and combined FWZ builds, independent XML/INI semantics,
whole-namespace comparison, retained staged-state fixtures and conflicting-input
checks passed offline. The lifecycle check is a finite model of the researched
process-list traversal, not execution of the target OS or a cloud/app test.
See the [dated validation record](VALIDATION-HISTORY.md#2026-11-05-no-ota-implementation-and-offline-validation).

### Read-only installed-device snapshot — 2026-11-05

Public-key SSH succeeded. The running environment reported normal firmware
(`RUNNING_FW_COPY=1`), with both `bt_eliot` and `fw_manager` present. Their binaries,
`dedrifupdater`, its library and the early-boot installer script matched the
stock hashes inspected offline. The OTA configuration remains `FwUpdate=1`,
`autoDownload=1`, `autoDownloadMinutesRange=120`, `UnpackFwToExtras=0`.

Both known persistent `UPGRADE.fwz` paths and the `update_flags` directory were
absent at observation time. `/proc/mounts` confirmed `/dev/mmcblk2p7` mounted at
`/home/bticino/cfg/extra`. The runtime startup XML selects both vendor services
with `working_mode=1`. These reads establish the current snapshot, not prevention
or absence of future downloads. No installer invocation, configuration change,
service restart, firmware write or reboot was performed.

A follow-up read confirmed `root/sw/dedrifu/enable=0` in both stock image XML
variants, both installed variants and the active `/var/tmp/stack_open.xml`.
The runtime link points to `/home/bticino/cfg/stack_open.xml`; the optional
`/home/bticino/cfg/bt_daemon` INI is absent on the device. This switch is baked into
the main filesystem image, not supplied by the persistent `cfg/extra` partition.
