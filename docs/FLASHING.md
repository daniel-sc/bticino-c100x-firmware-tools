# Flash firmware

Install using the [README](../README.md#installation), then use a compatible
`.fwz` image, such as the one from [Build firmware](BUILDER.md). Stock devices
do not need SSH. See [validation and known limits](ACCEPTANCE.md) for tested
scope and follow-up coverage.

## Compatibility

Only **C100X Door Entry 1.5.8** is supported. The tool checks hardware family
`02.*.*` (three numeric fields, first field `2`), device type `200`, object model
`1.0.99` and initial status `4*0`. The hardware rule follows the vendor updater;
it applies to preflight, reboot verification and recovery entry. Package checks
require the stock manifest/kernel and supported main/recovery filesystem profiles.
Passing these checks does not prove bootability.

**Supported versus tested:** hardware `02*06*0` has passed the recorded flash and
household checks. A community report adds successful stock-to-modified flashing
and functional checks on `02*07*0`. These results carry forward for unchanged
behavior; other family-02 revisions have no recorded hardware flash acceptance yet. See
[protocol evidence](PROTOCOL.md#hardware-family-compatibility-2026-11-07) and
[validation](ACCEPTANCE.md).

## 1. Inspect and run preflight

Open Terminal in the folder containing your image. These examples use the
builder guide's working folder and filename; adjust them if needed:

```sh
cd ~/C100X-firmware
/Applications/C100X/c100x inspect-fw custom.fwz
```

Inspection prints the validated image's metadata and checksums without contacting
the device. Connect the powered intercom with a USB data cable, then run preflight:

```sh
sudo /Applications/C100X/c100x plan custom.fwz
```

`sudo` asks for your Mac password. The tool manages USB networking automatically
and checks device identity/status without writing firmware. Success is confirmed
by a **Preflight passed** message; the JSON includes `"device_writes": false`
and the proposed sequence. If you want the
[optional existing-SSH check](#optional-recovery-verification-existing-ssh), add
its options to both preflight and flashing.

## 2. Flash

Keep the Mac awake, USB connected and device power stable throughout the update.
This command explicitly writes firmware and reboots the intercom:

```sh
sudo /Applications/C100X/c100x flash custom.fwz
```

Progress reports each stage; networking is maintained across the three reboot
transitions. On error, keep the device powered and record the stage and message.
There is no automatic retry, resume, rollback or cleanup reboot.

The intercom may also expose a `C100X` storage volume. Do not copy firmware onto
it; flashing uses USB networking. Before planned reboots, the flasher attempts an
ordinary unmount; failure warns and permits flashing to continue. macOS may still
show “disk not ejected properly”; the latest discovery fix awaits hardware
validation. Eject any mounted C100X volume before disconnecting after completion.

## 3. Check the result

Protocol completion is not functional acceptance. Check calls, two-way audio,
video and door release, plus whichever features you selected:

- **SSH:** find the intercom's LAN address in your router and connect from the
  same network with `ssh root2@INTERCOM_IP` (replace `INTERCOM_IP`). For the dedicated
  key in the builder guide, insert `-i ~/.ssh/c100x_ecdsa` before `root2@INTERCOM_IP`.
  Test each selected login
  method and confirm host identity persists across a subsequent normal reboot.
  A newly built image has a new host identity; investigate unexpected key changes.
- **MQTT:** in your broker's MQTT client, subscribe to your prefix's `/LastWillT`
  and `/tx` topics. Expect `online` when the bridge is ready and event frames
  during a doorbell call. A retained `online` message alone does not prove event
  delivery or household behavior. The [topic table](BUILDER.md#mqtt-bridge)
  describes the interface.

## Optional recovery verification (existing SSH)

If the **currently installed firmware** already has SSH enabled, add these options
to `plan` and `flash`: `--verify-recovery-ssh --ssh-user root2 --ssh-password`.
Here the password is the **existing intercom password**, not the new password
chosen during a build. SSH in the incoming image cannot provide this access yet.

Each command prompts once; the password stays in memory. Verification uses the
managed USB connection, not LAN SSH.

`plan` checks prerequisites without firmware writes. During `flash`, the extra
check runs **after writing recovery and rebooting normally, before clearing the
main kernel**. It compares the recovery filesystem and kernel/DTB contents with
the selected package and checks the copied filesystems offline. Failure or uncertainty stops
the update. This verifies integrity, not recovery bootability or household
functions. The gate has passed on hardware over USB and within a completed SSH
flash. See [validation](ACCEPTANCE.md).

- Allow several extra minutes and **512 MiB** of free space. SSH readiness is
  limited to two minutes; readback/analysis to fifteen minutes. Failed acquisitions
  are not retried.
- For keys, omit `--ssh-password`; optionally supply `--ssh-key /path/to/key`.
  Encrypted keys must already be unlocked in your agent. If sudo removes the agent
  socket, use `sudo --preserve-env=SSH_AUTH_SOCK ...`. ECDSA P-256 is recommended;
  legacy RSA host/login signatures are enabled only for this connection. Ed25519 is not
  supported by stock Dropbear.
- SSH host keys may change on older installations. First-seen/changed fingerprints
  produce warnings and are recorded, without changing your `known_hosts` file.
  This policy does not prove cryptographic identity continuity.
- A private `c100x-verification-<timestamp>-.../report.json` is saved in the working
  directory, owned by your ordinary user. Raw copies are removed on normal exit.
  After an abrupt kill/power loss, remove any leftover `raw/` directory explicitly;
  it can contain private firmware. Reports never authorize resuming a flash.

Use `sudo` from your ordinary account and an administrative device account (UID
0). This mode requires managed USB, so it cannot be combined with `--external-usb`.
Release bundles include the required filesystem tools.

<a id="wireless-updates-source-builds"></a>
<a id="wireless-updates-prerelease"></a>

## Wireless updates over SSH

**A complete owner-controlled OTA flash over SSH has passed on hardware**, including
recovery networking, installed recovery readback and final destination SSH
verification. Use a [dual-image SSH package](BUILDER.md#ssh-access); see
[validation](ACCEPTANCE.md) for the tested conditions.

The existing main firmware must already provide administrative SSH and the supported
vendor update components. Its SSH service need not be our `c100x-ssh` implementation.
After the first planned normal reboot, the same trusted host key and credentials
must reconnect before main-kernel invalidation. If SSH disappears or regenerates
its key, the run stops with main's kernel still intact. Recovery SSH need not
pre-exist: the normal system installs it before recovery access is needed.

The workflow assumes a trusted home network and owner-selected package. Admission
accepts equivalent executable permissions (for example `0750` or `0700`) on SSH
daemon/init files. Destination startup contents and credentials are still checked
offline because those environments cannot authenticate until installed.

Run without sudo on the same LAN. Example read-only preflight using your login key:

```sh
/Applications/C100X/c100x plan custom.fwz --transport ssh \
  --ssh-user root2 --ssh-key ~/.ssh/c100x_ecdsa
```

After preflight passes, explicitly write the firmware:

```sh
/Applications/C100X/c100x flash custom.fwz --transport ssh \
  --ssh-user root2 --ssh-key ~/.ssh/c100x_ecdsa
```

Recovery verification is automatic for SSH transport; `--verify-recovery-ssh`
may also be supplied explicitly. The recorded full flash took about 11 minutes.
The default target is `Bticino-Classe100X.local`; `--host NAME_OR_IP` overrides it.
Hostnames are resolved again on reconnect. A fixed IP/DHCP reservation is a
fallback when mDNS is unavailable. SSH-config aliases, proxies and jump hosts
are not interpreted. If a hostname resolves to multiple IPv4 addresses, supply
an unambiguous target.

- Use `--ssh-password` instead of a key to prompt once for the existing password;
  omit both for an unlocked SSH agent. Destination credentials default to the
  existing settings; `--destination-ssh-user`, `--destination-ssh-key` or
  `--destination-ssh-password` override them. Destination access is checked offline
  before any write. Keep the matching `.pub` sidecar beside an encrypted private
  key and unlock it in the agent. Login passwords are not persisted.
- Strict host-key checks apply. Existing trusted entries can seed enrollment;
  otherwise confirm the first fingerprint interactively. A trusted hostname
  identity takes precedence over entries for its resolved IP; address trust is
  used only when the hostname has no saved identity. Tool-owned trust lives
  under `~/Library/Application Support/C100X/trust/`. Your ordinary `known_hosts`
  is not changed. The expected package key is used in new recovery/main and
  remembered after final verification. Sources with regenerated keys require
  the explicit option described below.
- Recovery readback is mandatory, using the same gate as optional USB verification.
  Allow roughly 2 GiB free for image inspection plus private recovery evidence.
  Source setups need e2fsprogs, Dropbear keygen and OpenSSL; the release tool set
  already includes them. Ordinary USB flashing retains its smaller dependencies.
- Keep the computer connected throughout. The tool prevents idle sleep on macOS
  and tries `systemd-inhibit` on Linux, warning if unavailable. Lid closure,
  forced sleep, network interruption and power loss remain separate.
- Known staged vendor packages, nonempty update metadata or active installers
  stop preflight. These snapshots cannot prevent a subsequent competing installer
  in unprotected firmware. Neither pre-installed prevention nor temporary
  in-place configuration changes are required.
- Final normal reboot, vendor identity/state and authenticated destination SSH
  are required for completion. Perform household checks separately. No automatic
  retry/resume, transport fallback or cleanup reboot occurs. For manual
  continuation, see [below](#resuming-an-interrupted-wireless-update).

## Updating from an earlier firmware version

A wireless update starts only when the running system matches a **source profile**: the four update executables in `/home/bticino/bin` (`bt_device`, `bt_daemon`, `fw_manager` and `dedrifupdater`) must have exactly the SHA-256 values recorded for a supported firmware version. When no profile matches, the preflight stops before any write and names the closest profile and the executables that differ.

| Source firmware | Evidence |
|---|---|
| 1.5.8 | The stock 1.5.8 image this project was researched against. |
| 1.5.7 | Read from one intercom (`02*06*0`) running 1.5.7. Three of the four executables equal those of 1.5.8. `fw_manager` has not yet been compared with an official 1.5.7 image. |

The source version is accepted only while the source MAIN system is still the one running: before the first write, after the reboot that follows the recovery transfer, and after the recovery readback. Once the main kernel has been cleared, the recovery boot and the final MAIN system must report the target firmware. Device type, hardware family, object model and update state stay strict in every phase. To add a version, see [SOURCE-PROFILES.md](SOURCE-PROFILES.md).

### Source firmware that regenerates its SSH host key

Some source firmware generates a new SSH host key at every normal boot. On the 1.5.7 system above, `/var/lib` is a RAM disk and Dropbear takes its key from there. The update reboots the source system once, after the recovery was written, so a strict identity check stops it right there with `Unexpected SSH identity during phase transition`.

A profile declares this behavior with `HostKeyPolicy.EPHEMERAL_ON_NORMAL_REBOOT`. For such a source, `plan` and `flash` stop before any write unless `--accept-regenerated-host-key` is given. With it, the key presented after the first normal reboot is accepted once, without a prompt, and is never saved as trusted. It is accepted only when every matching profile declares the policy, only in that reboot, and only after the previous key stopped answering. The recovery boot and the final MAIN system must still present the key carried by the firmware image.

**The option accepts a key that cannot be verified**, because a key regenerated at every boot cannot be compared with anything. With `--ssh-password`, the existing password is offered to whatever answers after that reboot. Prefer `--ssh-key`, which hands over no secret, and use the option only on a network you trust.

```bash
c100x flash --transport ssh --host 192.168.1.20 \
  --ssh-user root2 --ssh-key ~/.ssh/c100x_ecdsa \
  --accept-regenerated-host-key custom.fwz
```

## Resuming an interrupted wireless update

If `flash` stops after writing recovery, use the commands below to continue.
Choose the section for the system the intercom is now running.

These commands were written for one intercom and have not yet been through the hardware acceptance recorded in [ACCEPTANCE.md](ACCEPTANCE.md).

### Stopped after the recovery was written

Use this when the last stage was `recovery: rebooting`, `recovery: verifying installed contents over SSH` or `recovery: reconnecting after SSH verification`, and the intercom runs its normal system again. The recovery is installed and the main kernel is intact.

- `plan-resume-recovery` is read-only. It checks the running system against a source profile, reads the installed recovery back over SSH and proves it identical to the firmware image.
- `resume-recovery` repeats those checks. Only if they pass does it clear the main kernel, reboot into the recovery and install the main system. The recovery is never written again.

They take the options of `plan` and `flash` that apply to SSH (`--host`, the existing and destination logins, and `--accept-regenerated-host-key` for a source that needs it), without `--transport`.

```bash
c100x plan-resume-recovery --host 192.168.1.20 \
  --ssh-user root2 --ssh-key ~/.ssh/c100x_ecdsa \
  --accept-regenerated-host-key custom.fwz
```

If the readback fails, the main kernel has not been cleared and the intercom still runs its previous system.

### Stopped after the main kernel was cleared

Use this when the intercom is already running recovery (update state 1).

Run `plan-recovery` to check that the expected recovery system is running and
ready. Then run `recover` to write the main firmware and reboot into it.
The SSH flow verifies the installed system's SSH access before saving its identity.

Both take a single login, the one the firmware image installs in the recovery: `--ssh-user` with `--ssh-password` or `--ssh-key`. There are no `--destination-*` options. Without `--transport ssh` they keep using USB as before.

```bash
c100x plan-recovery --transport ssh --host 192.168.1.20 \
  --ssh-user root2 --ssh-key ~/.ssh/c100x_ecdsa custom.fwz
c100x recover --transport ssh --host 192.168.1.20 \
  --ssh-user root2 --ssh-key ~/.ssh/c100x_ecdsa custom.fwz
```

Keep the intercom powered throughout. These commands stop on errors; they never
retry automatically. [Recovery evidence](RECOVERY.md) documents the limits.

## Troubleshooting

- **Image rejected:** use a profile-compatible image; version 1.5.8 alone is not
  enough. Building requires original stock; flashing accepts compatible custom images.
- **USB preflight fails:** check device power and a data-capable cable. Keep the
  reported error; manual network setup should not be necessary.
- **SSH verification fails:** confirm that SSH already works on the installed
  firmware and that you supplied its current credentials. A failed integrity check
  needs investigation; it is not a reason to resume without verification.
- **Wireless connection/readiness failure:** use the current Mac tool and retain
  the failed stage and cause. It waits for the FTP greeting, refreshes the command
  session after uploads and polls SSH readiness across planned reboots. A failure
  at the first recovery FTP greeting precedes payload writes; failures at later
  stages need their own assessment.
- **Flash fails:** preserve power and the stage/error output. For an interrupted
  SSH update, use the continuation steps above. For other rescue situations,
  [recovery evidence](RECOVERY.md) documents the limits.

For implementation details, see [the protocol](PROTOCOL.md). Developers can use
the separate [source and USB-helper setup](SOURCE.md#usb-helper-setup).

## Finishing from an already running recovery environment

For USB recovery, run `plan-recovery` to check that the expected recovery system
is running and ready. Then run `recover` to write the main firmware and reboot into it.

`plan-recovery` validates the full image and requires matching C100X 1.5.8 identity,
status `1*0` and an idle worker without writing to the device. `recover` repeats
those checks, installs the main filesystem and kernel through the vendor updater,
and requests one reboot, requiring normal state `4*0` and reset uptime afterward.
It does not need SSH. The original recovery-verification report remains unchanged.

Adjust the image path to your working folder:

```sh
sudo /Applications/C100X/c100x plan-recovery ~/C100X-firmware/custom.fwz
```

After **Preflight passed**, explicitly start the main installation:

```sh
sudo /Applications/C100X/c100x recover ~/C100X-firmware/custom.fwz
```

All managed commands support macOS's native recovery ECM interface and
switch to/from the bundled USB helper when normal boot requires RNDIS. Interface
names are discovered, not hard-coded. Keep power/USB stable and the Mac awake. On
an error, preserve power and the output. After completion, perform the
[functional checks](#3-check-the-result). See [ADR-014](DECISIONS.md#adr-014-explicit-main-installation-from-running-recovery).

Over SSH, see [Resuming an interrupted wireless update](#resuming-an-interrupted-wireless-update).
