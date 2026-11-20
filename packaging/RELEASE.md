**v0.3.0 brings the full build-and-flash workflow to Ubuntu Desktop.** Build a custom firmware image, connect a stock C100X over USB, and install it directly from Linux. No Mac or pre-existing SSH access is required.

- **Native USB flashing:** the CLI manages the USB network connection and reconnects through the intercom’s recovery and normal reboots. This experimental backend targets native Ubuntu 24.04 and 26.04 Desktop with NetworkManager: a complete flash and owner-reported household checks passed on 26.04.1; 24.04 passed package and offline tests but has no recorded hardware flash.
- **First Linux download:** extract `c100x-v0.3.0-linux-x86_64.tar.gz` for firmware building, inspection and wireless SSH updates on x86-64 Linux with glibc 2.39+. Python and builder tools are included.
- **Earlier source firmware:** SSH updates can start from a matching source profile,
  including the recorded 1.5.7 profile. Sources that regenerate their SSH host key
  require an explicit opt-in.
- **Manual continuation:** verify installed recovery before resuming, or install
  main from an already running recovery system over SSH. Errors retain whether
  clearing the main kernel was attempted. The generalized 1.5.7 and SSH continuation paths have offline coverage only.

See the [Linux USB guide](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/v0.3.0/docs/LINUX.md#experimental-native-usb), [installation instructions](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/v0.3.0/README.md#installation) and [hardware validation record](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/v0.3.0/docs/ACCEPTANCE.md). Firmware is not distributed.
