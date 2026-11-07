# Build firmware

Build a new C100X Door Entry **1.5.8** image with optional SSH and MQTT.
The original firmware is preserved; building does not contact or
change the intercom.
Install the tool using the [README](../README.md#installation) first.

**Builds block manufacturer updates in both main and recovery by default**,
including builds with no optional features. `--allow-vendor-updates` opts out.
Selecting SSH provisions both filesystems for owner-controlled wireless flashing.

## Prepare and choose features

Open Terminal and create a working folder outside the installation. Allow at
least **4 GiB** of free disk space. Run builds without `sudo`:

```sh
mkdir -p ~/C100X-firmware
cd ~/C100X-firmware
/Applications/C100X/c100x builder-doctor
```

The doctor lists the required tools and reports any missing ones. Use this build
template, replacing `FEATURE_OPTIONS` with the options from the sections below:

```sh
/Applications/C100X/c100x build-fw --stock c100x-1.5.8 \
  FEATURE_OPTIONS --output custom.fwz --report custom.build.json
```

**Choose features independently or combine their options in the same command.**
The CLI calls these features *payloads*.

Stock firmware is downloaded and verified automatically. For an offline build,
replace `--stock c100x-1.5.8` with the path to your original stock `.fwz` file;
already-modified inputs are rejected. Adjust the executable path throughout if
you installed somewhere other than `/Applications/C100X`.

## SSH access

Choose how to log in to the intercom's administrative account, **`root2`**:

| Authentication | Build options |
| --- | --- |
| Password | `--payload ssh --ssh-password` |
| Public key | `--payload ssh --ssh-public-key ~/.ssh/c100x_ecdsa.pub` |

The password option prompts for a **new intercom password**, not your Mac password.
For both methods, add `--ssh-password` to the public-key options. For unattended
builds, use `--ssh-password-file /path/to/password-file` instead (permissions `0600`).

Use an existing ECDSA P-256 public key, or create a dedicated one (choose another
filename if this already exists):

```sh
ssh-keygen -t ecdsa -b 256 -f ~/.ssh/c100x_ecdsa
```

Supply the `.pub` file to the builder; keep the matching private key on your Mac.
Ed25519 is unsupported by the stock SSH server. Legacy RSA login keys require
`-o PubkeyAcceptedAlgorithms=+ssh-rsa` when connecting.

Each SSH build creates one new host identity shared by main and recovery
and persistent across reboots. Both images receive the same owner login settings;
recovery retains its own vendor accounts. MQTT/custom payloads remain main-only.
Key-only builds disable password login. The independent `c100x-ssh` service
enables SSH regardless of the vendor's SSH-enable setting, preserving device
configuration. See the [SSH reference](BUILDER-REFERENCE.md#ssh-implementation)
for service management.

<a id="optional-mqtt-bridge"></a>

## MQTT bridge

Build options: `--payload mqtt --inputs build.private.json`

You need an existing MQTT broker reachable from the intercom, its numeric IPv4
address, and a username/password. This version supports **plaintext MQTT only**,
not TLS. It does not install a broker or Home Assistant configuration/discovery.

In the working folder, run `nano build.private.json`, paste the following, and
replace the example address and credentials. Save with Ctrl-O, Enter; exit with
Ctrl-X. The file must be plain-text JSON:

```json
{
  "mqtt": {
    "transport": "plain",
    "host": "192.0.2.10",
    "port": 1883,
    "username": "REPLACE_WITH_BROKER_USERNAME",
    "password": "REPLACE_WITH_BROKER_PASSWORD",
    "prefix": "Bticino"
  }
}
```

Restrict access before building:

```sh
chmod 600 build.private.json
```

Use a unique prefix per intercom on a shared broker; it also determines the client
ID. Port and prefix default to `1883` and `Bticino`. Changing broker settings later
requires rebuilding and flashing. Keep this file and generated firmware private.

With the example prefix, the broker must allow these topics:

| Topic | Direction and content |
| --- | --- |
| `Bticino/tx` | Intercom publishes OpenWebNet event frames; QoS 0, non-retained |
| `Bticino/rx` | Intercom subscribes to raw numeric commands ending in `##`; one per message, at most 4096 bytes |
| `Bticino/start_date` | Intercom publishes retained worker-start time from its local clock |
| `Bticino/LastWillT` | Intercom publishes retained `online` / `offline`; QoS 1 |

Publish commands **non-retained**. Detected connection failures discard queued
work; uncertain commands are not retried. Undetected stalls can delay in-flight
data. Physical-button reporting and administrative JSON/shell commands are not
provided. See [limits and diagnostics](BUILDER-REFERENCE.md#mqtt-limits-and-diagnostics)
for compatibility details.

## OTA prevention

Prevention is a default builder policy, not a manually selected payload. No
inputs, SSH or MQTT are required. A prevention-only build is:

```sh
/Applications/C100X/c100x build-fw --stock c100x-1.5.8 \
  --output no-ota.fwz --report no-ota.build.json
```

To permit manufacturer updates, add **`--allow-vendor-updates`**. With no optional
payloads this produces a stock-preserving build. The report includes
`vendor_updates: blocked|allowed` and records checks for both filesystems.

The policy removes `fw_manager` from the vendor process list, sets the cloud
client's `FwUpdate=0`, and removes the early-boot installer link. It verifies the
daemon's separate installer setting stays disabled. Installer files remain intact.

Protection applies in **both prepared environments**, including app-approved and
previously staged updates. Existing unprotected firmware remains unprotected until
replacement; installation checks do not exclude a later competing vendor update.
Staged packages and persistent update metadata are
left untouched; update prompts/downloads may remain. Re-enable OTA by rebuilding
from stock with `--allow-vendor-updates` and explicitly flashing; retained packages may
then become actionable. There is no runtime toggle.

An image with this policy completed a full SSH flash, recovery integrity checks
and final SSH verification on hardware; the user confirmed post-flash household
tests passed. Live prevention behavior and USB flashing with customized recovery
remain follow-up checks. See [OTA evidence](OTA.md) and [validation status](ACCEPTANCE.md).

## Build result and next step

For example, to combine password SSH access and the MQTT settings prepared above:

```sh
/Applications/C100X/c100x build-fw --stock c100x-1.5.8 \
  --payload ssh --ssh-password --payload mqtt --inputs build.private.json \
  --output custom.fwz --report custom.build.json
```

On success, `custom.fwz` is the checked firmware image and `custom.build.json` is
a redacted report of offline checks. Check the installed features after flashing.

Existing outputs are never overwritten: choose fresh output/report names for
another build. Keep the FWZ private; it contains credentials and, with SSH, a
host private key. To install it, continue to [Flash firmware](FLASHING.md).

If building fails, check the reported input/tool error, JSON syntax, permissions
and free space. A filesystem/profile failure is not repaired automatically; use
the supported original stock image.

<a id="authoring-trusted-payloads"></a>
<a id="create-your-own-firmware-customization"></a>

For custom files/services, see the
[advanced builder reference](BUILDER-REFERENCE.md#create-your-own-firmware-customization).
