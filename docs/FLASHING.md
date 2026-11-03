# Flash firmware

Install using the [README](../README.md#installation), then use a compatible
`.fwz` image, such as the one from [Build firmware](BUILDER.md). Stock devices
do not need SSH. **Experimental:** full native flashing and generated-image
behavior still need [hardware validation](ACCEPTANCE.md).

## Compatibility

Only **C100X Door Entry 1.5.8** is supported. Preflight checks hardware `02*06*0`,
object model `1.0.99` and initial status `4*0`. Images must preserve the stock
manifest, recovery and kernel and match the main-filesystem profile. Passing
these checks does not prove bootability.

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
it; flashing uses USB networking. Eject that volume before disconnecting after
the operation has finished.

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
stock and checks the copied filesystems offline. Failure or uncertainty stops
the update. This verifies integrity, not recovery bootability or household
functions. USB/SSH hardware validation of this new feature remains pending.

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

## Troubleshooting

- **Image rejected:** use a profile-compatible image; version 1.5.8 alone is not
  enough. Building requires original stock; flashing accepts compatible custom images.
- **USB preflight fails:** check device power and a data-capable cable. Keep the
  reported error; manual network setup should not be necessary.
- **SSH verification fails:** confirm that SSH already works on the installed
  firmware and that you supplied its current credentials. A failed integrity check
  needs investigation; it is not a reason to resume without verification.
- **Flash fails:** preserve power and the stage/error output for investigation.
  Do not rerun an uncertain write. There is no validated general rescue procedure;
  [recovery evidence](RECOVERY.md) documents the limits.

For implementation details, see [the protocol](PROTOCOL.md). Developers can use
the separate [source and USB-helper setup](SOURCE.md#usb-helper-setup).
