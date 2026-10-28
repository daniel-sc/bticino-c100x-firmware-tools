BTicino Classe 100X Firmware Tools — alpha

Copy the entire C100X folder to a writable location. Keep c100x and support
together. No Homebrew, Python, Xcode or MyHOME installation is required.

From a terminal in that folder:

  ./c100x --version
  ./c100x builder-doctor
  ./c100x build-fw --stock c100x-1.5.8 --payload ssh --ssh-password --output custom.fwz
  ./c100x inspect-fw custom.fwz
  sudo ./c100x plan custom.fwz
  sudo ./c100x flash custom.fwz

Build as your normal user. Plan and flash manage USB networking automatically;
flash explicitly writes firmware and reboots the device. Keep stable power/USB.
An error stops the sequence without retrying writes or rebooting as cleanup.

Firmware and generated credentials are private; do not share your generated FWZ.
This alpha has not completed hardware flash/functional acceptance. See docs for
the precise validation record, supported host version and payload authoring.

Source, release notes, dependency sources and checksums:
https://github.com/daniel-sc/bticino-c100x-firmware-tools/releases
