"""Read back files, startup links and unchanged stock dependencies after composition."""
from classe100x.firmware import FirmwareError
from classe100x.payload import Context
from common import STARTUP, configuration, prerequisites

c = Context()
prerequisites(c.image)
c.image.require_file("/etc/c100x-mqtt/config.ini", configuration(c.inputs), mode=0o600)
c.image.require_file("/usr/sbin/c100x-mqtt.py", (c.directory / "files/bridge.py").read_bytes(), mode=0o755)
c.image.require_file("/etc/init.d/c100x-mqtt", (c.directory / "files/init.sh").read_bytes(), mode=0o755)
info = c.image.stat("/etc/c100x-mqtt")
if (info["type"], info["uid"], info["gid"], info["mode"]) != ("directory", 0, 0, 0o700):
    raise FirmwareError("MQTT configuration-directory metadata check failed")
for path, target in STARTUP.items():
    c.image.require_symlink(path, target)
    info = c.image.stat(path)
    if info["uid"] or info["gid"]:
        raise FirmwareError("MQTT startup-link ownership check failed")
