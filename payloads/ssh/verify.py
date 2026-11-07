"""Read actual image bytes/inodes; never infer success from the apply process exit."""

import json

from classe100x.firmware import FirmwareError
from classe100x.payload import Context
from common import BOOT_LINKS, CONFIG, HOST_KEY, SERVICE, check_boot_prerequisites, digest, require_executable, stock_hashes

c = Context()
HASHES = stock_hashes(c.data.get("environment", "main"))
for target, asset, mode in (
    ("/etc/passwd", "passwd", 0o644),
    ("/etc/shadow", "shadow", 0o600),
    ("/etc/default/dropbear", "dropbear.conf", 0o644),
    (CONFIG, "c100x-ssh.conf", 0o644),
    ("/home/root/.ssh/authorized_keys", "authorized_keys", 0o600),
    ("/etc/dropbear/authorized_keys", "authorized_keys", 0o600),
    (HOST_KEY, "host_key", 0o600),
):
    c.image.require_file(target, (c.generated / asset).read_bytes(), mode=mode)
for path in ("/home/root", "/home/root/.ssh", "/etc/dropbear"):
    info = c.image.stat(path)
    if (info["type"], info["uid"], info["gid"], info["mode"]) != ("directory", 0, 0, 0o700):
        raise FirmwareError("SSH parent-directory metadata check failed")
require_executable(c.image, SERVICE, (c.directory / "files/init.sh").read_bytes())
for path, target in BOOT_LINKS.items():
    c.image.require_symlink(path, target)
c.image.require_absent("/etc/rc5.d/S98dropbear")
c.image.require_symlink("/usr/sbin/dropbear", "./dropbearmulti")
check_boot_prerequisites(c.image)
for path in ("/etc/passwd", "/etc/shadow"):
    data = c.image.read(path)
    original = b"".join(line for line in data.splitlines(keepends=True) if not line.startswith(b"root2:"))
    if digest(original) != HASHES[path] or sum(line.startswith(b"root2:") for line in data.splitlines()) != 1:
        raise FirmwareError("SSH payload changed vendor accounts")
expected = json.loads((c.generated / "expected.json").read_text())
if not c.image.read("/etc/default/dropbear").endswith(b"\nNO_START=1\n"):
    raise FirmwareError("Vendor SSH lifecycle is not disabled")
config = b"PASSWORD_AUTH=" + (b"1" if expected["password_enabled"] else b"0") + b"\n"
if c.image.read(CONFIG) != config:
    raise FirmwareError("SSH authentication configuration check failed")
host = c.image.read(HOST_KEY)
if b"ecdsa-sha2-nistp256" not in host[:64]:
    raise FirmwareError("Unexpected SSH host-key format")
