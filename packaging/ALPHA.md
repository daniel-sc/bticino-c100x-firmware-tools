Self-contained builder and flasher for **Apple Silicon macOS**. See `release.json`
for the artifact's minimum macOS version, bundled tool versions and source hashes.

Start with `README.md` in the downloaded `C100X` folder for installation and links
to the build/flash guides. [Current online overview](https://github.com/daniel-sc/bticino-c100x-firmware-tools#readme).
No Homebrew, Python, Xcode or MyHOME setup is required.

**New in alpha.3:** optional `mqtt` builder payload using stock Python/libmosquitto
and the public loopback event monitor. Supply private broker settings with
`--inputs` and select `--payload mqtt`; SSH remains independently selectable.
The bridge preserves the tested household bell and door-control payloads, rejects
retained command replay and reconnects without deliberately replaying queued work.
See `docs/BUILDER.md` for plaintext transport, topic configuration,
compatibility limits and diagnostics. No HA configuration is installed.

**Experimental alpha:** offline tests and packaged smoke checks have passed.
Full native flashing, recovery-mode networking and functional acceptance remain
unverified, including USB/SSH verification and the new MQTT payload's target
runtime/startup/end-to-end behavior. Version 1 waits for
successful hardware validation.

The DMG is Developer ID signed, notarized and stapled. Dependency sources and
build recipes are supplied alongside it; firmware and user credentials are not
distributed. Keep generated firmware private.
