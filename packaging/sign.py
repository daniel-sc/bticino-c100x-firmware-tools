"""Sign all shipped Mach-O code explicitly after relocation, then verify it."""

import argparse
import hashlib
from pathlib import Path
import re

from build import audit, macho, run, text

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
parser.add_argument("--keychain", required=True)
args = parser.parse_args()
identities = re.findall(r'\b([A-Fa-f0-9]{40}) "Developer ID Application: [^"\n]+"',
                        text("security", "find-identity", "-v", "-p", "codesigning", args.keychain))
if len(identities) != 1:
    raise SystemExit("The P12 must contain exactly one valid Developer ID Application certificate and private key; re-export that identity from Keychain Access")
audit(args.bundle.resolve())
for path in sorted(args.bundle.rglob("*")):
    if not macho(path):
        continue
    suffix = hashlib.sha256(str(path.relative_to(args.bundle)).encode()).hexdigest()[:16]
    run("codesign", "--force", "--sign", identities[0], "--keychain", args.keychain,
        "--identifier", f"org.daniel-sc.c100x.{suffix}", "--options", "runtime", "--timestamp", path)
    run("codesign", "--verify", "--strict", path)
