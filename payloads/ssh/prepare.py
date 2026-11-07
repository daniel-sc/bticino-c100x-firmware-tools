"""Prepare guarded account/config edits and a fresh persistent host identity."""

import json
from pathlib import Path, PurePosixPath
import re

from classe100x.firmware import FirmwareError
from classe100x.host import find_tool, run_tool
from classe100x.payload import Context
from classe100x.diagnostics import tool_error
from common import BOOT_LINKS, CONFIG, HOST_KEY, SERVICE, public_key, stock_hashes

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

original = {path: c.stock_file(path, checksum) for path, checksum in stock_hashes(c.data.get("environment", "main")).items()}
if b"id:5:initdefault:" not in original["/etc/inittab"]:
    raise FirmwareError("Unexpected default runlevel")
c.image.require_symlink("/usr/sbin/dropbear", "./dropbearmulti")
daemon = c.image.stat("/usr/sbin/dropbearmulti")
if daemon["type"] != "regular" or not daemon["mode"] & 0o111:
    raise FirmwareError("Stock SSH daemon is unavailable")
for path in ("/home/root/.ssh", HOST_KEY, "/etc/dropbear/authorized_keys", "/etc/rc5.d/S98dropbear",
             CONFIG, SERVICE, *BOOT_LINKS):
    c.image.require_absent(path)
for path in {"/home/root", "/etc/dropbear", *(str(PurePosixPath(p).parent) for p in BOOT_LINKS)}:
    if c.image.stat(path)["type"] != "directory":
        raise FirmwareError("Unexpected SSH parent-directory type")
for path in ("/etc/passwd", "/etc/shadow"):
    if any(line.split(b":", 1)[0] == b"root2" for line in original[path].splitlines()):
        raise FirmwareError("The administrative account already exists")

password_hash = b"*"
shared = Path(c.data["shared_ssh"]) if "shared_ssh" in c.data else None
if password is not None:
    # Stock shadow entries use SHA-512 crypt ($6$). stdin keeps the password out of argv.
    openssl = find_tool("openssl", c.inputs.get("openssl"))
    if shared is not None and (shared / "password_hash").exists():
        status, password_hash, err = 0, (shared / "password_hash").read_bytes(), b""
    else:
        status, out, err = run_tool([openssl, "passwd", "-6", "-stdin"],
                                  input_data=password.encode() + b"\n", timeout=10)
        password_hash = out.strip()
    if status or not re.fullmatch(rb"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}", password_hash):
        raise tool_error(FirmwareError("Unable to produce the stock-supported password hash"), openssl, status, err)
    if shared is not None:
        (shared / "password_hash").write_bytes(password_hash)
        (shared / "password_hash").chmod(0o600)

c.write("passwd", original["/etc/passwd"].rstrip(b"\n") + b"\nroot2:x:0:0:root:/home/root:/bin/sh\n")
c.write("shadow", original["/etc/shadow"].rstrip(b"\n") + b"\nroot2:" + password_hash + b":18033:0:99999:7:::\n")
# The pinned vendor script checks NO_START before dispatching both start and stop.
# Its calls must never control the independently owned c100x-ssh service.
c.write("dropbear.conf", original["/etc/default/dropbear"] + b"\nNO_START=1\n")
c.write("c100x-ssh.conf", b"PASSWORD_AUTH=" + (b"1" if password is not None else b"0") + b"\n")
c.write("authorized_keys", key)

hostkey = c.generated / "host_key"
dropbearkey = find_tool("dropbearkey", c.inputs.get("dropbearkey"))
if shared is not None and (shared / "host_key").exists():
    hostkey.write_bytes((shared / "host_key").read_bytes())
    status, err = 0, b""
else:
    status, _, err = run_tool([dropbearkey,
                             "-t", "ecdsa", "-s", "256", "-f", str(hostkey)], timeout=30)
if status or not hostkey.is_file():
    raise tool_error(FirmwareError("Unable to generate the SSH host key"), dropbearkey, status, err)
hostkey.chmod(0o600)
if shared is not None:
    (shared / "host_key").write_bytes(hostkey.read_bytes())
    (shared / "host_key").chmod(0o600)
c.write("expected.json", json.dumps({"password_enabled": password is not None,
                                    "public_key_type": key_type}).encode())
