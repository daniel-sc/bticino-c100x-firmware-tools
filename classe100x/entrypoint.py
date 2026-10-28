"""Entry point for the relocatable distribution and supervised child processes."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from classe100x.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
