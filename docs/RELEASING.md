# Bundled CLI releases

## Agreed design

- One Apple Silicon macOS CLI distribution for building, inspecting, planning and
  flashing. A DMG carries a relocatable `C100X` folder with one `c100x` entry point
  and private support files. No end-user package-manager/compiler setup.
- Bundle a portable CPython interpreter rather than freeze Python imports. This
  preserves the existing trusted Python-hook contract and standard library.
  Hooks do not install additional pip dependencies. Build/hook execution refuses
  root; only USB networking requires `sudo`.
- Bundle TetherKit, libusb, e2fsprogs, 7zip, Dropbear keygen and OpenSSL. Use
  relative library paths, preserve license notices, and publish dependency source
  archives/build metadata beside binaries.
- `plan`/`flash` own USB startup, readiness, route checks, reconnection and cleanup.
  Firmware validation precedes USB startup. The updater retains its existing
  recovery-first sequence and never retries uncertain writes. Local cleanup does
  not send device commands. `--external-usb` is an advanced development escape hatch.
- CI builds and publishes tagged **alpha prereleases** after offline tests and
  packaged smoke checks. Hardware flashing is not required for an explicitly
  experimental alpha; v1 waits for observed full flash and functional acceptance.
- Release artifacts are Developer ID signed, notarized and stapled. Downloaded
  artifacts are checked locally too; no hardware writes are implied by that check.

## Signing credentials (no Xcode application required locally)

Use repository Actions secrets at:
https://github.com/daniel-sc/bticino-c100x-firmware-tools/settings/secrets/actions

The existing `work_log` Developer ID identity can sign this CLI. GitHub cannot
export repository secret values; re-provision them from their originals or a new
export. Do not retrieve secrets through a workflow or print them in logs.

1. Open **Keychain Access**, select **login → My Certificates**, and locate the
   existing **Developer ID Application** certificate with its private key.
   If the certificate is instead under **System → Certificates** while its key
   is in login, export the public certificate as `.cer`, then select login and
   import it using **File → Import Items**. The paired identity should then
   appear under **login → My Certificates**. Keep the System copy in place.
2. **File → Export Items**, choose `.p12`, and set a new export password. This
   does not require the password of a previous P12 export. Do not use Developer
   ID Installer; that certificate type is for installer PKGs, not this DMG.
   Check the selected certificate's name before exporting: a `localhost`
   development/TLS certificate is not a code-signing identity.
3. At https://account.apple.com, select **Sign-In and Security → App-Specific
   Passwords** and generate one for this repository's notarization workflow.
4. Set these repository secrets:

   | Name | Value |
   | --- | --- |
   | `MACOS_CERTIFICATE_P12_BASE64` | Base64 of the P12 containing certificate and private key |
   | `MACOS_CERTIFICATE_PASSWORD` | New P12 export password |
   | `APPLE_ID` | Developer account email |
   | `APPLE_TEAM_ID` | Team ID from developer membership/signing identity |
   | `APPLE_APP_SPECIFIC_PASSWORD` | Newly generated app-specific password |

   Transfer the certificate without displaying it:

   ```sh
   base64 < ~/Downloads/c100x-signing.p12 |
     gh secret set MACOS_CERTIFICATE_P12_BASE64 --repo daniel-sc/bticino-c100x-firmware-tools
   ```

If the signing identity is no longer available, create a CSR using Keychain
Access's **Certificate Assistant → Request a Certificate From a Certificate
Authority**, saved to disk. In https://developer.apple.com/account/resources,
add a **Developer ID Application** certificate, upload the CSR, download the
`.cer`, and double-click to install it alongside the generated private key.
Then export the P12 as above. The portal cannot recover an old private key.

## Build and publish

The `Test and package` workflow runs the offline suite on pull requests. Main
pushes and manual runs also build the pinned USB helper and a self-contained
candidate DMG. These ad-hoc-signed candidates are CI artifacts only. Tags matching
`v0.<minor>.<patch>-alpha.<number>` additionally require all five signing secrets,
sign all Mach-O files, test the signed bundle, notarize/staple the DMG, and publish
a GitHub prerelease with sources, provenance and SHA-256 checksums.

Build locally with Command Line Tools, the pinned helper, and mise Python:

```sh
brew install e2fsprogs dropbear openssl@3 libusb sevenzip pkgconf xz zstd
mise exec -- python packaging/build.py --version 0.1.0-alpha.1 --output .local/release
mise exec -- python packaging/smoke.py .local/release/C100X
mise exec -- python packaging/dmg.py .local/release/C100X .local/release/c100x-candidate.dmg
```

Choose a fresh output directory for each build. Python links explicitly to
OpenSSL 3: the initial OpenSSL 4 build compiled but its `_ssl` extension could
not import (`SSLv3_method` was unavailable). Build-time and relocated-bundle
checks exercise TLS and compression imports. Tk/GNU dbm are optional and omitted.

The deployment target starts at macOS 15.0. Auditing every shipped Mach-O raises
the manifest minimum when dependencies require a newer OS; local Homebrew
bottles may therefore require a newer OS than a GitHub-built release. The audit
rejects missing arm64 slices, external libraries/symlinks and remaining rpaths.

After CI passes and signing secrets are configured:

```sh
git tag v0.1.0-alpha.1
git push origin v0.1.0-alpha.1
gh release download v0.1.0-alpha.1 --dir .local/downloaded-alpha
(cd .local/downloaded-alpha && shasum -a 256 -c SHA256SUMS)
```

Assess the downloaded DMG with `spctl --assess --type open --context
context:primary-signature --verbose=2 <file.dmg>` and validate its stapled ticket.
Mount it read-only, copy out `C100X`, check its native Developer ID signatures,
and repeat `packaging/smoke.py` against the copy. Gatekeeper's app-execution
assessment can reject a bare CLI as "not an app" even with valid code signatures.
Exercise real local firmware builds separately; firmware stays outside
GitHub CI. Record observed results in ACCEPTANCE.md before claiming validation.
