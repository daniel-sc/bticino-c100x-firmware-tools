# Researched C100X 1.5.8 update protocol

## Evidence and scope

The implementation follows the Classe 100 X16E profile in MyHOME Suite 3.5.38,
cross-checked against stock device binaries and scripts. Decompiled source paths
below refer to local research artifacts, not distributed vendor source.

1. Installer member
   `default/resTargetDir4/devices/2266_1.5_BT/xml/Protocol/protocol.xml` identifies
   device `344682`, model `1.0.99`, provider `BTESUProtocolXPProvider` and
   `watershedVer=always`. `classe100x/vendor.py` reads this member in memory.
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
stock password hashes. Values are not included in source, documents or logs.

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
  and SSH acceptance checks. No installed-filesystem readback is available here.

Deliberate fault injection is restricted to simulation.
