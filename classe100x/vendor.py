"""Read the vendor's C100X FTP settings in memory; never export credentials."""

from dataclasses import dataclass, field
import ast
import io
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Credentials:
    username: str = field(repr=False)
    password: str = field(repr=False)


@dataclass(frozen=True)
class VendorProfile:
    normal: Credentials
    recovery: Credentials


def key_from_builder(path: Path) -> bytes:
    """Read the existing legacy builder's literal C100X archive key, without executing it."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        raise ValueError("Unable to parse legacy builder") from None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "PrepareFirmware":
            for statement in node.body:
                if (isinstance(statement, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "password2" for t in statement.targets)
                        and isinstance(statement.value, ast.Constant)
                        and isinstance(statement.value.value, str)):
                    return statement.value.value.encode()
    raise ValueError("Legacy builder does not contain the expected literal archive key")


def load_profile(installer: Path) -> VendorProfile:
    """Read the profile from the researched MyHOME Suite 3.5.38 installer."""
    from bitrock_unpacker.cookfs import (
        PageReader, build_cookfs_layout, decompress_index_blob, find_cookfsinfo, parse_fsindex,
    )
    from bitrock_unpacker.extract import build_chunk_maps, write_entry_data
    from bitrock_unpacker.pe import parse_pe_overlay

    data = installer.read_bytes()
    pe = parse_pe_overlay(data)
    layout = build_cookfs_layout(data, pe.overlay_start, find_cookfsinfo(data, pe.overlay_start))
    entries = parse_fsindex(decompress_index_blob(data, layout))
    files, chunks = build_chunk_maps(entries)
    name = "default/resTargetDir4/devices/2266_1.5_BT/xml/Protocol/protocol.xml"
    output = io.BytesIO()
    reader = PageReader(data, layout)
    write_entry_data(output, reader, files[name])
    for chunk in chunks.get(name, []):
        write_entry_data(output, reader, chunk)
    root = ET.fromstring(output.getvalue())
    if (root.findtext("providerId") != "BTESUProtocolXPProvider"
            or root.findtext("modObjs/modObj") != "1.0.99"
            or root.findtext("watershedVer") != "always"):
        raise ValueError("Installer does not contain the researched C100X profile")

    def credentials(suffix: str) -> Credentials:
        username = root.findtext(f".//ftp_user_{suffix}")
        password = root.findtext(f".//ftp_pwd_{suffix}")
        if not username or not password or any(c in username + password for c in "\r\n"):
            raise ValueError("Installer FTP settings are missing or invalid")
        return Credentials(username, password)

    return VendorProfile(credentials("updateFw"), credentials("UpdateRecovery"))
