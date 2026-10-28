"""Example: install supplied device binary, prepared configuration and init script."""

import hashlib

from classe100x.firmware import FirmwareError
from classe100x.payload import Context

c = Context()
if set(c.inputs) != {"binary", "binary_sha256", "configuration", "service"}:
    raise FirmwareError("binary-service requires binary, binary_sha256, configuration and service inputs")
for path in ("/usr/bin/image-service", "/etc/image-service.conf", "/etc/init.d/image-service", "/etc/rc5.d/S99image-service"):
    c.image.require_absent(path)
binary = c.input_bytes("binary", 32 * 1024**2)
if hashlib.sha256(binary).hexdigest() != c.inputs["binary_sha256"]:
    raise FirmwareError("Device binary failed its supplied integrity check")
# A payload packages target programs; it must never execute them on the host.
if not (binary.startswith(b"\x7fELF\x01\x01") and binary[18:20] == b"\x28\x00"):
    raise FirmwareError("Example payload expects a prebuilt little-endian ARM ELF32 binary")
service = c.input_bytes("service")
if not service.startswith(b"#!/bin/sh\n"):
    raise FirmwareError("Example service script must use the device's /bin/sh")
c.write("binary", binary)
c.write("configuration", c.input_bytes("configuration"))
c.write("service", service)
