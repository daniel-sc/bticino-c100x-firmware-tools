"""Small bounded process boundary for trusted builder tools and payload hooks."""

import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time

from .firmware import FirmwareError
from .resources import bundled_tool


def find_tool(name: str, override: str | None = None) -> str:
    candidates = [override] if override else [
        str(bundled_tool(name)),
        shutil.which(name),
        shutil.which("7z") if name == "7zz" else None,
        f"/opt/homebrew/opt/e2fsprogs/sbin/{name}",
        f"/usr/local/opt/e2fsprogs/sbin/{name}",
        f"/opt/homebrew/bin/{name}",
        f"/usr/sbin/{name}",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise FirmwareError(f"Required builder tool not found: {name}; supply an explicit tool path")


def run_tool(arguments: list[str], *, cwd: Path | None = None, timeout: float = 120,
             limit: int = 2 * 1024**2, input_data: bytes | None = None) -> tuple[int, bytes, bytes]:
    """Never include argv, stdin or tool output in exceptions (they can hold secrets)."""
    env = {**os.environ, "LC_ALL": "C", "LANG": "C", "PAGER": "/bin/cat",
           "DEBUGFS_PAGER": "/bin/cat", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("E2FSPROGS_UNDO_DIR", None)
    # Small secret inputs only. A private temporary stdin file avoids pipe deadlocks.
    import tempfile
    with tempfile.TemporaryFile() as stdin:
        if input_data is not None:
            stdin.write(input_data)
            stdin.seek(0)
        process = subprocess.Popen(arguments, cwd=cwd, env=env, stdin=stdin,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        output = [bytearray(), bytearray()]
        deadline = time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, 0)
                selector.register(process.stderr, selectors.EVENT_READ, 1)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise FirmwareError("Builder subprocess exceeded its time limit")
                    for key, _ in selector.select(min(remaining, 0.25)):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            output[key.data].extend(chunk)
                            if sum(map(len, output)) > limit:
                                raise FirmwareError("Builder subprocess exceeded its output limit")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FirmwareError("Builder subprocess exceeded its time limit")
                status = process.wait(timeout=remaining)
            return status, bytes(output[0]), bytes(output[1])
        except subprocess.TimeoutExpired:
            raise FirmwareError("Builder subprocess exceeded its time limit") from None
        finally:
            # Also stop children that retained pipes or outlived a hook.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            process.stdout.close()
            process.stderr.close()
