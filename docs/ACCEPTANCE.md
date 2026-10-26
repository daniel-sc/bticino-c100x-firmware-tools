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

## Native preflight — pending physical USB access

Use the commands in [../README.md](../README.md), before restoring stock:

- [ ] Record Mac OS version, TetherKit revision and device USB enumeration.
- [ ] Start `usb` with terminal sudo; record the system-side feth interface.
- [ ] Verify `.2/30` and that the route to `.1` uses this interface.
- [ ] Run `probe`; require type 200, firmware 1.5.8, hardware 02*06*0,
      model 1.0.99, status 4*0 and valid uptime.
- [ ] Run `plan` for the selected image; require the expected archive hash and
      `device_writes: false`.
- [ ] While completely idle, disconnect/reconnect only USB, keeping device power
      stable. Verify interface reconfiguration and a second successful probe.
- [ ] Stop the supervisor with Ctrl-C while idle; verify its feth pair is removed.
      Start it again for subsequent work.

These checks do not start firmware transfer or enter recovery.

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
