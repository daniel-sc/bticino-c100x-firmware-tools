"""Optional, read-only SSH gate before sacrificing the normal boot path.

Only this opt-in module needs e2fsprogs. References come from PreparedFirmware;
there are no device mounts, repairs, write retries or restore operations here.
"""

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import zipfile

from .firmware import FirmwareError, geometry
from .host import find_tool, run_tool
from .ssh import SSHError
from .updater import UpdateError

PARTITIONS = {"mmcblk2p2": 50 * 1024**2, "mmcblk2p3": 150 * 1024**2}
ROOTFS_BYTES = 153600000
FREE_BYTES = 512 * 1024**2


class VerificationError(UpdateError):
    pass


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise VerificationError("Recovery verification exceeded its time limit")
    return seconds


def digest(path, *, length=None, deadline=None):
    value = hashlib.sha256()
    with path.open("rb") as source:
        while length is None or length > 0:
            if deadline is not None:
                remaining(deadline)
            chunk = source.read(1024**2 if length is None else min(length, 1024**2))
            if not chunk:
                if length:
                    raise VerificationError("Truncated recovery image")
                break
            value.update(chunk)
            if length is not None:
                length -= len(chunk)
    return value.hexdigest()


def inspection_command():
    # Constant shell program: never interpolate user input or filesystem paths.
    return """set -eu
test "$(id -u)" = 0
test "$(cat /var/tmp/flags/RUNNING_FW_COPY)" = 1
command -v dd >/dev/null
command -v sha256sum >/dev/null
for p in mmcblk2p2 mmcblk2p3; do
    test -b /dev/$p
    test -r /dev/$p
    test -z "$(ls -A /sys/class/block/$p/holders)"
    echo PARTITION:$p
    cat /sys/class/block/$p/size
    cat /sys/class/block/$p/dev
    stat -L -c '%t:%T' /dev/$p
    cat /sys/class/block/$p/partition
done
echo MOUNTS
cat /proc/self/mountinfo
"""


def parse_inspection(data):
    """Check block-device aliases by major/minor, not mount-source spelling."""
    try:
        lines = data.decode("ascii").splitlines()
        devices = {}
        for index, (name, size) in enumerate(PARTITIONS.items()):
            label, sectors, dev, node, number = lines[index * 5:index * 5 + 5]
            major, minor = map(int, dev.split(":"))
            node_major, node_minor = (int(part, 16) for part in node.split(":"))
            if (label != f"PARTITION:{name}" or int(sectors) * 512 != size
                    or (major, minor) != (node_major, node_minor)
                    or int(number) != int(name[-1]) or major < 0 or minor < 0):
                raise ValueError
            devices[name] = {"device": f"{major}:{minor}", "bytes": size}
        if lines[10] != "MOUNTS" or not lines[11:]:
            raise ValueError
        mounted = set()
        for line in lines[11:]:
            fields = line.split()
            if len(fields) < 10 or "-" not in fields or not re.fullmatch(r"\d+:\d+", fields[2]):
                raise ValueError
            mounted.add(fields[2])
        numbers = {item["device"] for item in devices.values()}
        if len(numbers) != len(devices):
            raise ValueError
        if numbers & mounted:
            raise VerificationError("A recovery partition is mounted; verification stopped")
        return devices
    except (UnicodeError, ValueError, IndexError):
        raise VerificationError("Recovery partition identity or size could not be verified") from None


class RecoveryVerifier:
    def __init__(self, firmware, ssh, *, progress=print, parent=None):
        self.firmware, self.ssh, self.progress = firmware, ssh, progress
        self.parent = Path.cwd() if parent is None else Path(parent)
        self.directory = None
        self.workspace = None
        self.deadline = None
        self.tools = {}
        self.record = {
            "profile": "c100x-1.5.8", "firmware_sha256": firmware.sha256,
            "preflight": "not_started", "verification": "not_started",
            "update_sequence": "not_started", "functional_acceptance": "not_performed",
            "stage": "setup", "host_key_policy": "warn_only",
            "cryptographic_identity_continuity_required": False,
            "partitions": {}, "raw_copies": "temporary",
        }

    def __enter__(self):
        try:
            self.ssh.__enter__()
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            self.directory = Path(tempfile.mkdtemp(prefix=f"c100x-verification-{stamp}-", dir=self.parent)).resolve()
            self._private(self.directory, directory=True)
            self.workspace = self.directory / "raw"
            self.workspace.mkdir(mode=0o700)
            self._private(self.workspace, directory=True)
            self.progress(f"Recovery verification evidence: {self.directory}")
            self._save()
            return self
        except BaseException:
            self.ssh.close()
            raise

    def _private(self, path, *, directory=False):
        os.chmod(path, 0o700 if directory else 0o600)
        if os.geteuid() == 0:
            os.chown(path, self.ssh.uid, self.ssh.gid)

    def _save(self):
        self.record["host_keys"] = list(self.ssh.host_keys)
        self.record["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        fd, name = tempfile.mkstemp(prefix=".report-", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w") as output:
                json.dump(self.record, output, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            self._private(temporary)
            temporary.replace(self.directory / "report.json")
        finally:
            temporary.unlink(missing_ok=True)

    def _stage(self, text):
        self.record["stage"] = text
        self.progress(f"Recovery verification: {text}")

    def _inspect(self, timeout=30):
        return parse_inspection(self.ssh.run(inspection_command(), timeout=timeout))

    def _space(self):
        if shutil.disk_usage(self.workspace).free < FREE_BYTES:
            raise VerificationError("Recovery verification needs at least 512 MiB of free host storage")

    def _references(self):
        size, reference = 0, hashlib.sha256()
        with gzip.open(self.firmware.directory / "btweb_only_recovery.ext4.gz", "rb") as source:
            header = source.read(2048)
            self.root_geometry = geometry(header)
            reference.update(header)
            size += len(header)
            while chunk := source.read(1024**2):
                size += len(chunk)
                if size > ROOTFS_BYTES:
                    raise VerificationError("Unexpected stock recovery filesystem size")
                reference.update(chunk)
        if size != ROOTFS_BYTES or self.root_geometry[1] * (1024 << self.root_geometry[3]) != size:
            raise VerificationError("Unexpected stock recovery filesystem geometry")
        self.root_sha256 = reference.hexdigest()
        self.kernel_files = {}
        with zipfile.ZipFile(self.firmware.directory / "uImage.zip") as archive:
            for entry in archive.infolist():
                if (not re.fullmatch(r"[A-Za-z0-9_.-]+", entry.filename)
                        or entry.filename in (".", "..") or entry.is_dir()
                        or entry.file_size > 16 * 1024**2 or entry.filename in self.kernel_files):
                    raise VerificationError("Unexpected stock kernel archive entry")
                self.kernel_files[entry.filename] = {
                    "bytes": entry.file_size,
                    "sha256": hashlib.sha256(archive.read(entry)).hexdigest(),
                }
        if len(self.kernel_files) != 21 or "uImage" not in self.kernel_files:
            raise VerificationError("Unexpected stock kernel/DTB file set")
        self.record["reference"] = {"rootfs_bytes": size, "rootfs_sha256": self.root_sha256,
                                    "kernel_files": self.kernel_files}

    def preflight(self):
        self._stage("preflight")
        try:
            self._space()
            self.tools = {name: find_tool(name) for name in ("debugfs", "e2fsck")}
            for name, option in (("debugfs", "-V"), ("e2fsck", "-V")):
                status, _, _ = run_tool([self.tools[name], option], timeout=10)
                if status:
                    raise VerificationError(f"Recovery verification tool could not start: {name}")
            self._references()
            self.initial_devices = self._inspect()
            self.record["preflight"] = "passed"
            self._save()
        except (SSHError, FirmwareError, OSError, ValueError, EOFError, zipfile.BadZipFile) as exc:
            raise VerificationError("Recovery verification preflight failed; check SSH access, tools and storage") from exc

    def update_result(self, status, stage):
        self.record["update_sequence"] = status
        self.record["update_stage"] = stage
        self._save()

    def _check_devices(self):
        devices = self._inspect(timeout=min(30, remaining(self.deadline)))
        if devices != self.initial_devices:
            raise VerificationError("Recovery partition identity changed after preflight")

    def _tool(self, arguments, *, cwd=None):
        status, out, err = run_tool(arguments, cwd=cwd, timeout=remaining(self.deadline), limit=256 * 1024)
        if status:
            raise VerificationError("Offline recovery filesystem tool failed; no repair was attempted")
        return out, err

    def _debugfs(self, image, command, *, cwd=None):
        out, err = self._tool([self.tools["debugfs"], "-R", command, str(image)], cwd=cwd)
        if any(not re.fullmatch(r"debugfs \d+\.\d+(?:\.\d+)? \([^\r\n]+\)", line)
               for line in err.decode(errors="replace").splitlines() if line.strip()):
            raise VerificationError("Offline recovery file inspection failed")
        return out

    def _kernel(self, image):
        listing = self._debugfs(image, "ls -p /").decode("ascii").splitlines()
        entries = {}
        for line in listing:
            if not line:
                continue
            fields = line.split("/")
            if len(fields) != 8 or not fields[1].isdigit():
                raise VerificationError("Invalid recovery kernel directory listing")
            name = fields[5]
            if name in (".", ".."):
                continue
            if name in entries or not re.fullmatch(r"100[0-7]{3}", fields[2]):
                raise VerificationError("Unexpected recovery kernel file type or duplicate")
            entries[name] = int(fields[6])
        if entries != {name: item["bytes"] for name, item in self.kernel_files.items()}:
            raise VerificationError("Installed recovery kernel/DTB file set or lengths differ from stock")
        for name, reference in self.kernel_files.items():
            # Fixed simple destination under cwd avoids debugfs quoting ambiguity
            # in the user's working directory. No device filenames are executed.
            destination = self.workspace / "kernel-file"
            self._debugfs(image, f"dump /{name} kernel-file", cwd=self.workspace)
            try:
                if (not destination.is_file() or destination.is_symlink()
                        or destination.stat().st_size != reference["bytes"]
                        or digest(destination, deadline=self.deadline) != reference["sha256"]):
                    raise VerificationError("Installed recovery kernel/DTB content differs from stock")
            finally:
                destination.unlink(missing_ok=True)
        self.record["kernel_files_match"] = True

    def verify(self):
        if self.record["preflight"] != "passed":
            raise VerificationError("SSH recovery verification requires a successful preflight")
        self.record["verification"] = "in_progress"
        self._stage("waiting for SSH after normal reboot")
        self._save()
        ready_deadline = time.monotonic() + 120
        try:
            while True:
                try:
                    self.ssh.run("true", timeout=min(10, remaining(ready_deadline)))
                    break
                except SSHError:
                    time.sleep(min(2, remaining(ready_deadline)))
            self.deadline = time.monotonic() + 900
            self._space()
            for name, size in PARTITIONS.items():
                self._stage(f"reading {name}")
                self._check_devices()
                image = self.workspace / f"{name}.img"
                self.ssh.run(f"dd if=/dev/{name} bs=1048576 count={size // 1024**2}",
                             timeout=remaining(self.deadline), output=image, expected_size=size)
                self._private(image)
                actual = digest(image, deadline=self.deadline)
                self._stage(f"independently hashing {name}")
                remote = self.ssh.run(f"sha256sum /dev/{name}", timeout=remaining(self.deadline))
                if not re.fullmatch(rb"[0-9a-f]{64}  /dev/" + name.encode() + rb"\n", remote):
                    raise VerificationError("Invalid independent recovery readback checksum")
                if remote[:64].decode() != actual:
                    raise VerificationError("Recovery acquisition and independent device checksum differ")
                self._check_devices()
                self.record["partitions"][name] = {"bytes": size, "sha256": actual,
                    "independent_read_matches": True, "unmounted_before_and_after": True}
                self._stage(f"checking {name} filesystem")
                self._tool([self.tools["e2fsck"], "-f", "-n", str(image)])
                self.record["partitions"][name]["filesystem_check"] = "passed"
                if name == "mmcblk2p3":
                    with image.open("rb") as source:
                        if geometry(source.read(2048)) != self.root_geometry:
                            raise VerificationError("Installed recovery filesystem geometry differs from stock")
                    if digest(image, length=ROOTFS_BYTES, deadline=self.deadline) != self.root_sha256:
                        raise VerificationError("Installed recovery filesystem bytes differ from stock")
                    self.record["rootfs_matches"] = True
                else:
                    self._kernel(image)
                if digest(image, deadline=self.deadline) != actual:
                    raise VerificationError("Recovery acquisition changed during offline inspection")
            self._check_devices()
            remaining(self.deadline)
            self.record["verification"] = "passed"
            self._stage("passed; saving evidence before main-kernel clear")
            self._save()  # A publication failure must block the destructive transition.
        except (SSHError, FirmwareError, OSError, ValueError) as exc:
            raise VerificationError("Recovery readback could not be verified; main kernel was not cleared") from exc
        finally:
            # The verifier has no SSH responsibilities during the main update.
            self.ssh.close()

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            self.record["failure_type"] = exc_type.__name__
            if self.record["preflight"] != "passed":
                self.record["preflight"] = "failed"
            if self.record["verification"] == "in_progress":
                self.record["verification"] = "failed"
        try:
            if self.workspace is not None:
                shutil.rmtree(self.workspace)
                self.record["raw_copies"] = "removed"
            self._save()
        except OSError:
            self.progress("Warning: evidence cleanup/publication failed; inspect the private evidence directory")
            if exc_type is None:
                raise VerificationError("Recovery evidence cleanup/publication failed") from None
        finally:
            self.ssh.close()
