# Research access, backups and continuation

The native user workflow is in [../README.md](../README.md). This file records
local operational knowledge that was previously scattered through the discussion.
Paths and SSH aliases below describe this workspace; they are not portable defaults.

## Research SSH and probe tunnel

The existing modified device can be reached with the user's `klingel` SSH alias
(`root2`, observed LAN address `192.168.0.241`). The alias and authentication
configuration live outside the repository. Stock firmware is not assumed to
provide this access. No SSH installation is part of the flashing workflow.

To open the password-authenticated research session in a real terminal:

```sh
ssh -M -S ~/.ssh/bticino-research.sock \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -o ExitOnForwardFailure=yes \
  -N -L 22000:127.0.0.1:20000 klingel
```

Enter the password interactively and leave that terminal open. Check the session:

```sh
ssh -S ~/.ssh/bticino-research.sock -O check klingel
```

Use an existing session without prompting or recording a password:

```sh
ssh -S ~/.ssh/bticino-research.sock -o BatchMode=yes -o ConnectTimeout=5 klingel 'uptime'
mise exec -- .venv/bin/python -m classe100x probe --host 127.0.0.1 --port 22000
```

The forwarded probe reaches the device's loopback OpenWebNet endpoint over LAN
SSH. It does not exercise USB routing or RNDIS. A missing control socket means
the user needs to reopen the session. Do not assume a connection from a previous
day is still available. An earlier attempt to install `authorized_keys` failed
because the target filesystem was read-only; no such installation was completed.

## USB network and storage are separate functions

Native control/transfer uses RNDIS, with a system-side feth address `.2/30`.
The device also exposes a roughly 52.4 MB `C100X` disk. Removing USB while this
volume is mounted caused macOS's “disk not ejected properly” warning during the
idle reconnect test. Eject the volume before future idle cable removal.

The updater does not copy firmware onto that disk. Disk and feth numbers are
temporary OS assignments; do not hard-code the observed `disk7` or `feth0` into
new logic. Graceful supervisor shutdown removed its interfaces without needing
to unplug USB. LAN SSH backups can continue without USB if network and device
power remain available. None of these observations justifies unplugging during
an actual firmware update.

## What the plain backups contain

The explicitly requested backup is at
`research/backups/20261027T201641Z/`; sizes and verification results are in
[ACCEPTANCE.md](ACCEPTANCE.md). The directory includes raw uncompressed images,
`manifest.json` and `SHA256SUMS`.

| Partition | Observed use | Backup consistency evidence |
| --- | --- | --- |
| `/dev/mmcblk2p6` | Main root filesystem, mounted read-only | Local reread and independent device-side hash matched |
| `/dev/mmcblk2p7` | Writable configuration/data mounted at `/home/bticino/cfg/extra` | Local reread matched the acquired stream; unquiesced live copy |

A loop-backed USB-related volume was also mounted beneath that writable area.
A matching hash verifies copied bytes, not filesystem/application consistency
for a concurrently changing partition. No services were stopped and no filesystem
was frozen. The script used was `.local/backup_partitions.py`, a Git-ignored,
one-off acquisition helper; there is no supported `backup` or `restore` command.

These are **main + data**, not **main + recovery** backups. Bootloader, kernel
and recovery partitions were not included, and no restore has been tested.
They contain device secrets; directory mode is 0700 and image modes are 0600.
Keep raw contents out of logs and Git. A local Git commit is not a backup of
these ignored files; any additional copy must be arranged separately.

## What would be needed to make an FWZ from a backup?

The main partition image would supply the main filesystem payload after gzip
compression. A package would also need a matching recovery filesystem, kernel/DTB
ZIP, correct manifest and archive encryption. Existing preserved package components
could be reused only after establishing that they are the intended matching set.
Then validate the entire new archive and explicitly review its new allowlisted
hash. This does not establish that the newly packaged image can be restored.

The separate data partition is not a substitute for the recovery payload and
does not belong in the researched four-member FWZ layout. Creating firmware or
an automated restore workflow remains outside the implemented CLI's scope.
For reinstalling the previously flashed modified build, the preserved original
modified FWZ is already the known package; a live backup captures possible later
on-device changes but is a different artifact.

## Continuing development or hardware testing

- Start with [ACCEPTANCE.md](ACCEPTANCE.md) for the last observed results. As of
  2026-10-27, native normal-mode probe/plan/reconnect/cleanup passed; FTP transfer,
  recovery-mode networking and actual flashing remained unverified.
- Either direct re-flash or the stock-to-modified acceptance path is possible;
  understand the distinction in [ADR-006](DECISIONS.md#adr-006-separate-direct-re-flash-testing-from-stock-device-acceptance).
- Before another native check, reconnect USB as needed and restart the supervisor
  in the user's sudo terminal, then inspect the route and run `probe`/`plan`.
- After actual flashing, record the three reboot boundaries and verify calls,
  both audio directions, video, door release and SSH. Report the actual evidence,
  not simply “flash successful” because the worker became idle.
- On an unexpected stop, preserve the stage/error and stable device power. There
  is no validated automatic resume/restore procedure; select subsequent actions
  based on observed state and protocol evidence.

## Reproducing the research workspace

Git contains source, tests, docs, mise configuration and a Ghidra decompilation
helper. It excludes vendor binaries, decompiled output, device images and tool
builds. `mise run research-setup` installs the additional Python analysis packages;
Ghidra/Java and .NET/ILSpy were used for device/vendor decompilation respectively.
ILSpy was installed locally at `.local/dotnet-tools/ilspycmd` (11.1.0.9782), and
Ghidra's macOS arm64 decompiler needed a local build during research. These steps
are not yet an end-to-end automated research rebuild.

The researched MyHOME installer came from the vendor's
[download endpoint](https://www.homesystems-legrandgroup.com/MatrixENG/liferay/bt_mxLiferayCheckout.jsp?fileFormat=generic&fileName=MyHOME_Suite_030538.exe&fileId=58107.23188.60514.44282).
Its profile member and decompiled reference locations are listed in
[PROTOCOL.md](PROTOCOL.md). The TetherKit clone/revision and original firmware
locations are in the README. A fresh clone requires those external inputs; the
research files cited by path are not promised to exist there automatically.
