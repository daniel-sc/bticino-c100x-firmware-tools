# C100X 1.5.8 image builder

The builder modifies a private copy of the pinned **Door Entry C100X 1.5.8**
stock package. It runs natively on macOS using ordinary files, without mounting
ext4 or contacting a device. Linux is a design target awaiting the same test
matrix; Windows currently means a future tested Linux/WSL workflow, not native
Windows support.

## Setup and commands

The downloadable macOS release includes all tools and its own Python interpreter.
Use `./c100x` in place of `mise exec -- python -m classe100x` in the commands below.
Run builds as your ordinary user; the builder and payload hooks refuse root.
The following dependency installation is only for running from source.

Use the project's mise-managed Python and 7zip. On macOS:

```sh
mise trust
mise install python 7zip
brew install e2fsprogs dropbear openssl
mise exec -- python -m classe100x builder-doctor
mise run test-builder
```

The SSH payload additionally uses `openssl passwd -6` for password builds.
`dropbearkey` generates an ECDSA P-256 **host** key, independently of the login
public key. Homebrew's e2fsprogs is keg-only; discovery checks PATH and the
standard Apple Silicon/Intel Homebrew locations. `--debugfs`, `--e2fsck` and
`--sevenzip` override executable paths. SSH inputs can override `dropbearkey`
and `openssl`. Nothing is silently installed by a CLI command.
Bundled tools are preferred over PATH; explicit overrides still take precedence.

The builder itself needs no compiler. Apple Silicon Homebrew bottles are prebuilt;
installing formulae from source requires Xcode Command Line Tools. The native USB
helper has separate compiler/SDK requirements in [FLASHING.md](FLASHING.md).

Fetch the pinned original ahead of time, or let `--stock` fetch on cache miss:

```sh
mise exec -- python -m classe100x fetch-fw
mise exec -- python -m classe100x build-fw --stock c100x-1.5.8 \
  --output .local/roundtrip.fwz --report .local/roundtrip.build.json
```

With no payloads the decompressed main filesystem must remain byte-identical.
The rebuilt archive is not byte-identical: compression, timestamps and encryption
randomness can differ. A fresh SSH host key also prevents identical SSH builds.

Build with the bundled SSH payload (explicit selection is required):

```sh
mise exec -- python -m classe100x build-fw --stock c100x-1.5.8 \
  --payload ssh --ssh-public-key ~/.ssh/id_ecdsa.pub \
  --output .local/custom.fwz --report .local/custom.build.json
```

Use your existing ECDSA P-256 public key. RSA public keys are accepted for legacy
compatibility, but stock Dropbear 2017.75 then requires the OpenSSH
`PubkeyAcceptedAlgorithms +ssh-rsa` exception for **user authentication**. The
new ECDSA host identity addresses the separate `HostKeyAlgorithms` exception.
Ed25519 login keys are not supported by this stock daemon. Vendor-build ECDSA
user authentication still requires hardware acceptance; installing/read-checking
a key offline does not demonstrate successful login.

For password-only or combined authentication, add `--ssh-password` to prompt in
a terminal, or `--ssh-password-file .local/ssh.password` (mode 0600). At least
one authentication method is required. Passwords are SHA-512-crypt hashed with
a fresh salt, matching the stock shadow-file algorithm. The plaintext is passed
to OpenSSL through private stdin, not argv. Key-only builds set Dropbear `-s`;
password builds enable daemon-wide password authentication while preserving
vendor accounts. Login account: `root2`, UID/GID 0, home `/home/root`.

The host key is newly generated for each build and installed at
`/etc/dropbear/classe100x_ecdsa_host_key`. The existing init script receives that
path through `DROPBEAR_RSAKEY` (despite the variable name, its `-r` option accepts
ECDSA). This avoids its volatile RSA-key generation path. Identity is intended
to remain stable across reboots; a new build intentionally has a different host
identity. The FWZ contains the host private key and possibly configuration
secrets: treat it as a private artifact, not as encrypted secret storage.

To build offline from a file, replace `--stock c100x-1.5.8` with the path to the
original stock FWZ. The builder rejects already-modified inputs. Inspect the
finished artifact using the same validation used by `plan`/`flash`:

```sh
mise exec -- python -m classe100x inspect-fw .local/custom.fwz
```

Building never invokes flashing. Use the separate [flashing guide](FLASHING.md),
including the real-device compatibility checks.
Neither a build report nor a successful offline inspection proves bootability.

## Optional MQTT bridge

Select `--payload mqtt` to install the bridge using stock Python 2.7 and
libmosquitto. SSH is independently selectable. Create a mode-0600 JSON file
outside source control, for example `.local/build.private.json`:

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

Replace the example address and credentials with your broker settings. V1 requires
explicit plaintext transport, a numeric IPv4 address and nonempty username/password.
Port and prefix default to `1883` and `Bticino`. Prefixes use ASCII letters, digits,
`_`, `-` and nonempty `/`-separated levels, at most 128 characters. Credentials
are UTF-8, at most 512 bytes each, without NUL/newlines. Unknown fields fail.

```sh
chmod 600 .local/build.private.json
mise exec -- python -m classe100x build-fw --stock c100x-1.5.8 \
  --payload mqtt --inputs .local/build.private.json \
  --output .local/mqtt.fwz --report .local/mqtt.build.json
```

Add `--payload ssh --ssh-password` or `--ssh-public-key ...` for administrative
access. Broker configuration is embedded privately in the image; changing it means
rebuilding and flashing. Hex-encoded configuration values are **not encryption**.
Keep the inputs and generated FWZ private. TLS and runtime provisioning are deferred.
Use a unique prefix per device on a shared broker: it also determines the MQTT
client ID. Broker ACLs should permit this client to publish its `tx`, `start_date`
and `LastWillT` topics and subscribe to its `rx` topic.

| Topic suffix | Behavior |
| --- | --- |
| `/tx` | Public-monitor OpenWebNet frames, QoS 0, non-retained |
| `/rx` | One raw numeric `##`-terminated command per message, at most 4096 bytes |
| `/start_date` | Retained worker-start date/time from the device's local clock |
| `/LastWillT` | Retained `online` / `offline`, QoS 1 |

Existing household bell payload `*8*1#1#4#21*10##` and door press/release
`*8*19*20##`, `*8*20*20##` are preserved. Callers send the two commands with their
own timing. This does not install HA discovery/configuration, administrative
JSON/file/shell operations or physical-button reporting. Public-monitor output
is not identical to the legacy tcpdump stream; only the documented household
coverage has been observed on the existing device.

`online` means MQTT, the subscription and the loopback public monitor are ready.
Detected failures discard pending work and reconnect; commands are serialized
through short-lived port-30006 connections and never retried on uncertain delivery.
Clean sessions and retained-command rejection prevent retained replay. Publish
commands non-retained; MQTT 3.1.1 does not identify a live retained publish as
retained for existing subscribers. There is no persistent event/command queue.
Undetected stalls may delay already-in-flight data. Pending commands expire after
two seconds, with a 16-command queue and two-second exchange deadline. Outgoing
publications are limited to 64, with a three-second stall deadline. MQTT keepalive
is 15 seconds; reconnect delays are 1/2/4/8/16/30 seconds, capped at 30.

The runlevel-5 service starts one Python supervisor and one worker. It only owns
bridge resources. Diagnostics (including raw frames, with credentials redacted)
rotate across two files totaling at most 1 MiB under
`/var/volatile/tmp/c100x-mqtt/`; reboot removes them. If SSH was selected separately,
`/etc/init.d/c100x-mqtt status` checks the supervisor, not broker readiness;
`stop`, `start` and `restart` manage this service. Readiness is reported via MQTT
and private logs. Fresh-image boot, target ABI and household behavior still need
hardware acceptance; offline build verification establishes installed bytes only.

## Downloads and package policy

The single catalog entry uses
`https://assets.legrand.com/pim/AUTRE/C100X_010508.fwz`, length **106240356**, and
stock SHA-256 `bca0dd7e407c2406d6f8c696f0a9e50bc1e795c8e4700c89e83f09ff96c3efb2`.
The bytes downloaded on 2026-10-28 matched that pin. Downloads have size and time
bounds and are cached only after verification; cached files are rehashed before
reuse. A corrupt cache fails rather than being silently replaced. There is no
latest-version discovery, alternate-model substitution or hash override.

Both the builder and flasher require exactly four classic, ZipCrypto-encrypted
DEFLATE ZIP entries. Flags 1 (stock/7zip) and 3 (researched legacy custom image)
are accepted; AES, Zip64 and streaming descriptors are rejected. Local and
central headers must agree. ZIP timestamps/attributes may differ, and bounded
non-Zip64/non-AES extra fields are allowed. The decoded `fwz.xml`, recovery gzip
and kernel ZIP are SHA-256 pinned to stock. Only the main filesystem may vary.
Its expanded size, ext geometry and feature flags are checked without e2fsprogs
by the flasher. Builder checks additionally preserve filesystem identity/journal
layout fields and run `e2fsck -f -n` before and after modification.
The extraction-version low byte is 20; the original vendor package uses upper
byte 3, while the selected legacy custom and 7zip output use 0. Both observed
variants are allowed, with matching local/central fields.

No `.sig` handling or manifest rewrites are implemented: the supported stock
package has neither a signature entry nor a need for a manifest edit. Six absent
manifest extras remain intentionally absent, as in the researched vendor flow.

7zip can choose STORE for incompressible entries despite requesting DEFLATE.
The builder fails verification for that packaging variant rather than weakening
the profile. The real stock and SSH round trips passed with mise's 7zip 26.05.
Windows/MyHOME import compatibility is a target, still awaiting an actual import
test; matching ZIP properties is not that acceptance test.

<a id="authoring-trusted-payloads"></a>

## Create your own firmware customization

**This section is for advanced users adding their own files or services.**
For the included SSH and MQTT features, use the setup instructions above; you do
not need to write any of the files described here.

A **payload** is a folder containing files to add to the firmware and instructions
for the builder. The included `ssh` and `mqtt` folders are examples. You can make
your own to add a configuration file, install a device-compatible program, or
arrange for a service to start when the intercom boots.

The builder copies the original firmware into a private working folder, applies
your instructions to that copy, checks the result, and saves a new `.fwz` file.
Installing that image on the intercom is a separate flashing step.

**Why must you trust the source?** Build instructions run on your Mac with the
same permissions as you. They can access your host files, not just the firmware
copy. A private working folder does not isolate those instructions from your Mac.

### Example: add a text file to the firmware

This small example adds `/etc/c100x-note.txt` to the new image. It demonstrates
how to include a file and check that it was installed correctly.

Create a folder called `my-note` containing these four files:

```text
my-note/
  payload.json       # identifies this customization
  note.txt           # the file to include in the firmware
  apply.debugfs      # instructions for editing the firmware filesystem
  verify.py          # checks the installed file
```

**1. `payload.json` — name and supported firmware:**

```json
{"id":"my-note","version":"1","profile":"c100x-1.5.8","verification_required":true}
```

**2. `note.txt` — the file's contents:**

```text
Built with my custom firmware settings.
```

**3. `apply.debugfs` — copy the file and set its owner and permissions:**

```text
write note.txt /etc/c100x-note.txt
set_inode_field /etc/c100x-note.txt uid 0
set_inode_field /etc/c100x-note.txt gid 0
set_inode_field /etc/c100x-note.txt mode 0100644
```

`debugfs` is the tool the builder uses to edit the Linux filesystem inside the
firmware image. These are its commands, not shell commands. The first path is
relative to your payload folder; `/etc/c100x-note.txt` is inside the image.
The remaining lines make the file root-owned and readable by everyone, with only
root allowed to change it. `0100644` includes the regular-file type and permissions.

**4. `verify.py` — read the file back from the image and check it:**

```python
from classe100x.payload import Context

c = Context()
c.image.require_file(
    "/etc/c100x-note.txt",
    (c.directory / "note.txt").read_bytes(),
    mode=0o644,
)
```

This Python script runs on your Mac during the build. It checks the file's exact
contents, root ownership and permissions. If a check fails, the build fails.

From the folder containing `my-note`, run:

```sh
/Applications/C100X/c100x build-fw --stock c100x-1.5.8 \
  --payload ./my-note --output custom-note.fwz --report custom-note.build.json
```

For a source checkout, replace `/Applications/C100X/c100x` with
`mise exec -- python -m classe100x`. You can combine this with included features;
for example, add `--payload ssh --ssh-password` to the same build command.

### File and script reference

For more involved customizations, the full folder structure is:

```text
my-payload/
  payload.json        # required name, version and supported firmware
  prepare.py          # optional Python script to check inputs and prepare files
  apply.debugfs       # required instructions for editing the image
  verify.py           # Python script to check the result; recommended
  files/              # optional folder for files to include in the image
```

```json
{"id":"my-payload","version":"1","profile":"c100x-1.5.8"}
```

Set `"verification_required": true` to require `verify.py`. IDs are unique within
a build. Repeating `--payload` defines execution order; there is no dependency
solver, implicit SSH installation, command substitution or conflict inference.

`prepare.py` and `verify.py` are also called **hooks**: Python scripts the builder
runs before editing the image and when checking the result. They run on your Mac.
Programs copied into the firmware must be compatible with the intercom's Linux/ARM
environment; the builder does not run those programs on your Mac.

The engine snapshots payload files into individual private directories and uses
that directory as each hook/command file's working directory. Source symlinks
are rejected; image symlinks are created with `debugfs`. `generated/` is reserved
for prepared files and `context.json` for the engine. Hooks use the same Python
interpreter as the CLI and receive the private `context.json` path as their sole
argument. It contains image path,
workspace path, tool paths, input base and the selected payload's input object.
`from classe100x.payload import Context` supplies small convenience methods.
Relative input-file paths resolve relative to the inputs JSON file (or the CLI
working directory without a JSON file).
The release carries CPython's standard library, so existing hook scripts and
imports from `classe100x.payload` continue to work. No pip environment or automatic
third-party package installation is provided. Interpreter startup is isolated
from user site packages and `PYTHONPATH`. Optional Tk GUI and GNU dbm extensions
are not bundled; SQLite, ctypes, TLS and all standard compression codecs are.

`--inputs .local/build.private.json` requires private permissions (mode 0600) and
accepts an object keyed by payload ID:

```json
{
  "ssh": {"public_key": "/absolute/path/login.pub"},
  "binary-service": {
    "binary": "/absolute/path/device-program",
    "binary_sha256": "SHA256_OF_SUPPLIED_BINARY",
    "configuration": "/absolute/path/private.conf",
    "service": "/absolute/path/init-script"
  }
}
```

The `binary-service` example packages a supplied ARM ELF32 binary, prepared
configuration and `/bin/sh` init script under `/usr/bin/image-service`,
`/etc/image-service.conf`, `/etc/init.d/image-service`, and a runlevel-5 symlink.
The supplied service script must use those paths. This demonstrates the
binary/config/service pattern; it is not a maintained MQTT integration or proof
of the binary's ABI/runtime compatibility. No target programs execute on the host.

The builder does not determine every change a customization can make or detect
every possible interaction between installed services.

The backend checks process status and rejects stderr other than the recognized
debugfs version banner. A failing mutation can return 0 and the rest of its batch
can run; such a batch is rejected before publication. Stdout/stderr are bounded
and withheld from normal logs because commands/output can contain secrets.
Hooks have bounded runtime/output and their process group is terminated on
timeout/cancellation. Hook failure reports identify the payload and phase.
Authors can raise `FirmwareError` with a short, explicitly non-secret user-facing
message; only that deliberate error message is forwarded, not a traceback or
arbitrary process output. Never include credentials in those messages.

Verification reads actual bytes and metadata, runs after each payload, after all
payloads, and on the reopened output image. Bundled SSH checks pin expected stock
inputs, preserve vendor accounts, check critical startup files, and verify the
result's contents/owners/modes/links. Its replacements require ordinary
single-link files without xattrs/ACLs. Replacement intentionally recreates inodes
and timestamps; it does not promise metadata-preserving general replacement.
The shadow file becomes 0600, and `/etc/dropbear` becomes root-owned 0700.

## Failure, reports and tests

Originals and existing outputs are never overwritten; aliases and existing
symlinks are rejected. The destination directory must exist. Allow at least
3.5 GiB free workspace space. There is no automatic filesystem repair, resize,
resume or device cleanup. Unexplained baseline filesystem errors stop the build.

Only a fully reopened/verified image is published, mode 0600, using a same-volume
no-clobber operation. Reports are optional, redacted and tied to the final FWZ
hash. Image publication precedes report publication; if the latter fails, the
valid image remains and the CLI reports that distinction. Reports contain no
credential values, per-secret hashes or user input paths.

Handled cancellation (including SIGTERM/SIGHUP) removes unpublished workspaces.
An uncatchable termination can leave a private `.classe100x-build-*` directory;
those directories are Git-ignored. There is no promise of secure erasure on SSDs.

`mise run test` runs the original offline suite plus builder/download tests.
Integration tests use synthetic filesystems and skip when tools are absent.
`mise run test-builder` requires the builder tools and fails if they are missing.
The SSH-mode fixture test additionally requires OpenSSH keygen, Dropbear keygen
and OpenSSL. Proprietary images are used only in explicitly authorized local
validation; the dated results and pending hardware work are in ACCEPTANCE.md.

Native MQTT tests use ephemeral loopback fixture servers and a host build of
libmosquitto 1.4.14. Prepare that test-only dependency with
`mise exec -- python tests/build_mqtt_library.py`, then run the suite with
`CLASSE100X_MQTT_LIBRARY="$PWD/.local/mqtt-native/mosquitto-1.4.14/lib/libmosquitto.so.1" mise run test`.
CI requires these native tests; without the environment variable they skip locally.
`tests/test_mqtt_runtime.py` also runs under Python 2.7 for compatibility checks.
