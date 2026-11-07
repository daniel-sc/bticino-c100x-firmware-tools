# Bundled CLI releases

## Release checklist

1. Review [ACCEPTANCE.md](ACCEPTANCE.md) against the changes being released;
   apply the validation policy below.
2. Update `packaging/RELEASE.md` and the README version for the intended tag.
   Keep release notes dense and user-facing: **one or two sentences per change**,
   focused on its effect. Omit internal review logs and test inventories; link to
   validation details when useful. The first stable release uses a brief product
   introduction instead of an alpha-by-alpha changelog.
3. Run main CI against the intended release commit, then tag it. Use
   `v<major>.<minor>.<patch>` for stable releases or append `-alpha.<number>` for
   prereleases. Stable releases become GitHub's latest release; alphas do not.
4. Complete signing/notarization, downloaded-artifact checks and the manual
   Homebrew tap update below. Record observed results in the validation history
   and update the current acceptance summary.

## Validation policy

Validation follows **changed behavior**, not the version number. A release does
not require another device flash merely because it contains changes or becomes
stable. Existing hardware acceptance carries forward for unchanged behavior.

Maintain acceptance by capability and tested conditions. Keep exact versions,
commits and configurations as provenance in the validation history. A structural,
incompatible or other material change reopens only the affected checks; it does
not reset the project's acceptance record. Packaging, signatures and installation
remain checks of each newly published artifact.

| Change | Appropriate checks |
| --- | --- |
| Documentation | Accuracy, examples and links. |
| Small host-only fixes, diagnostics or packaging | Relevant offline regressions; packaged CI and downloaded-artifact checks for the release. |
| Material changes to firmware writes, reboot/USB handover, compatibility or device payload startup/runtime | Targeted hardware validation of the affected behavior before claiming it validated; combine flash-dependent checks into a planned hardware run. |

A breaking CLI option can be verified offline; a small patch to write sequencing
can need hardware validation. Major/breaking releases deserve a scope review, but
the version label alone does not determine whether a flash is useful.

The USB storage-discovery correction is a bounded best-effort host step:
its regression and packaged checks suffice for release. Live unmount/network and
notification observations can wait for convenient maintenance and the next
otherwise-planned flash. Stock-to-modified now has community-reported coverage
on `02*07*0`. MQTT resilience and
additional SSH-key coverage remain disclosed follow-ups, not recurring release gates. Do not turn
deferred checks into claimed passes. See [ADR-011](DECISIONS.md#adr-011-distribute-one-self-contained-cli-through-alpha-releases).

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
- `plan`/`flash` and `plan-recovery`/`recover` own USB startup, readiness, route
  checks, ECM/RNDIS handover and cleanup.
  Firmware validation precedes USB startup. The updater retains its existing
  recovery-first sequence and never retries uncertain writes. Local cleanup does
  not send device commands. `--external-usb` is an advanced development escape hatch.
- CI builds and publishes tagged **alpha prereleases** after offline tests and
  packaged smoke checks, and stable releases when tagged without the alpha suffix.
  USB and SSH full-flash sequences and functional acceptance have passed for the
  tested installation; subsequent validation follows the policy above.
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
candidate DMG. These ad-hoc-signed candidates are CI artifacts only. Stable and
alpha tags additionally require all five signing secrets, sign all Mach-O files,
test the signed bundle, notarize/staple the DMG, and publish a GitHub release with
sources, provenance and SHA-256 checksums. Only alpha tags use `--prerelease`.

Choose a new stable or alpha tag as described above. Use the same
`VERSION` below for the local build, tag and download; never reuse a published tag.
Build locally with Command Line Tools, the pinned helper, and mise Python:

```sh
brew install e2fsprogs dropbear openssl@3 libusb sevenzip pkgconf xz zstd
printf 'New release tag: '
read -r VERSION
OUT=".local/release-$VERSION"
mise exec -- python packaging/build.py --version "$VERSION" --output "$OUT"
mise exec -- python packaging/smoke.py "$OUT/C100X"
mise exec -- python packaging/dmg.py "$OUT/C100X" "$OUT/c100x-candidate.dmg"
```

Choose a fresh output directory for each build. Python links explicitly to
OpenSSL 3: the initial OpenSSL 4 build compiled but its `_ssl` extension could
not import (`SSLv3_method` was unavailable). Build-time and relocated-bundle
checks exercise TLS and compression imports. Tk/GNU dbm are optional and omitted.

The deployment target starts at macOS 15.0. Auditing every shipped Mach-O raises
the manifest minimum when dependencies require a newer OS; local Homebrew
bottles may therefore require a newer OS than a GitHub-built release. The audit
rejects missing arm64 slices, external libraries/symlinks and remaining rpaths.

Before tagging, commit the documentation alongside the code:

- Check README setup/update instructions and `docs/BUILDER.md` against the release.
- Update `packaging/RELEASE.md` for the chosen version. Preserve dated evidence in
  `docs/VALIDATION-HISTORY.md` and summarize current results in `docs/ACCEPTANCE.md`
  only after observing them.
- Check the candidate's `README.md`, short `README.txt` entry point and linked
  `docs/` files. The package copies the repository README directly.

After main CI passes and signing secrets are configured, tag the intended commit:

```sh
git tag -a "$VERSION" -m "C100X $VERSION"
git push origin "$VERSION"
```

After the tagged workflow publishes the release:

```sh
DOWNLOAD=".local/downloaded-$VERSION"
gh release download "$VERSION" --dir "$DOWNLOAD"
(cd "$DOWNLOAD" && shasum -a 256 -c SHA256SUMS)
```

Assess the downloaded DMG with `spctl --assess --type open --context
context:primary-signature --verbose=2 <file.dmg>` and validate its stapled ticket.
Mount it read-only, copy out `C100X`, check its native Developer ID signatures,
and repeat `packaging/smoke.py` against the copy. Gatekeeper's app-execution
assessment can reject a bare CLI as "not an app" even with valid code signatures.
Check the downloaded README and guide links as well. Exercise real local firmware
builds separately; firmware stays outside GitHub CI. Record observed results in
ACCEPTANCE.md before claiming validation, then update the online README's release
link. Released documentation remains a snapshot; corrections ship in a new release.

## Homebrew tap follow-up

The public [daniel-sc/homebrew-tap](https://github.com/daniel-sc/homebrew-tap)
repository contains `Casks/c100x.rb` (stable) and `Casks/c100x@preview.rb`
(prerelease), installing the
existing signed DMG's complete bundle into `/Applications/C100X` and linking
`c100x` onto PATH. Keep Apple Silicon/macOS 15+ requirements aligned with the
release metadata. Install with:

```sh
brew install --cask daniel-sc/tap/c100x
```

After publishing and validating **each release**, manually update the matching
cask's version and DMG SHA-256 (and URL if needed), then commit and push the tap.
Stable tags update `c100x`; alpha/beta tags update `c100x@preview`. Keep their
mutual `conflicts_with` declarations: both install the same bundle and executable.
Use the published DMG checksum, not a local candidate's. Verify Brew installation
or upgrade and `c100x --version` before reporting the tap updated. Updates are
manual; there is no cross-repository release automation.
