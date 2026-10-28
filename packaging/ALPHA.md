Self-contained builder and flasher for **Apple Silicon macOS**. See `release.json`
for the artifact's minimum macOS version, bundled tool versions and source hashes.

Download the DMG, copy `C100X` into a writable location, open a terminal in that
folder, then run `./c100x --help`.
Keep `c100x` and `support` together. No Homebrew, Python, Xcode or MyHOME setup.

- Build as your ordinary user: `./c100x build-fw --stock c100x-1.5.8 --payload ssh --ssh-password --output custom.fwz`
- Read-only device preflight: `sudo ./c100x plan custom.fwz`
- Explicit firmware update: `sudo ./c100x flash custom.fwz`

Plan/flash manage USB networking automatically. Keep stable device power and USB
throughout flashing. An error stops subsequent commands; uncertain writes are
never retried, and cleanup does not reboot the device.

**Experimental alpha:** offline tests and packaged smoke checks have passed.
Full native flashing, recovery-mode networking and functional acceptance remain
unverified. Version 1 waits for successful hardware validation.

The DMG is Developer ID signed, notarized and stapled. Dependency sources and
build recipes are supplied alongside it; firmware and user credentials are not
distributed. Keep generated firmware private.
