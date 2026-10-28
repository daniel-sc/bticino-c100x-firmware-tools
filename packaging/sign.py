"""Sign all shipped Mach-O code explicitly after relocation, then verify it."""

import argparse
import hashlib
from pathlib import Path

from build import audit, macho, run

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
parser.add_argument("--keychain", required=True)
args = parser.parse_args()
audit(args.bundle.resolve())
for path in sorted(args.bundle.rglob("*")):
    if not macho(path):
        continue
    suffix = hashlib.sha256(str(path.relative_to(args.bundle)).encode()).hexdigest()[:16]
    run("codesign", "--force", "--sign", "Developer ID Application:", "--keychain", args.keychain,
        "--identifier", f"org.daniel-sc.c100x.{suffix}", "--options", "runtime", "--timestamp", path)
    run("codesign", "--verify", "--strict", path)
