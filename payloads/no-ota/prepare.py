"""Make only the two configuration edits, from byte-pinned stock inputs."""
import re

from classe100x.firmware import FirmwareError
from classe100x.payload import Context
from common import BOOT, CLOUD, OUTPUT, STACK, STOCK, prerequisites, require_digest

c = Context()
if c.inputs:
    raise FirmwareError("no-ota accepts no inputs")
prerequisites(c.image)
c.image.require_symlink(BOOT, "../init.d/dedrifu.sh")
stack = c.stock_file(STACK, STOCK[STACK])
# Preserve every other byte, including vendor formatting. Stock has p0..p9;
# removing p8 requires renumbering the remaining camera entry to p8.
stack = re.sub(rb"<p8>\s*<name>fw_manager</name>.*?</p8>\n", b"", stack, flags=re.S)
stack = stack.replace(b"<p9>", b"<p8>").replace(b"</p9>", b"</p8>")
cloud = c.stock_file(CLOUD, STOCK[CLOUD]).replace(b"\nFwUpdate=1\n", b"\nFwUpdate=0\n")
for path, name, data in ((STACK, "stack_open.xml", stack), (CLOUD, "bt_eliot", cloud)):
    require_digest(data, OUTPUT[path], path)
    c.write(name, data)
