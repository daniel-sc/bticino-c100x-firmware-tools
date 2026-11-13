**C100X — Linux packages and SSH recovery.**

- **Linux download:** an x86-64 bundle includes Python and firmware-building tools.
   Build firmware and update over SSH on Linux with glibc 2.39+.
   Experimental USB targets native Ubuntu 24.04/26.04 Desktop with NetworkManager;
   A complete USB flash and owner-reported household checks passed on Ubuntu
   26.04.1; 24.04 hardware validation remains open. SSH updates try to prevent sleep
   with `systemd-inhibit`.
- **Earlier source firmware:** SSH updates can start from a matching source profile,
  including the recorded 1.5.7 profile. Sources that regenerate their SSH host key
  require an explicit opt-in.
- **Manual continuation:** verify installed recovery before resuming, or install
  main from an already running recovery system over SSH. Errors retain whether
  clearing the main kernel was attempted.

See [installation](https://github.com/daniel-sc/bticino-c100x-firmware-tools#installation)
and [validation](https://github.com/daniel-sc/bticino-c100x-firmware-tools/blob/main/docs/ACCEPTANCE.md).
Linux hardware coverage remains limited. Firmware is not distributed; keep generated images private.
