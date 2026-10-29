# Researched C100X 1.5.8 update protocol

## Evidence and scope

The implementation follows the Classe 100 X16E profile in MyHOME Suite 3.5.38,
cross-checked against stock device binaries and scripts. Decompiled source paths
below refer to local research artifacts, not distributed vendor source.

1. Installer member
   `default/resTargetDir4/devices/2266_1.5_BT/xml/Protocol/protocol.xml` identifies
   device `344682`, model `1.0.99`, provider `BTESUProtocolXPProvider` and
   `watershedVer=always`. `classe100x/vendor.py` bundles the normal/recovery FTP
   settings from this member. The source installer SHA-256 is
   `707d8a43a5296a1ea87c33f111e9269c8bbd0fe524ac5efe87bdede8b6eb311b`;
   the manufacturer download is linked in [OPERATIONS.md](OPERATIONS.md).
2. `research/myhome-BTicino.Core.v3.dll-VersionsHelper.cs`, lines 30–32:
   `always` evaluates to `CheckResult.lt`.
3. `research/myhome-btesuxp-provider/BTicino.Protocol.ProtocolManager.Providers.BTESUXP/BTESUProtocolXPProvider.cs`,
   `FirmwareUpdateWorkingMode` (around lines 429–729), selects recovery first
   and supplies separate recovery/main payload lists.
4. Under `research/myhome-BTicino.Protocol.ProtocolManager.Protocol.BTESUXP.ETH.dll/`:
   - `BTicino.Protocol.BTESUXP.ETH/ProtocolHelperEth.cs`, `UpdateFirmware`
     (around lines 170–300): status/error handling and recovery transition;
     `UpdateFrwFullEth` (around line 1516): main transfer and reboot.
   - `BTicino.Protocol.BTESUXP.ETH/EthernetCommandParser.cs`, `BuildCommand`
     (around lines 275–337): exact command strings. Extended identity parsing
     at lines 370–374 uses fields 0, 3 and 2 as code, line and brand.
   - `BTicino.Protocol.BTESUXP.ETH.Ethernet/EthernetProtocolUtility.cs`,
     `DoFileTransfer`, `CheckIfDeviceIsReady`, `RestartDeviceInRecoveryMode`
     and `UpdateFrw_Recovery`: FTP/commit/poll ordering and reboot behavior.
5. `research/device/bt_device.c`: extended identity construction near line 733;
   kernel invalidation near 4804; uptime near 5419; status near 5780;
   worker/reboot queries near 5966; checksum/write and start-transfer handlers
   near 6847–7121. Filesystem update handlers clear their corresponding kernel
   before writing the filesystem, requiring filesystem-before-kernel ordering.
6. `research/myhome-BTicino.Protocol.ServicePackManager/BTicino.Protocol.ProtocolManager.Common.Model.DevInfos/FwzWithInfoXmlV3.cs`
   parses XML 3.0 firmware modules and action/status associations.

The older BTESU v3 implementation is not authoritative for this profile: its
extended identity field mapping differs. The FWZ manifest still names its
provider `btesuv3`; the installed device profile selects BTESUXP.

Installed `bt_device`, `openserver`, `bt_daemon` and `fw_manager` were compared
with stock. Recovery `bt_device`, `openserver` and `bt_daemon` are byte-identical
to the corresponding main binaries. This supports the command interpretation
but does not replace a native hardware flash test.

## Transport and authentication

Stock main and recovery `/etc/init.d/bt-networking.sh` configure USB gadget
VID:PID `1da4:0056`, device `192.168.129.1/30` and host `.2`. The installer profile
advertises a `/29`; the implementation uses the device scripts' `/30`.
`/home/bticino/cfg/openserver` has `OwnPort=20000`, `ForceHMAC=0` and trusts `.2`.

OpenWebNet connection sequence: receive ACK, send `*99*0##`, receive ACK.
ACK is `*#*1##`; NACK is `*#*0##`. Authentication challenges are rejected without
logging their content. TCP frames may be fragmented or coalesced; each exchange
has a deadline and each frame a 4096-byte limit. A failed exchange closes the
connection.

Stock `/etc/vsftpd.conf` uses control port 21 and passive port 11111, with local
users chrooted. The firmware accounts' home is `/var/tmp/ftp`. Vendor normal
and recovery credentials were verified offline against the corresponding
stock password hashes. The fixed settings are bundled as public profile data;
normal log output and credential representations remain redacted. Personal SSH
credentials, generated host keys and private device configuration are not bundled.

## Read-only identity

| Request | Meaning / required result |
| --- | --- |
| `*#13**15##` | Device type `200` |
| `*#13**16##` | Firmware `1*5*8` |
| `*#13**17##` | Hardware `02*06*0` |
| `*#13**19##` | Uptime: days, hours, minutes, seconds |
| `*#13**40##` | Firmware state and extra status; initially `4*0` |
| `*#1013**1##` | Code, configuration, brand, line; observed `99*6*1*0` |

Data replies use the same prefix plus `*<fields>##`, followed by ACK. Object
model is **brand.line.code**, yielding `1.0.99`; configuration is not the line.
State 4 means normal operation requiring recovery for a main-firmware update.
State 1 means recovery. An extra-status field other than zero is rejected.

In ordinary non-NFS normal boot, state 4 also reflects completion of the stock
daemon's installed recovery **uImage** checksum check. It does not cover recovery
rootfs or DTBs; see the offline findings below.

These queries, including uptime and normalized identity, have been exercised on
the existing modified intercom through the research tunnel and directly over
native USB. On 2026-10-27, both native `probe` and the non-writing `plan` passed;
FTP transfer, recovery-mode networking and actual flashing remain unverified.

## Write sequence

Each stage starts with an idle-worker check and uses a single command session.

| Operation | Exact frame |
| --- | --- |
| Start recovery transfer | `*#13**#37*0##` |
| Start main transfer | `*#13**#36*0##` |
| Commit one uploaded file | `*#13**#35*<bytes>*0*<POSIX cksum>##` |
| Poll worker | `*#13**42##` |
| Close FTP | `*#13**#33*0##` |
| Clear main kernel for recovery boot | `*13*25**##` |
| Request reboot | `*#13**43##` |

1. Require normal state `4*0` and the expected firmware/hardware/model.
2. Start recovery transfer. Using normal-mode FTP credentials, upload
   `btweb_only_recovery.ext4.gz`, commit, and poll to idle. Repeat for `uImage.zip`.
3. Close FTP, settle, reboot and verify normal state `4*0` with reset uptime.
4. Clear the main kernel, reboot and verify recovery state `1*0` with reset uptime.
5. Start main transfer. Using recovery credentials, upload `btweb_only.ext4.gz`,
   commit and poll to idle. Repeat for `uImage.zip`.
6. Close FTP, settle, reboot and verify normal state `4*0` with reset uptime.

The firmware account's FTP directory must be empty before each upload and contain
only that payload afterward. Binary transfer length is checked with FTP SIZE.
No deletion of unexplained remote files is attempted. `/usr/bin/cksum` supplies
the POSIX checksum of the compressed payload; ZIP/zlib CRC32 is not equivalent.

Both researched archives have the same manifest and contain only `fwz.xml`, the
two filesystem gzip files and `uImage.zip`. Six extras referenced by the manifest
are absent from both archives. The firmware modules are processed separately
from configuration/extra updates; absent extra payloads are not invented.
The selected recovery and kernel files are byte-identical to stock. See
[selected-image.json](selected-image.json) for sizes and hashes.

## Completion, timeouts and errors

- Query 42 ACK means the upgrade child is absent. It **does not report the
  child's exit status or prove the written bytes are correct**. NACK means busy.
- Query 44 also schedules a reboot in the device handler. It is not a harmless
  read query and is excluded from the preflight allowlist.
- Write commands are sent once. Missing ACK, malformed reply or disconnect
  stops the sequence without retry or cleanup reboot. No resume is implemented.
- Worker polling uses a 180-second budget, five-second intervals and bounded
  command exchanges. Reconnection polling uses a 240-second budget with
  two-second per-exchange probe timeouts. An in-flight exchange may extend past
  the polling budget; all socket operations remain bounded. FTP uses 30-second
  socket timeouts, not a total-transfer deadline.
- Reboot proof compares uptime before/after with elapsed monotonic time. A
  temporary network outage or unchanged 1.5.8 version cannot establish reboot.
- Ctrl-C stops further commands and closes local sockets. It cannot cancel a
  write already accepted by the device. Keep the device powered after an error.
- Final protocol completion must be followed by calls, audio/video, door-release
  and SSH acceptance checks. The optional SSH gate below adds installed recovery
  readback; ordinary stock-device flashing has no full-filesystem readback.

Deliberate fault injection is restricted to simulation.

The actual device's boot environment was read on 2026-10-29. Its normal-to-recovery
fallback checks the kernel image and DTB load, not later Linux/rootfs/application
health. Bootloader and rescue evidence, including limitations of public recovery
reports, is recorded in [RECOVERY.md](RECOVERY.md).

## 2026-10-29: Stock USB-accessible recovery verification (offline research)

**Partial verification already exists; full recovery readback was not found.**
The existing post-recovery-write normal reboot and query-40 state check provide
more evidence than worker completion alone, but do not verify the recovery rootfs.
No new command was sent to the device during this research.

### Installed kernel check behind query 40

- Stock-matching `bt_daemon` was decompiled offline into
  `research/device/bt_daemon.c`. Startup clears status flags and sets recovery
  kernel status to `0` (around lines 2261–2304).
- Its normal, non-NFS startup path calls `FUN_0001d93c("/mnt/uImage", ...)`
  (around lines 1517–1558). This mounts the recovery kernel partition, opens the
  installed `uImage`, checks U-Boot magic, header CRC and data CRC, then unmounts
  it (function at `0x1d93c`, around lines 3794–3874). The caller records
  `1:<hex-data-CRC>` on success, or `2` on failure. A maintenance path also invokes
  the same check; this is not an on-demand readback command.
- `libcommon.so.0.0.c`, getters/setters near `0x4570c`/`0x45a84`, reads/writes
  `/var/tmp/flags/RECOVERY_PARTITION_KNL_STATUS`. A missing flag reads as `0`.
- `bt_device.c`, query 40 around lines 5780–5840, returns NACK while that value
  is `0`. In normal mode, value `2` produces `*#13**40*2*0##`; a successful
  normal state can produce the expected `4*0`. Running recovery produces `1*0`.
  Query 45 merely checks that kernel status is nonzero: it ACKs even a failed
  check and is not an integrity alternative.
- `classe100x/updater.py` already requires a verified normal reboot and state 4
  after writing recovery and before clearing the main kernel. In the ordinary
  stock non-NFS boot path this therefore gates the transition on the newly booted
  daemon's recovery-kernel check. This behavior is established from code, not from
  an actual flash or a deliberately corrupted-device experiment.

Coverage is **only `uImage` self-consistency**. No stock-pinned hash comparison,
DTB validation, recovery-rootfs scan or filesystem consistency check occurs in
that routine. Query 40 exposes status, not the stored CRC or installed bytes.
It reads cached status rather than rechecking storage on each query. NFS and
already-running-recovery paths can mark kernel status good without this read;
the interpretation above is specifically the normal non-NFS path.

### Other candidates do not provide the missing readback

- Query 44 reads `/MTD_KERNEL_RECOVERY_OK` and `/MTD_FS_RECOVERY_OK`, then takes
  the ACK/reboot path. It does not compute their contents. A literal scan of the
  stock main image found each filename only in `bt_device`; no producer was
  established. The FS status helpers in `libcommon`/`libopen` are flag accessors,
  not evidence of a filesystem checksum producer. Query 44 remains excluded.
- Configuration export `#31` copies `conf.zip` from
  `/home/bticino/cfg/extra/conf/conf.img`; extra export `#39` archives the selected
  extra beneath `/home/bticino/cfg/extra`. Their checksum queries 32/35 cover
  those staged exports, not recovery partitions (`bt_device.c`, around
  5676–5738, 6592–6647 and 6807–6840).
- Stock FTP chroots local accounts; the firmware accounts' home is the staging
  directory `/var/tmp/ftp`. Its normal file retrieval is not a raw-partition
  readback facility. Stock runlevel-5 startup does not establish a usable SSH or
  telnet inspection service. The Dropbear startup in `bt-networking.sh` is a
  runlevel-4 path, not proof of ordinary stock USB shell access.
- Public searches found no demonstrated C100X 1.5.8 stock USB partition-readback
  procedure. The [USB backup question in upstream issue 31](https://github.com/fquinto/bticinoClasse300x/issues/31#issuecomment-2505409654)
  concerns 2.x hardware and supplies no validated answer for this profile.

These findings do not establish that every possible diagnostic interface is
absent. They establish no evidenced stock USB mechanism suitable for adding the
proposed rootfs/DTB readback gate to the current flasher.

### Optional SSH readback gate

`--verify-recovery-ssh` uses an already-enabled administrative SSH service over
managed USB. Its preflight requires UID 0, normal `RUNNING_FW_COPY=1`, fixed p2/p3
block devices and expected sizes, matching sysfs/device-node major/minor numbers,
empty sysfs holders and no matching mountinfo major/minor entries. Those checks
are repeated around acquisitions and at the end; snapshots cannot rule out a
transient concurrent mount/raw writer. This is intended for the trusted supported
installation, not arbitrary Linux storage configurations.

After the existing verified normal reboot, the gate reads p2/p3 using bounded
`dd` and compares each exact-length stream with independent device-side
`sha256sum` output. It runs host `e2fsck -f -n`, compares p3's reference-defined
153600000-byte filesystem extent with the staged stock recovery gzip, and uses
read-only `debugfs` to compare p2's complete 21-file kernel/DTB set with the staged
kernel ZIP. The unwritten p3 partition tail is excluded from stock equality, but
included in acquisition integrity. Local image hashes must remain unchanged.

No SSH command mounts, repairs or writes a device partition. A passed report must
be saved before normal-kernel invalidation. The command connection is refreshed
and state 4 rechecked after SSH preflight and verification: stock `openserver`
arms a 30-second idle timeout, shorter than a full readback (local decompilation
`openserver.c`, around lines 5618–5620). Missing prerequisites, failed reads,
mismatches, timeout, cancellation or report-save failure stop that transition;
there is no unchecked fallback or transfer retry. First-seen/changed host keys
warn rather than block, so this does not establish cryptographic identity
continuity. Readback does not establish uncached physical-media verification or
recovery boot/USB operation. See [ADR-012](DECISIONS.md#adr-012-optional-ssh-recovery-integrity-gate).

## 2026-10-28: Builder package and SSH evidence (offline)

The downloaded manufacturer `C100X_010508.fwz` was 106240356 bytes and matched
the existing stock SHA-256 pin. The local original was inspected without mounting
its filesystem. Its four entries use traditional encryption and DEFLATE; flags
are 1, extraction-version low byte 20 and upper byte 3. The selected legacy
modified image uses flags 3 and version upper byte 0. New 7zip output uses flags
1 and upper byte 0. All accepted variants require matching local/central header
fields and intact CRCs. Output verification rejects Zip64, AES and descriptors.

Stock preserved-component hashes:

| Decoded archive member | SHA-256 |
| --- | --- |
| `fwz.xml` | `f2f78c7a45546800f1d1148e3229b39365c417b9a758b80c57dfa807697e8fb5` |
| `btweb_only_recovery.ext4.gz` | `00840dd0d6e326e8cc25033037a24889ef9cfad13795e83a495b355e1d69cce3` |
| `uImage.zip` | `b06b75e3a956fb26578788293db449f5f188b0502a70cd24f91719ad1dffda3d` |

The stock main filesystem expands to 1073741824 bytes. Its superblock has
262144 blocks of 4096 bytes, 262144 inodes, inode size 256, and feature masks
compat=60, incompat=578, read-only-compat=123. `e2fsck 1.47.4 -f -n` returned 0.
The main rootfs SHA-256 is
`80f04c61a9a34032e397d1dc6a1209ad029162a59d08981d7fd9f81348264354`.
The initial no-op round trip preserved those complete decompressed bytes.

Read-only stock-file inspection confirmed:

- `/etc/inittab` selects runlevel 5. `/etc/rc5.d/S98dropbear` is initially absent.
- `/usr/sbin/dropbear` is a symlink to `./dropbearmulti`. The binary contains
  `ecdsa-sha2-nistp256`; this is capability evidence, not a successful login test.
- `/etc/init.d/dropbear` sources `/etc/default/dropbear`, passes `DROPBEAR_RSAKEY`
  to generic `-r`, and only generates an RSA key when that configured file does
  not exist. The default read-only-rootfs key path is volatile. The factory-key
  copy is conditional on runlevel 4, not the normal runlevel 5.
- `/etc/default/dropbear` initially sets `DROPBEAR_EXTRA_ARGS="-B"`.
- `/home/root` is root-owned 0700; `.ssh` is absent. `/etc/dropbear` initially has
  UID/GID 1000:1000 and mode 0775. The SSH payload intentionally changes that
  directory to root-owned 0700 and shadow to 0600.
- Stock shadow hashes use SHA-512 crypt (`$6$`). Values were not logged or tracked.

The payload's guarded input hashes are in `payloads/ssh/common.py`; proprietary
file contents remain local. Original account entries are preserved, including
vendor-specific duplicate passwd entries. The bundled payload appends `root2`
and enables the existing init script, rather than replacing the daemon.

Upstream references used as supporting evidence:

- `jorgeavlobo/intercom-firmware-tool` revision
  `97ce7e9b95acc3a337a3d6657b023314e15882db`, `FirmwareRegistry.cs`,
  `Ext4Probe.cs` and the C100X 1.5.8 verification record.
- Dropbear tag `DROPBEAR_2017.75`, `svr-runopts.c` (`-s` disables password login;
  `-B` permits blank passwords), `svr-auth.c`, `svr-authpubkey.c` and `signkey.c`.
- Its 2020.79 changelog introduces Ed25519 and RSA-SHA2 support; do not attribute
  those capabilities to the stock 2017.75 daemon.

None of this changes the device update command sequence or establishes a hardware
flash, SSH-authentication or MyHOME-import result. See ACCEPTANCE.md for observed
local builds and pending hardware checks.
