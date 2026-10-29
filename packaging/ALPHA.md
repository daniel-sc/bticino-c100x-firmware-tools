Self-contained builder and flasher for **Apple Silicon macOS**. See `release.json`
for the artifact's minimum macOS version, bundled tool versions and source hashes.

Open the DMG and drag `C100X` onto the Applications shortcut, then eject the DMG.
Open a terminal in a writable working folder and run `/Applications/C100X/c100x --help`.
Keep `c100x` and `support` together. No Homebrew, Python, Xcode or MyHOME setup.
For a per-user installation, copy to `~/Applications` and adjust the paths below.
Generated firmware belongs in your working folder, outside the installation.

- Build as your ordinary user: `/Applications/C100X/c100x build-fw --stock c100x-1.5.8 --payload ssh --ssh-password --output custom.fwz`
- Read-only device preflight: `sudo /Applications/C100X/c100x plan custom.fwz`
- Explicit firmware update: `sudo /Applications/C100X/c100x flash custom.fwz`

Plan/flash manage USB networking automatically. Keep stable device power and USB
throughout flashing. An error stops subsequent commands; uncertain writes are
never retried, and cleanup does not reboot the device.

**New in alpha.2:** optional recovery readback before clearing the normal kernel,
for devices with SSH already enabled. Add
`--verify-recovery-ssh --ssh-user root2 --ssh-password` to `plan`/`flash`;
the password is prompted once per command and kept in memory. See the included
flashing guide for key authentication and verification limits. The standard
stock-device workflow still needs no SSH. This release also adds the DMG's
drag-and-drop Applications shortcut.

**Experimental alpha:** offline tests and packaged smoke checks have passed.
Full native flashing, recovery-mode networking and functional acceptance remain
unverified, including the new USB/SSH verification path. Version 1 waits for
successful hardware validation.

The DMG is Developer ID signed, notarized and stapled. Dependency sources and
build recipes are supplied alongside it; firmware and user credentials are not
distributed. Keep generated firmware private.
