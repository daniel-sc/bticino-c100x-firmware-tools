# C100X boot fallback and rescue investigation

**2026-10-29 — read-only investigation of the existing modified C100X 1.5.8,
hardware `02*06*0`, SHARK Dig-2/Car-6.**

The installed boot environment establishes a normal-to-recovery fallback for
kernel/image-check or device-tree-load failures. It does **not** establish an
automatic rollback after Linux starts and then fails. A usable rescue path when
both firmware environments are unusable remains **unvalidated**.

No firmware write, environment change, reboot, recovery boot, serial-console
interaction or ROM download was performed. SSH was used only for research reads;
the supported stock-device update workflow still does not require SSH.

## Evidence acquired

- Read the actual device's `fw_printenv`, `/etc/fw_env.config`, storage layout,
  CPU/device-tree identity, kernel command line and boot messages.
- Read 4 KiB of the environment from `/dev/mmcblk2p1`. Its CRC32 is valid and
  its entries match `fw_printenv`, which emitted no fallback warning.
- Privately copied both 4 MiB eMMC boot regions and the first 1 MiB of the
  user area. Each local reread hash matched the received bytes and an independent
  device-side read/hash. The boot0 region contains a U-Boot image; boot1 was all
  zero bytes. Two exposed boot regions therefore do not establish two working
  bootloader copies.
- The boot0 image's i.MX IVT boot-data structure describes a 241664-byte image
  at `0x177ff000`, with entry point `0x17800000`. Its banner identifies U-Boot
  2015.04, vendor revision `29803fd92239f5ba26f408a57fbd8bc6f29e2b1f`, built
  2019-07-23. The environment's `ubootver` agrees with that revision.
- The device identifies as i.MX6DL, silicon revision 1.3; its Linux console is
  `ttymxc2,115200n8`.
- Read the running flattened device tree. Linux `serial2` resolves to UART3 at
  `/soc/aips-bus@02100000/serial@021ec000`, enabled with the `uart3grp` pinctrl.
- Completed targeted offline Ghidra analysis of the captured bootloader after an
  earlier interrupted attempt. Kernel checks, keyed boot interruption and the
  command-interpreter path are supported by actual binary control flow, not only
  by strings or an upstream U-Boot implementation.

Private acquisition files and manifests are under
`.local/boot-research-20261029T132507Z/`. They may contain device-specific data and
must stay outside Git. These small region copies supplement the older main/data
backups; they are **not a full-device backup or a tested restore image**.

## Installed boot selection

The following is a paraphrase of the CRC-verified environment, not commands to
execute:

```text
bootcmd:
  update version metadata; select board device-tree filename
  if FORCE_RECOVERY exists:
    test recovery
  otherwise:
    test normal
    if normal did not pass: test recovery
  boot the selected environment

test normal:
  load uImage from U-Boot mmc 0:5
  require iminfo success
  load the board DTB from mmc 0:5
  only then set operative_boot_flag

test recovery:
  load uImage from U-Boot mmc 0:2
  require iminfo success
  load the board DTB from mmc 0:2
  only then set recovery_boot_flag

boot selection:
  normal flag present -> boot kernel + DTB, Linux root mmcblk2p6
  otherwise recovery flag present -> boot kernel + DTB, Linux root mmcblk2p3
  neither flag present -> no Linux boot command in this script
```

Neither selection flag nor `FORCE_RECOVERY` was present in the saved environment.
The configured boot delay is one second and stdin/stdout/stderr are serial.
U-Boot MMC numbering and Linux block-device numbering are different here.

`iminfo` checks the loaded kernel image, not its root filesystem. The captured
binary's image-check function verifies legacy-image magic, header CRC and data
CRC, returning failure for a bad check. The explicit data check is not conditional
on the environment's `verify=n`. This agrees with
[upstream U-Boot 2015.04](https://github.com/u-boot/u-boot/blob/v2015.04/common/cmd_bootm.c),
but is now supported by the device's own binary too.

### Static binary evidence

The analyzed boot0 region has SHA-256
`35d51fbd793d3b2e1ed4c78692058e92e6859b316995ef29bc93f7df7778cd4f`.
Addresses below use the IVT-derived image base `0x177ff000`; they are references
for offline analysis, not device memory-access instructions.

| Address | Observed role |
| --- | --- |
| `0x17806a90` | Image checks: legacy magic, header checksum, data checksum; failed checks return failure. |
| `0x178117f8` | Header-check helper: copy 64-byte header, zero its checksum field, compute and compare checksum. |
| `0x17811848` | Data-check helper: checksum the payload length from the image header and compare its stored checksum. |
| `0x17806158` | Keyed autoboot handling: environment stop/delay strings, compiled fallback stop string, timed serial input comparison, command execution on timeout. |
| `0x17803b80` | Startup loop calls autoboot handling and then the shell/parser path if autoboot returns. |
| `0x17805fe8` | Entry into the shell/parser path after autoboot. |
| `0x1780c534` | Serial binary-transfer handler shared by the identified `loadb`, `loadx`, `loady` command descriptors. |

Private decompilations are `boot-evidence.c` and `boot-details.c` beside the
acquisition files; the Ghidra project is
`research/ghidra/bootloader-awake-20261029`. These support an available software
path toward console rescue, not proof that the board's console can be accessed
or that it remains available indefinitely under all watchdog/failure conditions.

### What the fallback covers

| Failure | What the installed script establishes |
| --- | --- |
| Normal kernel missing, image check fails, or normal DTB cannot be loaded | Recovery is tested next. |
| Recovery kernel/DTB also fails its checks | Neither normal nor recovery is booted by this script; the analyzed startup code has a shell/parser path after autoboot returns. |
| Kernel passes checks but Linux cannot mount its rootfs | No rootfs-health test or late fallback appears in this script. |
| Linux boots but application/network startup hangs | No application-health rollback appears in this script. |
| `bootm` itself fails after the normal flag was set | The normal branch does not then test recovery. |

No `bootcount`, `bootlimit` or `altbootcmd` variable was present. This is evidence
about the inspected environment, not a proof that every vendor hardware/watchdog
path has been characterized. A reset alone does not establish a change of boot
selection; it may repeat the same failure.

### Preserve the current environment

The captured bootloader contains embedded default-environment text whose recovery
test loads its kernel from `0:2` but its **DTB from `0:5`**. The valid saved
environment instead loads both from `0:2`. Embedded and saved `bootcmd` text also
differ. Do not treat resetting U-Boot defaults as a demonstrated repair: it could
reintroduce a dependency on the main kernel partition that the update deliberately
clears. Preserve and analyze the valid environment before proposing any changes.

## Rescue paths and their current limits

### 1. Linux/update services still work: vendor USB update

This is the best-supported route. In public issue
[#62](https://github.com/fquinto/bticinoClasse300x/issues/62), an owner reports
recovering a C100X 16E **1.5.8** update with **MyHOME Suite 3.5.38** after Windows
misbound the USB network function to a serial-port driver. Correcting the RNDIS
binding, including after a mid-update re-enumeration, allowed the update to finish.

This supports recovery from a **host-driver/connectivity failure while device
update services remain usable**. The issue's phrase "bootloader/recovery mode"
does not prove U-Boot itself implements the OpenWebNet/FTP updater. Black screen,
blinking buttons or a Windows COM-port classification do not identify the boot
stage reliably.

The original reporter in
[#51](https://github.com/fquinto/bticinoClasse300x/issues/51) still reported failed
connections after trying the suggested driver fix. These anecdotes are neither a
universal recovery guarantee nor data for calculating a failure probability.

For a future failed update:

1. Preserve the last updater stage/error and stable device power. A host timeout
   does not prove the device has stopped writing.
2. Once device state is assessed, inspect USB enumeration and the host's driver/
   routing state. `1da4:0056` with network interface `MI_00` is the reported
   Windows driver case, not a ROM-download identifier.
3. Establish read-only identity/status before choosing another write operation.
   The current native `flash` command requires normal state 4 at entry; it is
   **not** a recovery-state resume command. Do not bypass that check.
4. If the vendor tool can communicate with the matching device in its actual
   state, the established MyHOME workflow is the candidate repair route. The
   linked driver script is third-party material, not a locally validated tool.

Repeated power cycling, driver restarts or firmware retries during an uncertain
write are not a recovery procedure. The power-cycle anecdotes in issue #51 do
not change the project's stop-on-uncertainty policy.

### 2. U-Boot works, but Linux does not: serial-console rescue candidate

There is concrete evidence worth pursuing:

- Stock main and recovery `/etc/inittab` configure a Linux getty on `ttymxc2` at
  115200 baud. The actual boot environment uses that same serial console.
- The boot0 binary has structurally identified command descriptors for serial
  transfers (`loadb`, `loadx`, `loady`), filesystem reads, MMC access and
  environment operations. These are static findings, not executed commands.
- Its boot script has an explicit `FORCE_RECOVERY` branch.
- Decompiled control flow confirms **keyed** interruption, with a compiled stop
  sequence used when `bootstopkey` is absent. The saved environment does not
  override it. Its bytes are preserved privately in `console-stop-sequence.bin`,
  not logged or published. "Press any key" is not this build's mechanism.

The running device tree's UART3 mux values map to SoC pads **EIM_D24 TX** and
**EIM_D25 RX** using the
[NXP i.MX6DL pin definitions](https://github.com/nxp-imx/linux-imx/blob/lf-6.6.y/arch/arm/boot/dts/nxp/imx/imx6dl-pinfunc.h).
This identifies the configured SoC signals, **not physical PCB pads or connector
pins**. Neither the board's logic voltage nor a usable external connection has
been established. The DTB is private as `running-device-tree.dtb` with its
acquisition size/hash in `device-tree-acquisition.json`.

This suggests two different possibilities: select an intact on-device recovery
environment, or load board-matched boot material into RAM through the console.
Neither has been exercised. If **both root filesystems** are unusable, loading a
kernel/DTB alone is insufficient: a working rescue rootfs/initramfs and a validated
repair workflow are also required.

Missing prerequisites: C100X Dig-2/Car-6 PCB UART pad identification, measured logic
voltage, accessible boot output and prompt, hardware verification of keyed interruption,
appropriate rescue images and a successful controlled rescue on spare hardware.
The Linux getty configuration is not a board pinout or proof of bootloader access.
No speculative wiring, environment-write or raw-partition-write recipe is given.

### 3. Bootloader unavailable: i.MX ROM-download candidate

NXP documents i.MX serial-download recovery and tools such as
[UUU](https://github.com/nxp-imx/mfgtools/wiki) and
[imx_usb_loader](https://github.com/boundarydevices/imx_usb_loader).
The actual i.MX6DL identification makes this a relevant research direction.

However, the ROM loads the bootloader before Linux. A valid bootloader followed
by broken Linux does **not** itself establish automatic entry into ROM recovery.
Board boot straps, accessible USB/UART routing, fuse/security configuration and
correct SHARK-specific RAM initialization/images still need evidence.

The publicly documented
[BTicino Mamoj USB/DFU procedure](https://github.com/u-boot/u-boot/blob/master/board/bticino/mamoj/README)
is for another board. Its images, memory assumptions, pin settings and partition
commands must not be applied to SHARK on the strength of manufacturer/CPU family
similarity. No C100X-specific ROM or JTAG rescue has been established here.

## Next evidence needed

Internal UART/board-level work was subsequently excluded from the user's current
scope. The items below describe what would be needed to close the deeper rescue
gap, rather than authorized next device operations. The in-scope read-only
integrity baseline is recorded below.

1. Identify the UART on this exact board revision from board documentation or
   competent physical inspection and voltage measurements.
2. On a separately planned hardware session, capture a normal boot and establish
   console access without changing persistent state. A reboot is still an
   interruption to the household intercom and was not part of this investigation.
3. Establish a board-matched RAM-boot rescue environment and vendor repair path
   on spare hardware, without deliberately interrupting an actual flash.
4. Obtain the exact vendor bootloader source/configuration if available. The
   stock C100X `/home/bticino/cfg/README` offers corresponding GPL/LGPL source
   through BTicino's contacts. The advertised vendor commit was not found in the
   checked public `bticino/uboot-imx` or `nxp-imx/uboot-imx` repositories.

The first remaining blocker is physical board-level console access. Another
ordinary SSH read or synthetic test cannot establish that access or demonstrate
a rescue when both Linux environments are unavailable.

**Risk conclusion:** normal-to-recovery boot selection is now grounded in this
unit's actual settings, and one real-world USB-driver rescue is documented.
Recovery from loss of both Linux environments is technically plausible but is
still not an established household fallback. No percentage risk of permanent
loss or guarantee of repair follows from these findings.

## Installed-component integrity baseline — 2026-10-29

Read-only acquisition of the unmounted recovery kernel (`p2`), recovery rootfs
(`p3`) and normal kernel (`p5`) passed independent device/local SHA-256 comparison.
Both kernel partitions contain all **21 stock kernel/DTB files byte-for-byte**,
with no unexpected root entries. All three partition images and the stock
recovery rootfs passed offline `e2fsck -f -n` with exit 0.

The installed recovery filesystem differs from stock by 18384 byte positions
across 103 1-KiB blocks. All differences were localized to filesystem metadata,
journal contents and two new volatile-directory symlinks consistent with the
stock startup script. Existing regular-file contents are unchanged. Its
153600000-byte filesystem extent was compared separately from the remaining
3686400 bytes of partition space.

This is positive evidence about the present components' integrity. It is **not**
a successful recovery boot, recovery USB test or guarantee about the copy written
by a future flash. Detailed results are in
[ACCEPTANCE.md](ACCEPTANCE.md#2026-10-29-installed-kernel-and-recovery-integrity--read-only);
private acquisition and analysis artifacts are under
`.local/recovery-integrity-20261029T204358Z/`.

## Stock USB verification search — 2026-10-29

Offline stock-binary analysis found a **partial safeguard already used by the
flasher**: on normal non-NFS startup, `bt_daemon` verifies the installed recovery
`uImage` magic and header/data CRCs. Query 40 reflects that cached result. The
existing sequence requires normal state 4 after rewriting recovery and rebooting,
before clearing the main kernel, so it already checks more than worker completion.

This corrects the earlier interpretation that this boundary checked only normal
identity/status with no installed recovery integrity evidence. Its coverage is
still limited: **no recovery-rootfs, DTB or filesystem-health verification** was
found. Query 44's checksum-looking filenames do not establish such a mechanism,
and that query also reboots. Configuration/extra FTP exports do not export
firmware partitions. No suitable stock USB full-readback facility was established.

The evidence, status values and boot-path limitations are detailed in
[PROTOCOL.md](PROTOCOL.md#2026-10-29-stock-usb-accessible-recovery-verification-offline-research).
This investigation used public sources and local stock artifacts only; no new
device command, reboot or flash was performed.
