"""Locate release assets independently of the current working directory."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def bundled_tool(name: str) -> Path:
    return ROOT / "tools" / name


def tetherkit() -> Path:
    bundled = bundled_tool("tetherkit-cli")
    return bundled if bundled.is_file() else ROOT / ".local/tetherkit-build/bin/tetherkit-cli"


def version() -> str:
    manifest = ROOT / "release.json"
    return json.loads(manifest.read_text())["version"] if manifest.is_file() else "development"


def child_command(*arguments: str) -> list[str]:
    return [sys.executable, "-I", "-B", str(Path(__file__).with_name("entrypoint.py")), *arguments]
