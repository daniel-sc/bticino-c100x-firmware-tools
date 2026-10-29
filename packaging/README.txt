BTicino Classe 100X Firmware Tools — alpha

Drag the entire C100X folder onto the Applications shortcut in this disk image,
then eject the disk image. Keep c100x and support together. You can also copy
the folder to ~/Applications for a per-user installation.
No Homebrew, Python, Xcode or MyHOME installation is required.

Open a terminal in a writable working folder for your firmware, then run:

  /Applications/C100X/c100x --version
  /Applications/C100X/c100x builder-doctor
  /Applications/C100X/c100x build-fw --stock c100x-1.5.8 --payload ssh --ssh-password --output custom.fwz
  /Applications/C100X/c100x inspect-fw custom.fwz
  sudo /Applications/C100X/c100x plan custom.fwz
  sudo /Applications/C100X/c100x flash custom.fwz

Adjust the executable path if you chose a different installation folder.
Keep generated firmware in your working folder, outside the installation.

Build as your normal user. Plan and flash manage USB networking automatically;
flash explicitly writes firmware and reboots the device. Keep stable power/USB.
An error stops the sequence without retrying writes or rebooting as cleanup.

Firmware and generated credentials are private; do not share your generated FWZ.
This alpha has not completed hardware flash/functional acceptance. See docs for
the precise validation record, supported host version and payload authoring.

Source, release notes, dependency sources and checksums:
https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases
