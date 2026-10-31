"""Prepare inert private configuration and check the stock runtime offline."""
from classe100x.firmware import FirmwareError
from classe100x.payload import Context
from common import STARTUP, configuration, prerequisites

c = Context()
config = configuration(c.inputs)
prerequisites(c.image)
for path in ("/etc/c100x-mqtt", "/etc/init.d/c100x-mqtt", "/usr/sbin/c100x-mqtt.py", *STARTUP):
    c.image.require_absent(path)
for path in ("/etc", "/etc/init.d", "/etc/rc5.d", "/etc/rc0.d", "/etc/rc6.d", "/usr/sbin"):
    if c.image.stat(path)["type"] != "directory":
        raise FirmwareError("Unexpected MQTT parent-directory type")
c.write("config.ini", config)
