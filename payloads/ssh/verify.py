"""Read actual image bytes/inodes; never infer success from the apply process exit."""

import json

from classe100x.firmware import FirmwareError
from classe100x.payload import Context
from common import HASHES, HOST_KEY, digest

c = Context()
for target, asset, mode in (
    ("/etc/passwd", "passwd", 0o644),
    ("/etc/shadow", "shadow", 0o600),
    ("/etc/default/dropbear", "dropbear.conf", 0o644),
    ("/home/root/.ssh/authorized_keys", "authorized_keys", 0o600),
    ("/etc/dropbear/authorized_keys", "authorized_keys", 0o600),
    (HOST_KEY, "host_key", 0o600),
):
    c.image.require_file(target, (c.generated / asset).read_bytes(), mode=mode)
for path in ("/home/root", "/home/root/.ssh", "/etc/dropbear"):
    info = c.image.stat(path)
    if (info["type"], info["uid"], info["gid"], info["mode"]) != ("directory", 0, 0, 0o700):
        raise FirmwareError("SSH parent-directory metadata check failed")
c.image.require_symlink("/etc/rc5.d/S98dropbear", "../init.d/dropbear")
c.image.require_symlink("/usr/sbin/dropbear", "./dropbearmulti")
for path in ("/etc/init.d/dropbear", "/etc/inittab", "/usr/sbin/dropbearmulti"):
    if digest(c.image.read(path)) != HASHES[path]:
        raise FirmwareError("SSH boot prerequisite changed")
if not c.image.stat("/etc/init.d/dropbear")["mode"] & 0o111:
    raise FirmwareError("SSH init script is not executable")
for path in ("/etc/passwd", "/etc/shadow"):
    data = c.image.read(path)
    original = b"".join(line for line in data.splitlines(keepends=True) if not line.startswith(b"root2:"))
    if digest(original) != HASHES[path] or sum(line.startswith(b"root2:") for line in data.splitlines()) != 1:
        raise FirmwareError("SSH payload changed vendor accounts")
expected = json.loads((c.generated / "expected.json").read_text())
config = c.image.read("/etc/default/dropbear")
args = b'DROPBEAR_EXTRA_ARGS="' + (b"" if expected["password_enabled"] else b"-s") + b'"'
if args not in config or b'"-B"' in config or b"DROPBEAR_RSAKEY=" + HOST_KEY.encode() not in config:
    raise FirmwareError("SSH authentication/host-key configuration check failed")
host = c.image.read(HOST_KEY)
if b"ecdsa-sha2-nistp256" not in host[:64]:
    raise FirmwareError("Unexpected SSH host-key format")
