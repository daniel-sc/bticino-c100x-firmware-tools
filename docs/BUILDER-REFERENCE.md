# Advanced builder reference

For ordinary SSH/MQTT setup, use [Build firmware](BUILDER.md). This page covers
implementation details and custom payload authoring; source setup and tests are
in [SOURCE.md](SOURCE.md).

## SSH implementation

The SSH payload uses `openssl passwd -6` for salted SHA-512-crypt passwords,
passed through private stdin, and `dropbearkey` for a new ECDSA P-256 host key.
Key-only builds set Dropbear `-s`; password builds enable daemon-wide password
authentication while preserving vendor accounts. The added `root2` account has
UID/GID 0 and home `/home/root`.

The host key is newly generated for each build and installed at
`/etc/dropbear/classe100x_ecdsa_host_key`. The existing init script receives that
path through `DROPBEAR_RSAKEY` (despite the variable name, its `-r` option accepts
ECDSA). This avoids its volatile RSA-key generation path. Identity is intended
to remain stable across reboots; a new build intentionally has a different host
identity. The FWZ contains the host private key and possibly configuration
secrets: treat it as a private artifact, not as encrypted secret storage.

## MQTT limits and diagnostics

The bridge uses stock Python 2.7 and libmosquitto. Prefixes use ASCII letters,
digits, `_`, `-` and nonempty `/`-separated levels, at most 128 characters.
Credentials are UTF-8, at most 512 bytes each, without NUL/newlines. Unknown
configuration fields fail. Hex-encoded configuration values are not encryption.

The existing household bell frame `*8*1#1#4#21*10##` and door press/release
`*8*19*20##`, `*8*20*20##` are preserved. Callers supply the press/release timing.
Public-monitor output is not identical to the legacy tcpdump stream; only the
documented household coverage has been observed on the existing device.

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

With no payloads the decompressed main filesystem must remain byte-identical.
The rebuilt archive is not byte-identical: compression, timestamps and encryption
randomness can differ. A fresh SSH host key also prevents identical SSH builds.

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
For the included SSH and MQTT features, use [BUILDER.md](BUILDER.md); you do
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

You can combine this with included features by adding their options to the same
build command.

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
can run; such a batch is rejected before publication. Runtime/output are bounded;
failure diagnostics include tool identity, exit status and stderr. Filesystem
check and packaging failures also include their diagnostic stdout. Raw debugfs
readback and hook stdout are not printed because they can contain file contents.
Hook process groups are terminated on timeout/cancellation. Hook failures retain
their payload/phase, original error and traceback, including for unexpected
exceptions. Authors can still raise `FirmwareError` with a short user-facing
summary. Never deliberately include credentials in error messages. The standard
payload context registers explicit secret inputs for exact-value removal.

Verification reads actual bytes and metadata, runs after each payload, after all
payloads, and on the reopened output image. Bundled SSH checks pin expected stock
inputs, preserve vendor accounts, check critical startup files, and verify the
result's contents/owners/modes/links. Its replacements require ordinary
single-link files without xattrs/ACLs. Replacement intentionally recreates inodes
and timestamps; it does not promise metadata-preserving general replacement.
The shadow file becomes 0600, and `/etc/dropbear` becomes root-owned 0700.

## Publication and failure handling

Originals and existing outputs are never overwritten; aliases and existing
symlinks are rejected. The destination directory must exist. Allow at least
3.5 GiB free workspace space. There is no automatic filesystem repair, resize,
resume or device cleanup. Unexplained baseline filesystem errors stop the build.

Only a fully reopened/verified image is published, mode 0600, using a same-volume
no-clobber operation. Successful reports are optional and tied to the final FWZ
hash. Image publication precedes report publication; if the latter fails, the
valid image remains and the CLI reports that distinction. Once a requested report
path has been validated, build failures also try to publish a private no-clobber
report with `status: failed`, the build stage, exception chain and stack traces.
Failure-report publication errors do not replace the original build failure.
Diagnostics retain paths and original tool messages; review reports before sharing.
Known secret inputs are removed, and no locals, stdin or command arguments are
collected. Existing reports are never overwritten, including on a later attempt.

Handled cancellation (including SIGTERM/SIGHUP) removes unpublished workspaces.
An uncatchable termination can leave a private `.classe100x-build-*` directory;
those directories are Git-ignored. There is no promise of secure erasure on SSDs.
