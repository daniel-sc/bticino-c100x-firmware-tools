"""Subprocess entry point for explicitly trusted local payload hooks."""

from pathlib import Path
import os
import runpy
import sys

if __name__ == "__main__":
    if os.geteuid() == 0:
        raise SystemExit("Payload hooks must run as an ordinary user, not root")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    script, context = sys.argv[1:]
    sys.path.insert(0, str(Path(script).resolve().parent))
    sys.argv = [script, context]
    from classe100x.firmware import FirmwareError
    try:
        runpy.run_path(script, run_name="__main__")
    except FirmwareError as exc:
        # Payload authors may deliberately provide a short, non-secret user error.
        # Tracebacks, arbitrary exceptions and other stdout/stderr stay private.
        message = str(exc)
        if len(message) <= 300 and "\n" not in message and "\r" not in message:
            print("Payload error: " + message, file=sys.stderr)
        raise SystemExit(1) from None
