# C100X 1.5.8 image builder

The builder modifies a private copy of the pinned **Door Entry C100X 1.5.8**
stock package. It runs natively on macOS using ordinary files, without mounting
ext4 or contacting a device. Linux is a design target awaiting the same test
matrix; Windows currently means a future tested Linux/WSL workflow, not native
Windows support.

## Setup and commands

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

## Authoring trusted payloads

```text
my-payload/
  payload.json
  prepare.py          # optional trusted host Python
  apply.debugfs       # required raw commands
  verify.py           # optional generally, required for bundled payloads
  files/              # optional ordinary assets
```

```json
{"id":"my-payload","version":"1","profile":"c100x-1.5.8"}
```

Set `"verification_required": true` to require `verify.py`. IDs are unique within
a build. Repeating `--payload` defines execution order; there is no dependency
solver, implicit SSH installation, command substitution or conflict inference.

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

`--inputs .local/build.private.json` accepts an object keyed by payload ID:

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

`debugfs` commands and Python hooks have the builder user's host permissions.
Raw commands can access other host files and invoke a shell. The private
workspace is **not a sandbox**. Review payloads as host programs. The engine
neither proves the complete write set nor detects every service interaction.

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
