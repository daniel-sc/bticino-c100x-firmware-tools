# Hardware acceptance record

## Completed without firmware writes

- [x] Preserve and hash the original stock and selected modified 1.5.8 archives.
- [x] Validate the complete selected archive, gzip trailers, nested kernel ZIP,
      payload SHA-256 and POSIX checksums.
- [x] Establish the vendor C100X recovery-first sequence from installer and
      device code; verify normal/recovery FTP credentials offline.
- [x] Read type, firmware, hardware, status, uptime and normalized object model
      from the existing intercom through the research SSH tunnel.
- [x] Build pinned TetherKit; its 23 CTest entries passed. This run does not
      establish privileged or C100X hardware coverage.
- [x] Pass 36 Python tests: framing, archive rejection/integrity, sequence and
      failure at each simulated step, lost write ACK, FTP failures, stale reboot
      replies, USB reconfiguration and signal-driven helper cleanup.

## Native read-only preflight — passed

Use the commands in [../README.md](../README.md), before restoring stock:

- [x] Record Mac OS version, TetherKit revision and device USB enumeration.
- [x] Start `usb` with terminal sudo; record the system-side feth interface.
- [x] Verify `.2/30` and that the route to `.1` uses this interface.
- [x] Run `probe`; require type 200, firmware 1.5.8, hardware 02*06*0,
      model 1.0.99, status 4*0 and valid uptime.
- [x] Run `plan` for the selected image; require the expected archive hash and
      `device_writes: false`.
- [x] While completely idle, disconnect/reconnect only USB, keeping device power
      stable. Verify interface reconfiguration and a second successful probe.
- [x] Stop the supervisor with Ctrl-C while idle; verify its feth pair is removed.

These checks do not start firmware transfer or enter recovery. The supervisor is
currently stopped; start it again before subsequent native device checks.

### 2026-10-27: USB enumeration

- macOS 27.0.1 (26A434).
- TetherKit revision `1ded051fd243c547fd6e250a898f0164cc30561d`.
- Native enumeration found `1da4:0056`, bus 000/device 001, control interface 0,
  data interface 1, RNDIS signature `02/02/ff`.
- Research SSH access was restored. Before terminal sudo was started, no feth
  interface existed and the route to `192.168.129.1` used the ordinary LAN
  default route (`en0`). Native probe/plan had not yet run at this point.

### 2026-10-27: Native USB probe and plan passed

- User started the supervisor with terminal sudo. System-side `feth0` is active
  at `192.168.129.2/30`, paired with driver-side `feth1`.
- Route to `192.168.129.1` uses `feth0` and subnet `192.168.129.0/30`.
- Direct native `probe` returned type 200, firmware 1.5.8, hardware 02*06*0,
  status 4*0, extended identity 99*6*1*0 and normalized model 1.0.99.
- Direct native `plan` validated the selected archive, vendor profile and device,
  returning the expected archive hash and `device_writes: false`.
- Uptime advanced from 1 day 00:30:48 during probe to 1 day 00:31:33 during plan.
  Neither command used the SSH tunnel or sent firmware-write/reboot commands.
- At this point, physical idle reconnect and supervisor cleanup checks were
  still pending, alongside native FTP transfer, recovery-mode networking and
  actual flash acceptance.

### 2026-10-27: Idle USB reconnect passed

- User disconnected/reconnected USB with the supervisor running. Afterward,
  `feth0` was active at `.2/30`, paired with `feth1`, and the device route still
  used `feth0`.
- A fresh direct USB probe succeeded with the same expected identity/status.
  Uptime was 1 day 00:33:37, consistent with uninterrupted device power.
- macOS reported “disk not ejected properly”. The intercom also exposes a
  52.4 MB external physical disk named `C100X` (disk7 during this check).
  This storage interface is separate from the RNDIS update transport; the CLI
  has not written firmware or files to that volume. Its filesystem integrity
  has not been checked. Eject the C100X volume before future idle cable removal.
- Supervisor Ctrl-C cleanup was the remaining idle transport check at this point.

### 2026-10-27: Supervisor cleanup passed

- User stopped the supervisor with Ctrl-C while the device was idle and USB
  remained connected.
- Both `feth0` and `feth1` disappeared from the macOS interface list.
- The USB subnet route was removed; lookup for `.1` now falls back to the
  existing LAN default route through `en0`/`192.168.0.1`.
- No matching TetherKit CLI or Python USB supervisor process remained.
- Native read-only preflight is complete. FTP transfer, recovery-mode networking
  and stock-to-modified flash acceptance remain pending.

## 2026-10-27: Plain partition backups completed

At the user's request, raw uncompressed images of the main firmware and
configuration/data partitions were acquired over LAN SSH into the Git-ignored
directory `research/backups/20261027T201641Z/`:

- `mmcblk2p6.img`: 1,073,741,824 bytes. The source filesystem was mounted
  read-only. Local reread SHA-256 matched the received stream and an independent
  device-side SHA-256 read of the partition.
- `mmcblk2p7.img`: 2,567,962,624 bytes. Local reread SHA-256 matched the received
  stream. The source remained mounted read-write, so this is an unquiesced live
  copy, not a guaranteed consistent filesystem/application snapshot.
- `manifest.json` records acquisition details and verification results;
  `SHA256SUMS` records the image hashes. No partial files remained.
- The backup directory has mode 0700 and both images have mode 0600. Images
  contain private device data and credentials and remain outside Git.
- No device writes, filesystem freezes or service stops were requested. These
  images do not include bootloader/kernel/recovery partitions, are not FWZ
  packages, and have not been restore-tested.

## Stock-to-modified acceptance — pending

- [ ] Make the previously successful Windows/MyHOME setup available.
- [ ] Restore stock 1.5.8 with that established method and confirm normal boot.
- [ ] Check baseline calling, audio/video and door release.
- [ ] Reconnect to macOS; run native `probe` and `plan` again.
- [ ] Run the explicit `flash` command without SSH. Keep the Mac awake, device
      powered and transport terminal open throughout.
- [ ] Record all four payload stages and all three verified reboot boundaries.
- [ ] Confirm final normal state 4*0 and firmware 1.5.8.
- [ ] Verify incoming call/ring and answering.
- [ ] Verify audio in both directions and video.
- [ ] Verify door release.
- [ ] Verify SSH access supplied by the selected modified image, using the
      existing credentials interactively without recording them.
- [ ] Stop the transport after completion; confirm interface cleanup.

Never deliberately interrupt an actual write to test failure handling. On an
unexpected stop, record the last stage and error, keep power stable and assess
the observed state before any further update. Windows availability is not proof
of recoverability from every interrupted state.

Record outcomes and timestamps here after the hardware run. Until then there is
no claim of a successful native USB flash or completed functional acceptance.
