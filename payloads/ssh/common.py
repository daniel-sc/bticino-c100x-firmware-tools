"""Stock-specific SSH facts and small helpers; no vendor file contents are embedded."""

import base64
import hashlib
import struct

from classe100x.firmware import FirmwareError

HASHES = {
    "/etc/init.d/dropbear": "1c29abbb814626792f35c9f1d6329b45dd25566f91d30e684e78936b412d35b0",
    "/etc/default/dropbear": "d840d3c22916eb4c846a56481ddc3a87ec5345cf2345f5fcd8957c49cbc73235",
    "/etc/passwd": "ac0c2a31973f79693aa7bc6e96603d76a3cbba79bcf6577fbb1e122182e2101b",
    "/etc/shadow": "a53ed6a07da40e4917227f5c32d8ef52049f089b86c43cb8d163cb135bea61ea",
    "/etc/inittab": "d1b2bbf70058109ab5b3c786201b59ebc035bd91997784b9846d305eea9bd260",
    "/usr/sbin/dropbearmulti": "25593c31c1793bb2ea51d6ff084af51d527ee13c1913915612a4f0bcc8312760",
}
HOST_KEY = "/etc/dropbear/classe100x_ecdsa_host_key"


def public_key(data: bytes) -> tuple[bytes, str]:
    lines = [line.strip() for line in data.splitlines() if line.strip()]
    if len(lines) != 1:
        raise FirmwareError("Supply exactly one OpenSSH public key")
    parts = lines[0].split()
    if len(parts) < 2 or parts[0] not in (b"ecdsa-sha2-nistp256", b"ssh-rsa"):
        raise FirmwareError("Stock Dropbear requires an ECDSA P-256 or legacy RSA public key")
    try:
        encoded = base64.b64decode(parts[1], validate=True)
        fields = []
        while encoded:
            length = struct.unpack_from(">I", encoded)[0]
            if length > len(encoded) - 4:
                raise ValueError
            fields.append(encoded[4:4 + length])
            encoded = encoded[4 + length:]
        if len(fields) != 3 or fields[0] != parts[0]:
            raise ValueError
        if parts[0].startswith(b"ecdsa") and (fields[1] != b"nistp256" or len(fields[2]) != 65 or fields[2][0] != 4):
            raise ValueError
        if parts[0] == b"ssh-rsa" and (not fields[1] or not fields[2]):
            raise ValueError
    except (ValueError, struct.error):
        raise FirmwareError("Malformed SSH public key") from None
    # Comments and authorized_keys options are deliberately not carried into the image.
    return b" ".join(parts[:2]) + b"\n", parts[0].decode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
