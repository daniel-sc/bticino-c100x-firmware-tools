"""Prepare guarded account/config edits and a fresh persistent host identity."""

import json
import re

from classe100x.firmware import FirmwareError
from classe100x.host import find_tool, run_tool
from classe100x.payload import Context
from common import HASHES, HOST_KEY, public_key

c = Context()
if set(c.inputs) - {"public_key", "password", "password_file", "dropbearkey", "openssl"}:
    raise FirmwareError("Unknown SSH input")
if "password" in c.inputs and "password_file" in c.inputs:
    raise FirmwareError("Supply one password source")
password = c.inputs.get("password")
if "password_file" in c.inputs:
    if c.input_path("password_file").stat().st_mode & 0o077:
        raise FirmwareError("Password input file must have private permissions")
    password = c.input_bytes("password_file", 1024).decode("utf-8").removesuffix("\n")
if password is not None and (not isinstance(password, str) or not password or len(password.encode()) > 512
                             or any(ch in password for ch in "\x00\r\n")):
    raise FirmwareError("SSH password must be nonempty, bounded and single-line")
key, key_type = (b"", None)
if "public_key" in c.inputs:
    key, key_type = public_key(c.input_bytes("public_key", 16384))
if not key and password is None:
    raise FirmwareError("SSH requires a public key, password, or both")

original = {path: c.stock_file(path, checksum) for path, checksum in HASHES.items()}
if b"id:5:initdefault:" not in original["/etc/inittab"]:
    raise FirmwareError("Unexpected default runlevel")
c.image.require_symlink("/usr/sbin/dropbear", "./dropbearmulti")
daemon = c.image.stat("/usr/sbin/dropbearmulti")
if daemon["type"] != "regular" or not daemon["mode"] & 0o111:
    raise FirmwareError("Stock SSH daemon is unavailable")
for path in ("/home/root/.ssh", HOST_KEY, "/etc/dropbear/authorized_keys", "/etc/rc5.d/S98dropbear"):
    c.image.require_absent(path)
for path in ("/home/root", "/etc/dropbear", "/etc/rc5.d"):
    if c.image.stat(path)["type"] != "directory":
        raise FirmwareError("Unexpected SSH parent-directory type")
for path in ("/etc/passwd", "/etc/shadow"):
    if any(line.split(b":", 1)[0] == b"root2" for line in original[path].splitlines()):
        raise FirmwareError("The administrative account already exists")

password_hash = b"*"
if password is not None:
    # Stock shadow entries use SHA-512 crypt ($6$). stdin keeps the password out of argv.
    status, out, _ = run_tool([find_tool("openssl", c.inputs.get("openssl")), "passwd", "-6", "-stdin"],
                              input_data=password.encode() + b"\n", timeout=10)
    password_hash = out.strip()
    if status or not re.fullmatch(rb"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}", password_hash):
        raise FirmwareError("Unable to produce the stock-supported password hash")

c.write("passwd", original["/etc/passwd"].rstrip(b"\n") + b"\nroot2:x:0:0:root:/home/root:/bin/sh\n")
c.write("shadow", original["/etc/shadow"].rstrip(b"\n") + b"\nroot2:" + password_hash + b":18033:0:99999:7:::\n")
config = original["/etc/default/dropbear"]
if config.count(b'DROPBEAR_EXTRA_ARGS="-B"') != 1:
    raise FirmwareError("Unexpected stock SSH argument definition")
config = config.replace(b'DROPBEAR_EXTRA_ARGS="-B"',
                        b'DROPBEAR_EXTRA_ARGS="' + (b"-s" if password is None else b"") + b'"')
# Despite the variable name, init passes this file directly to Dropbear's generic -r.
# The existing file also prevents init's RSA generation branch on read-only rootfs.
config += b"\nNO_START=0\nDROPBEAR_RSAKEY=" + HOST_KEY.encode() + b"\n"
c.write("dropbear.conf", config)
c.write("authorized_keys", key)

hostkey = c.generated / "host_key"
status, _, _ = run_tool([find_tool("dropbearkey", c.inputs.get("dropbearkey")),
                         "-t", "ecdsa", "-s", "256", "-f", str(hostkey)], timeout=30)
if status or not hostkey.is_file():
    raise FirmwareError("Unable to generate the SSH host key")
hostkey.chmod(0o600)
c.write("expected.json", json.dumps({"password_enabled": password is not None,
                                    "public_key_type": key_type}).encode())
