"""Read-only destination admission for SSH flashing; loaded only on that path."""

from contextlib import contextmanager
from dataclasses import dataclass
import gzip
import hashlib
import hmac
import os
from pathlib import Path
import re
import runpy
import selectors
import shutil
import signal
import subprocess
import tempfile
import time

from .diagnostics import remember_secret
from .ext4 import Ext4
from .firmware import FirmwareError, MAIN_FILES, RECOVERY_FILES, check_main_image, filesystem_profile
from .host import find_tool, run_tool


ASSETS = Path(__file__).resolve().parent.parent / "payloads"


def facts(name):
    return runpy.run_path(str(ASSETS / name / "common.py"))


def public_identity(data):
    return facts("ssh")["public_key"](data)[0].decode().strip()


def pipe_tool(arguments, *, secret=None, env=None, **privileges):
    """Small bounded-output local credential utilities. Never spool password stdin."""
    remember_secret(secret)
    data = b"" if secret is None else secret.encode() + b"\n"
    if len(data) > 4097:
        raise FirmwareError("Credential input exceeds its limit")
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE if data else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                               env=env or {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, **privileges)
    output = [bytearray(), bytearray()]
    deadline = time.monotonic() + 10
    try:
        with selectors.DefaultSelector() as selector:
            for stream, index in ((process.stdout, 0), (process.stderr, 1)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, index)
            if data:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, 2)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FirmwareError("Credential tool timed out")
                for event, _ in selector.select(min(remaining, 0.1)):
                    if event.data == 2:
                        sent = os.write(event.fd, data[:4096])
                        data = data[sent:]
                        if not data:
                            selector.unregister(event.fileobj)
                            process.stdin.close()
                    else:
                        chunk = os.read(event.fd, 16384)
                        if not chunk:
                            selector.unregister(event.fileobj)
                        else:
                            output[event.data].extend(chunk)
                            if sum(map(len, output)) > 65536:
                                raise FirmwareError("Credential tool output exceeded its limit")
            if process.wait(timeout=max(0.001, deadline - time.monotonic())):
                raise FirmwareError("Credential tool failed")
        return bytes(output[0])
    finally:
        if secret is not None:
            remember_secret(bytes(output[0]).strip())
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def check_password(password, encoded, openssl):
    if not re.fullmatch(rb"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}", encoded):
        raise FirmwareError("Destination uses an unsupported password hash")
    remember_secret(encoded)
    result = pipe_tool([openssl, "passwd", "-6", "-salt", encoded.split(b"$")[2].decode(), "-stdin"], secret=password).strip()
    remember_secret(result)
    if not hmac.compare_digest(result, encoded):
        raise FirmwareError("Destination password does not match both images")


@dataclass
class Destination:
    host_key: str
    vendor_updates: bool
    authentication: str = ""


def inspect_image(image, environment, directory, credentials, tools):
    ssh = facts("ssh")
    hashes = ssh["stock_hashes"](environment)
    user = credentials.user
    if user != "root2":
        raise FirmwareError("Destination requires the supported root2 administrative account")
    records = {}
    for path, mode in (("/etc/passwd", 0o644), ("/etc/shadow", 0o600)):
        data = image.read(path)
        records[path] = [line for line in data.splitlines() if line.startswith(b"root2:")]
        original = b"".join(line for line in data.splitlines(keepends=True) if not line.startswith(b"root2:"))
        if len(records[path]) != 1 or hashlib.sha256(original).hexdigest() != hashes[path]:
            raise FirmwareError("Unsupported destination account records")
        image.require_file(path, data, mode=mode)
    if records["/etc/passwd"][0] != b"root2:x:0:0:root:/home/root:/bin/sh":
        raise FirmwareError("Unsupported destination administrative account")
    ssh["check_boot_prerequisites"](image)
    image.require_symlink("/usr/sbin/dropbear", "./dropbearmulti")
    ssh["require_executable"](image, ssh["SERVICE"], (ASSETS / "ssh/files/init.sh").read_bytes())
    for path, target in ssh["BOOT_LINKS"].items():
        image.require_symlink(path, target)
    image.require_absent("/etc/rc5.d/S98dropbear")
    for path in ("/home/root", "/home/root/.ssh", "/etc/dropbear"):
        info = image.stat(path)
        if (info["type"], info["mode"], info["uid"], info["gid"]) != ("directory", 0o700, 0, 0):
            raise FirmwareError("Invalid SSH directory permissions")
    defaults = image.read("/etc/default/dropbear")
    if (not defaults.endswith(b"\nNO_START=1\n") or
            hashlib.sha256(defaults[:-12]).hexdigest() != hashes["/etc/default/dropbear"]):
        raise FirmwareError("Destination vendor SSH lifecycle is not disabled")
    image.require_file("/etc/default/dropbear", defaults, mode=0o644)
    config = image.read(ssh["CONFIG"])
    if config not in (b"PASSWORD_AUTH=0\n", b"PASSWORD_AUTH=1\n"):
        raise FirmwareError("Unsupported destination authentication configuration")
    image.require_file(ssh["CONFIG"], config, mode=0o644)
    authorized = image.read("/home/root/.ssh/authorized_keys", limit=16384)
    for path in ("/home/root/.ssh/authorized_keys", "/etc/dropbear/authorized_keys"):
        image.require_file(path, authorized, mode=0o600)
    if credentials.password is not None:
        if config != b"PASSWORD_AUTH=1\n":
            raise FirmwareError("Destination password authentication is disabled")
        check_password(credentials.password, records["/etc/shadow"][0].split(b":")[1], tools["openssl"])
    elif not authorized or public_identity(authorized) not in credentials.public_keys():
        raise FirmwareError("Destination does not authorize the selected login key/agent")
    host = image.read(ssh["HOST_KEY"], limit=16384)
    image.require_file(ssh["HOST_KEY"], host, mode=0o600)
    keyfile = directory / "host-key"
    try:
        keyfile.write_bytes(host)
        keyfile.chmod(0o600)
        status, out, _ = run_tool([tools["dropbearkey"], "-y", "-f", str(keyfile)], timeout=10, limit=16384)
        lines = [line for line in out.splitlines() if line.startswith(b"ecdsa-sha2-nistp256 ")]
        if status or len(lines) != 1:
            raise FirmwareError("Invalid destination SSH host key")
        public = public_identity(lines[0])
    finally:
        keyfile.unlink(missing_ok=True)
    policy = facts("no-ota")
    policy["prerequisites"](image, environment)
    stack = hashlib.sha256(image.read(policy["STACK"])).hexdigest()
    allowed = stack == policy["STOCK"][policy["STACK"]]
    pins = policy["STOCK"] if allowed else policy["OUTPUT"]
    for path, expected in pins.items():
        policy["require_pinned"](image, path, expected, 0o664, 1000)
    if allowed:
        image.require_symlink(policy["BOOT"], "../init.d/dedrifu.sh")
    else:
        image.require_absent(policy["BOOT"])
        policy["require_no_updater_links"](image)
    return Destination(public, allowed, hashlib.sha256(config + authorized + records["/etc/shadow"][0]).hexdigest())


@contextmanager
def admit(firmware, credentials):
    tools = {name: find_tool(name) for name in ("debugfs", "e2fsck", "dropbearkey", "openssl")}
    with tempfile.TemporaryDirectory(prefix="wireless-images-", dir=firmware.directory) as tmp:
        directory = Path(tmp)
        if shutil.disk_usage(directory).free < sum(filesystem_profile(r)[0] for r in (False, True)) + 512 * 1024**2:
            raise FirmwareError("Wireless admission needs at least 1.7 GiB free for private image checks")
        results = []
        for recovery, name in ((False, MAIN_FILES[0]), (True, RECOVERY_FILES[0])):
            image = directory / ("recovery.ext4" if recovery else "main.ext4")
            with gzip.open(firmware.directory / name, "rb") as src, image.open("xb") as dst:
                size = 0
                while data := src.read(1024**2):
                    size += len(data)
                    if size > filesystem_profile(recovery)[0]:
                        raise FirmwareError("Expanded wireless image exceeds its profile")
                    dst.write(data)
            check_main_image(image, recovery=recovery)
            fs = Ext4(image, tools["debugfs"], tools["e2fsck"])
            fs.check()
            results.append(inspect_image(fs, "recovery" if recovery else "main", directory, credentials, tools))
        if results[0] != results[1]:
            raise FirmwareError("Main and recovery SSH identity or vendor-update policy differs")
        yield results[0]
