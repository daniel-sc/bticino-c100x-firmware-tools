"""Validate and stage the two researched C100X 1.5.8 archives unchanged."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import gzip
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

SELECTED_SHA256 = "67848425d6ec5a251ff8362394dad052737f42eb8326cdc8333038d7ede22abc"
STOCK_SHA256 = "bca0dd7e407c2406d6f8c696f0a9e50bc1e795c8e4700c89e83f09ff96c3efb2"
MAIN_FILES = ("btweb_only.ext4.gz", "uImage.zip")
RECOVERY_FILES = ("btweb_only_recovery.ext4.gz", "uImage.zip")
MEMBERS = {"fwz.xml", *MAIN_FILES, *RECOVERY_FILES}


class FirmwareError(Exception):
    """The input cannot be used by the researched update workflow."""


@dataclass(frozen=True)
class Payload:
    name: str
    size: int
    sha256: str
    cksum: int


@dataclass(frozen=True)
class PreparedFirmware:
    directory: Path
    sha256: str
    payloads: tuple[Payload, ...]

    def payload(self, name: str) -> Payload:
        return next(item for item in self.payloads if item.name == name)

    def report(self) -> dict:
        return {
            "sha256": self.sha256,
            "model": "C100X",
            "version": "1.5.8",
            "object_model": "1.0.99",
            "payloads": [asdict(item) for item in self.payloads],
        }


def posix_cksum(path: Path) -> int:
    # macOS cksum defaults to the POSIX polynomial with the length folded in.
    # ZIP/zlib CRC32 is a different checksum and cannot be used for dimension 35.
    result = subprocess.run(
        ["/usr/bin/cksum", str(path.resolve())], capture_output=True, check=True, text=True,
    )
    crc, length, *_ = result.stdout.split()
    if int(length) != path.stat().st_size or not 0 <= int(crc) <= 0xFFFFFFFF:
        raise FirmwareError("Unable to calculate payload checksum")
    return int(crc)


def validate_manifest(data: bytes) -> None:
    if len(data) > 65536 or b"<!" in data:
        raise FirmwareError("Unsupported firmware manifest")
    try:
        root = ET.fromstring(data)
        if root.tag != "fwz" or any(root.findtext(tag) != value for tag, value in (
            ("name", "C100X"), ("fwz_ver", "1.5.8"), ("xml_ver", "3.0"),
        )):
            raise FirmwareError("Expected a C100X 1.5.8 version-3 manifest")
        devices = root.findall("device")
        groups = root.findall("actions")
        if len(devices) != 1 or len(groups) != 1:
            raise FirmwareError("Unsupported manifest device/action groups")
        if devices[0].get("act_id") != groups[0].get("id"):
            raise FirmwareError("Manifest action group does not match the device")
        if [n.text for n in devices[0].findall("object_models/object_model")] != ["1.0.99"]:
            raise FirmwareError("Firmware object model does not match C100X")
        for kind, expected in (("firmware", MAIN_FILES), ("recovery_firmware", RECOVERY_FILES)):
            actions = groups[0].findall(f"action[@type='{kind}']")
            if len(actions) != 1 or actions[0].get("provider") != "btesuv3":
                raise FirmwareError("Unsupported firmware action")
            if tuple(n.text for n in actions[0].findall("attr[@type='file']")) != expected:
                raise FirmwareError("Unexpected filesystem/kernel payload ordering")
    except ET.ParseError:
        raise FirmwareError("Malformed firmware manifest") from None


def _validate_payload(path: Path) -> None:
    if path.name.endswith(".gz"):
        with gzip.open(path, "rb") as stream:
            header = stream.read(2048)
            if header[1080:1082] != b"\x53\xef":
                raise FirmwareError("Filesystem payload is not an ext filesystem")
            size = len(header)
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > 2 * 1024**3:
                    raise FirmwareError("Expanded filesystem exceeds the supported limit")
            # Consume through EOF to verify the gzip trailer before any device writes.
            if size < 2048:
                raise FirmwareError("Truncated filesystem payload")
    else:
        with zipfile.ZipFile(path) as kernel:
            files = kernel.infolist()
            if not files or sum(item.file_size for item in files) > 64 * 1024**2:
                raise FirmwareError("Unsupported kernel archive size")
            for item in files:
                if item.filename != Path(item.filename).name or item.is_dir():
                    raise FirmwareError("Unsupported kernel archive member")
            if kernel.testzip() is not None:
                raise FirmwareError("Kernel archive checksum mismatch")


@contextmanager
def prepare_firmware(path: Path, archive_key: bytes, *, temporary_parent: Path | None = None):
    """Yield verified payloads in a private temporary directory, then remove them.

    Pinning the two researched images makes this deliberately unsuitable for
    other releases, arbitrary manifests, or newly generated custom firmware.
    The source descriptor stays open from hashing through archive extraction.
    """
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest not in (SELECTED_SHA256, STOCK_SHA256):
            raise FirmwareError("Archive SHA-256 is not one of the two researched 1.5.8 images")
        source.seek(0)
        with tempfile.TemporaryDirectory(prefix="classe100x-", dir=temporary_parent) as tmp:
            directory = Path(tmp)
            try:
                with zipfile.ZipFile(source) as archive:
                    files = archive.infolist()
                    if len(files) != len(MEMBERS) or {f.filename for f in files} != MEMBERS:
                        raise FirmwareError("Unexpected or duplicate FWZ archive members")
                    if any(f.file_size > 256 * 1024**2 for f in files):
                        raise FirmwareError("Firmware payload exceeds the supported limit")
                    if archive.getinfo("fwz.xml").file_size > 65536:
                        raise FirmwareError("Firmware manifest exceeds the supported limit")
                    validate_manifest(archive.read("fwz.xml", pwd=archive_key))
                    payloads = []
                    for name in dict.fromkeys((*RECOVERY_FILES, *MAIN_FILES)):
                        destination = directory / name
                        with archive.open(name, pwd=archive_key) as src, destination.open("xb") as dst:
                            shutil.copyfileobj(src, dst, 1024 * 1024)
                        _validate_payload(destination)
                        with destination.open("rb") as data:
                            sha256 = hashlib.file_digest(data, "sha256").hexdigest()
                        payloads.append(Payload(name, destination.stat().st_size, sha256, posix_cksum(destination)))
                prepared = PreparedFirmware(directory, digest, tuple(payloads))
            except (RuntimeError, zipfile.BadZipFile, gzip.BadGzipFile, EOFError):
                # Archive-library exceptions can embed input-derived text. Keep
                # credentials and package content out of CLI messages/logs.
                raise FirmwareError("Unable to decrypt or validate firmware payloads") from None
            yield prepared
