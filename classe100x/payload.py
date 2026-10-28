"""Convenience helpers for payload authors; this is not a sandbox or plugin API."""

import hashlib
import json
from pathlib import Path
import sys

from .ext4 import Ext4
from .firmware import FirmwareError, regular_file


class Context:
    def __init__(self, path: Path | None = None):
        self.data = json.loads((path or Path(sys.argv[1])).read_text())
        self.inputs = self.data["inputs"]
        self.directory = Path(self.data["directory"])
        self.generated = self.directory / "generated"
        self.generated.mkdir(mode=0o700, exist_ok=True)
        self.image = Ext4(Path(self.data["image"]), self.data["tools"]["debugfs"], self.data["tools"]["e2fsck"])

    def input_path(self, name: str) -> Path:
        value = self.inputs.get(name)
        if not isinstance(value, str):
            raise FirmwareError("Payload requires a file input")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path(self.data["input_base"]) / path
        return path.resolve()

    def input_bytes(self, name: str, limit=1024 * 1024) -> bytes:
        with regular_file(self.input_path(name)) as source:
            data = source.read(limit + 1)
        if len(data) > limit:
            raise FirmwareError("Payload input exceeds its size limit")
        return data

    def stock_file(self, path: str, expected_sha256: str) -> bytes:
        """Guard bundled replacements against unexpected contents or inode semantics."""
        info = self.image.stat(path)
        if info["type"] != "regular" or info["links"] != 1 or info["acl"] != 0:
            raise FirmwareError("Payload cannot replace this inode type/link/ACL layout")
        from .ext4 import quote
        if self.image.command(f"ea_list {quote(path)}").strip():
            raise FirmwareError("Payload does not replace files with extended attributes")
        data = self.image.read(path)
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise FirmwareError("Payload precondition failed: unexpected original file")
        return data

    def write(self, name: str, data: bytes) -> None:
        if Path(name).name != name:
            raise FirmwareError("Generated asset must have a simple filename")
        path = self.generated / name
        with path.open("xb") as output:
            output.write(data)
        path.chmod(0o600)
