"""Fetch the one researched stock image, verifying bytes before cache publication."""

import hashlib
import http.client
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.request

from .firmware import FirmwareError, STOCK_SHA256, regular_file

STOCK_URL = "https://assets.legrand.com/pim/AUTRE/C100X_010508.fwz"
STOCK_SIZE = 106240356
PROFILE = "c100x-1.5.8"


def stock_matches(path: Path) -> bool:
    with regular_file(path) as source:
        return (os.fstat(source.fileno()).st_size == STOCK_SIZE
                and hashlib.file_digest(source, "sha256").hexdigest() == STOCK_SHA256)


def publish(source: Path, destination: Path) -> None:
    """Atomic, no-clobber publication on the same filesystem, including symlinks."""
    try:
        os.link(source, destination)
    except FileExistsError:
        raise FirmwareError("Output already exists; choose a new path") from None
    source.unlink()


def fetch_stock(cache: Path, *, timeout: float = 300) -> Path:
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = cache / f"{PROFILE}-{STOCK_SHA256}.fwz"
    if target.exists() or target.is_symlink():
        if not stock_matches(target):
            raise FirmwareError("Cached stock firmware failed verification; remove it before fetching again")
        return target
    fd, name = tempfile.mkstemp(prefix=".download-", dir=cache)
    partial = Path(name)
    deadline = time.monotonic() + timeout
    try:
        with os.fdopen(fd, "wb") as output:
            request = urllib.request.Request(STOCK_URL, headers={"User-Agent": "classe100x-firmware-builder"})
            try:
                with urllib.request.urlopen(request, timeout=min(30, timeout)) as response:
                    if response.geturl().split(":", 1)[0] != "https":
                        raise FirmwareError("Firmware download redirected away from HTTPS")
                    expected = response.headers.get("Content-Length")
                    if expected is not None and expected != str(STOCK_SIZE):
                        raise FirmwareError("Firmware download has an unexpected size")
                    digest = hashlib.sha256()
                    length = 0
                    while True:
                        if time.monotonic() > deadline:
                            raise FirmwareError("Firmware download deadline exceeded")
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        length += len(chunk)
                        if length > STOCK_SIZE:
                            raise FirmwareError("Firmware download exceeds the pinned size")
                        output.write(chunk)
                        digest.update(chunk)
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
                raise FirmwareError("Unable to download the pinned stock firmware") from None
            if length != STOCK_SIZE or digest.hexdigest() != STOCK_SHA256:
                raise FirmwareError("Downloaded firmware failed size/SHA-256 verification")
            output.flush()
            os.fsync(output.fileno())
        try:
            publish(partial, target)
        except FirmwareError:
            # A concurrent fetch may have published the same verified bytes.
            if not target.exists() or not stock_matches(target):
                raise
        return target
    finally:
        partial.unlink(missing_ok=True)
