"""e2fsprogs image-file backend. Raw command files are trusted, not sandboxed."""

from dataclasses import dataclass
from pathlib import Path
import re
import tempfile

from .firmware import FirmwareError
from .host import find_tool, run_tool


def quote(value: str | Path) -> str:
    # debugfs has its own parser, not shell quoting. Reject ambiguous characters.
    value = str(value)
    if any(c in value for c in ('"', "\\", "\n", "\r", "\x00")):
        raise FirmwareError("Unsupported character in a debugfs path")
    return f'"{value}"'


@dataclass
class Ext4:
    image: Path
    debugfs: str
    e2fsck: str

    @classmethod
    def discover(cls, image: Path, *, debugfs=None, e2fsck=None):
        return cls(image.resolve(), find_tool("debugfs", debugfs), find_tool("e2fsck", e2fsck))

    def _run(self, options: list[str], *, cwd: Path | None = None) -> bytes:
        status, stdout, stderr = run_tool([self.debugfs, *options, str(self.image)], cwd=cwd)
        lines = stderr.decode("utf-8", errors="replace").splitlines()
        # Even failed write/mkdir commands can exit 0. Permit only the tool banner.
        if status or any(not re.fullmatch(r"debugfs \d+\.\d+(?:\.\d+)? \([^\r\n]+\)", line)
                         for line in lines if line.strip()):
            raise FirmwareError("debugfs reported an operation error (raw diagnostics withheld)")
        return stdout

    def command(self, command: str) -> bytes:
        return self._run(["-R", command])

    def names(self, directory: str) -> set[str]:
        if self.stat(directory)["type"] != "directory":
            raise FirmwareError("Expected a directory inside the image")
        entries = self.command(f"ls -p {quote(directory)}").decode("utf-8").splitlines()
        names = set()
        for line in entries:
            if not line:
                continue
            fields = line.split("/")
            if len(fields) < 7 or not fields[1].isdigit():
                raise FirmwareError("Unable to interpret debugfs directory listing")
            names.add(fields[5])
        return names

    def require_absent(self, path: str) -> None:
        parent, name = path.rsplit("/", 1)
        if name in self.names(parent or "/"):
            raise FirmwareError("Payload expected an absent destination")

    def apply(self, commands: Path, cwd: Path) -> None:
        if commands.stat().st_size > 1024 * 1024:
            raise FirmwareError("Payload command file exceeds the supported limit")
        # Avoid silent truncation of a long line in debugfs's fixed-size batch buffer.
        data = commands.read_bytes()
        if b"\x00" in data or any(len(line) > 4096 for line in data.splitlines()):
            raise FirmwareError("Invalid or overlong debugfs command line")
        self._run(["-w", "-f", str(commands.resolve())], cwd=cwd)

    def check(self) -> None:
        status, _, _ = run_tool([self.e2fsck, "-f", "-n", str(self.image)], timeout=300)
        if status != 0:
            raise FirmwareError("Filesystem check failed; no automatic repair or vendor-error exception is enabled")

    def read(self, path: str, *, limit: int = 1024 * 1024) -> bytes:
        info = self.stat(path)
        if info["type"] != "regular" or info["size"] > limit:
            raise FirmwareError("Expected a bounded regular file inside the image")
        if info["size"] <= 1024 * 1024:
            data = self.command(f"cat {quote(path)}")
        else:
            with tempfile.TemporaryDirectory(prefix="readback-", dir=self.image.parent) as tmp:
                destination = Path(tmp) / "file"
                self.command(f"dump {quote(path)} {quote(destination)}")
                if destination.stat().st_size > limit:
                    raise FirmwareError("Readback exceeded its size limit")
                data = destination.read_bytes()
        if len(data) != info["size"]:
            raise FirmwareError("Image file readback length mismatch")
        return data

    def stat(self, path: str) -> dict:
        text = self.command(f"stat {quote(path)}").decode("utf-8", errors="strict")
        inode = re.search(r"Inode:\s+(\d+)\s+Type:\s+(\w+)\s+Mode:\s+([0-7]+)", text)
        owner = re.search(r"User:\s+(\d+)\s+Group:\s+(\d+).*?Size:\s+(\d+)", text)
        links = re.search(r"Links:\s+(\d+)", text)
        acl = re.search(r"File ACL:\s+(\d+)", text)
        if not all((inode, owner, links, acl)):
            raise FirmwareError("Unable to interpret debugfs inode metadata")
        return {"inode": int(inode[1]), "type": inode[2], "mode": int(inode[3], 8),
                "uid": int(owner[1]), "gid": int(owner[2]), "size": int(owner[3]),
                "links": int(links[1]), "acl": int(acl[1]), "raw": text}

    def require_file(self, path: str, data: bytes, *, mode: int, uid=0, gid=0) -> None:
        info = self.stat(path)
        if (info["type"], info["mode"], info["uid"], info["gid"]) != ("regular", mode, uid, gid):
            raise FirmwareError("Payload file metadata verification failed")
        if self.read(path, limit=max(len(data), 1)) != data:
            raise FirmwareError("Payload file content verification failed")

    def require_symlink(self, path: str, target: str) -> None:
        info = self.stat(path)
        # Bundled startup links are short, stored inline. Long links require a separate reader.
        if info["type"] != "symlink" or f'Fast link dest: "{target}"' not in info["raw"]:
            raise FirmwareError("Payload symlink verification failed")
