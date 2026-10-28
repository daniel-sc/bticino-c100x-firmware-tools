"""Validate and stage the fixed C100X 1.5.8 profile before any device operation."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib

SELECTED_SHA256 = "67848425d6ec5a251ff8362394dad052737f42eb8326cdc8333038d7ede22abc"
STOCK_SHA256 = "bca0dd7e407c2406d6f8c696f0a9e50bc1e795c8e4700c89e83f09ff96c3efb2"
MAIN_FILES = ("btweb_only.ext4.gz", "uImage.zip")
RECOVERY_FILES = ("btweb_only_recovery.ext4.gz", "uImage.zip")
MEMBERS = {"fwz.xml", *MAIN_FILES, *RECOVERY_FILES}
ARCHIVE_KEY = b"C100X"  # Published format password, not a device credential.
PROFILE = "c100x-1.5.8"
PRESERVED_SHA256 = {
    "fwz.xml": "f2f78c7a45546800f1d1148e3229b39365c417b9a758b80c57dfa807697e8fb5",
    "btweb_only_recovery.ext4.gz": "00840dd0d6e326e8cc25033037a24889ef9cfad13795e83a495b355e1d69cce3",
    "uImage.zip": "b06b75e3a956fb26578788293db449f5f188b0502a70cd24f91719ad1dffda3d",
}
MAIN_SIZE = 1073741824
# Stock superblock geometry/features; no implicit resizing or feature conversion.
MAIN_GEOMETRY = (262144, 262144, 0, 2, 32768, 32768, 60, 578, 123, 0, 256)


def regular_file(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise FirmwareError("Expected a regular input file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def geometry(header: bytes) -> tuple:
    if len(header) < 2048 or header[1080:1082] != b"\x53\xef":
        raise FirmwareError("Filesystem payload is not an ext filesystem")
    sb = header[1024:2048]
    return tuple(struct.unpack_from("<I", sb, offset)[0]
                 for offset in (0, 4, 20, 24, 32, 40, 92, 96, 100, 336)) + (struct.unpack_from("<H", sb, 88)[0],)


def check_main_image(path: Path) -> None:
    with regular_file(path) as source:
        if os.fstat(source.fileno()).st_size != MAIN_SIZE or geometry(source.read(2048)) != MAIN_GEOMETRY:
            raise FirmwareError("Main filesystem size, geometry or features differ from the stock profile")


def _check_zip_directory(source) -> None:
    """Bound ZIP directory parsing before zipfile allocates entry objects."""
    source.seek(0, 2)
    size = source.tell()
    source.seek(max(0, size - 65557))
    tail = source.read()
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        raise FirmwareError("Missing classic ZIP directory")
    _, disk, cd_disk, local_count, total_count, cd_size, cd_offset, comment = struct.unpack_from("<4s4H2IH", tail, offset)
    eocd_offset = size - len(tail) + offset
    if (disk or cd_disk or local_count != 4 or total_count != 4 or cd_size > 4096
            or cd_offset + cd_size != eocd_offset or offset + 22 + comment != len(tail)):
        raise FirmwareError("Unsupported, duplicate or excessive FWZ ZIP directory")
    source.seek(0)
    if source.read(4) != b"PK\x03\x04":
        raise FirmwareError("Unsupported FWZ archive prefix")
    source.seek(0)


def _check_local_header(source, member) -> None:
    source.seek(member.header_offset)
    header = source.read(30)
    if len(header) != 30:
        raise FirmwareError("Truncated ZIP local header")
    signature, version, flags, method, _, _, crc, compressed, expanded, name_size, extra_size = struct.unpack("<4s5H3I2H", header)
    if (signature != b"PK\x03\x04" or version != member.extract_version + (member.reserved << 8) or flags != member.flag_bits
            or method != member.compress_type or crc != member.CRC or compressed != member.compress_size
            or expanded != member.file_size or name_size > 128 or extra_size > 4096
            or source.read(name_size) != member.filename.encode("ascii")):
        raise FirmwareError("Inconsistent ZIP local and central headers")


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
        [shutil.which("cksum") or "/usr/bin/cksum", str(path.resolve())],
        capture_output=True, check=True, text=True, timeout=120,
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


def _validate_payload(path: Path, *, profile: bool = False) -> None:
    if path.name.endswith(".gz"):
        with gzip.open(path, "rb") as stream:
            header = stream.read(2048)
            if header[1080:1082] != b"\x53\xef":
                raise FirmwareError("Filesystem payload is not an ext filesystem")
            if profile and path.name == MAIN_FILES[0] and geometry(header) != MAIN_GEOMETRY:
                raise FirmwareError("Main filesystem geometry/features differ from the stock profile")
            size = len(header)
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                limit = MAIN_SIZE if profile and path.name == MAIN_FILES[0] else 2 * 1024**3
                if size > limit:
                    raise FirmwareError("Expanded filesystem exceeds the supported limit")
            # Consume through EOF to verify the gzip trailer before any device writes.
            if size < 2048:
                raise FirmwareError("Truncated filesystem payload")
            if profile and path.name == MAIN_FILES[0] and (size != MAIN_SIZE or geometry(header) != MAIN_GEOMETRY):
                raise FirmwareError("Main filesystem size, geometry or features differ from the stock profile")
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
def prepare_firmware(path: Path, archive_key: bytes = ARCHIVE_KEY, *, temporary_parent: Path | None = None):
    """Yield verified payloads in a private temporary directory, then remove them.

    The main filesystem may vary; the manifest, recovery and kernel must match
    stock. This checks package compatibility/integrity, not filesystem health or
    bootability. The source descriptor stays open throughout inspection.
    """
    with regular_file(path) as source:
        if os.fstat(source.fileno()).st_size > 512 * 1024**2:
            raise FirmwareError("Firmware archive exceeds the supported limit")
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        if not zipfile.is_zipfile(source):
            raise FirmwareError("Archive SHA-256 is unknown and input is not a supported FWZ")
        _check_zip_directory(source)
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
                    for member in files:
                        # Match classic, encrypted DEFLATE ZIP, excluding AES/Zip64/descriptors.
                        if (member.flag_bits not in (1, 3) or member.compress_type != zipfile.ZIP_DEFLATED
                                or member.extract_version != 20 or member.reserved not in (0, 3) or member.is_dir()):
                            raise FirmwareError("Unsupported FWZ encryption or ZIP packaging")
                        if stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG):
                            raise FirmwareError("FWZ members must be regular files")
                        _check_local_header(source, member)
                        extra = member.extra
                        while extra:
                            if len(extra) < 4:
                                raise FirmwareError("Malformed ZIP extra field")
                            kind, length = struct.unpack_from("<HH", extra)
                            if kind in (1, 0x9901) or length > len(extra) - 4:
                                raise FirmwareError("Unsupported ZIP extra field")
                            extra = extra[4 + length:]
                    if archive.getinfo("fwz.xml").file_size > 65536:
                        raise FirmwareError("Firmware manifest exceeds the supported limit")
                    manifest = archive.read("fwz.xml", pwd=archive_key)
                    validate_manifest(manifest)
                    if hashlib.sha256(manifest).hexdigest() != PRESERVED_SHA256["fwz.xml"]:
                        raise FirmwareError("Firmware manifest differs from the stock profile")
                    (directory / "fwz.xml").write_bytes(manifest)
                    payloads = []
                    for name in dict.fromkeys((*RECOVERY_FILES, *MAIN_FILES)):
                        destination = directory / name
                        with archive.open(name, pwd=archive_key) as src, destination.open("xb") as dst:
                            copied = 0
                            while chunk := src.read(1024 * 1024):
                                copied += len(chunk)
                                if copied > 256 * 1024**2:
                                    raise FirmwareError("Firmware member exceeds the supported limit")
                                dst.write(chunk)
                        _validate_payload(destination, profile=True)
                        with destination.open("rb") as data:
                            sha256 = hashlib.file_digest(data, "sha256").hexdigest()
                        if name in PRESERVED_SHA256 and sha256 != PRESERVED_SHA256[name]:
                            raise FirmwareError("Recovery/kernel contents differ from the stock profile")
                        payloads.append(Payload(name, destination.stat().st_size, sha256, posix_cksum(destination)))
                prepared = PreparedFirmware(directory, digest, tuple(payloads))
                source.seek(0)
                if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                    raise FirmwareError("Firmware input changed during validation")
            except (RuntimeError, zipfile.BadZipFile, gzip.BadGzipFile, EOFError, NotImplementedError, zlib.error):
                # Archive-library exceptions can embed input-derived text. Keep
                # credentials and package content out of CLI messages/logs.
                raise FirmwareError("Unable to decrypt or validate firmware payloads") from None
            yield prepared
