"""Create the download with its relocatable C100X folder intact."""

import argparse
from pathlib import Path
import shutil
import tempfile

from build import run

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="c100x-dmg-") as temporary:
    staging = Path(temporary)
    shutil.copytree(args.bundle, staging / "C100X", symlinks=True)
    run("hdiutil", "create", "-volname", "C100X Firmware Tools", "-srcfolder", staging,
        "-format", "UDZO", args.output.resolve())
