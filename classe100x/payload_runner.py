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
    from classe100x.diagnostics import format_failure, text
    try:
        runpy.run_path(script, run_name="__main__")
    except Exception as exc:
        message = text(str(exc))
        if isinstance(exc, FirmwareError) and len(message) <= 300 and "\n" not in message:
            print("Payload error: " + message, file=sys.stderr)
        print(format_failure(exc, debug=True), file=sys.stderr)
        raise SystemExit(1) from None
