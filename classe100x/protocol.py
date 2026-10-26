"""Bounded, read-only OpenWebNet preflight.

The query allowlist comes from stock C100X 1.5.8 bt_device handlers.
An ACK to status 42 means the update child is absent, not proof of a successful
write. Query 40 returns update status, not device identification.
"""

from contextlib import AbstractContextManager
import math
import re
import socket
import time

ACK = b"*#*1##"
NACK = b"*#*0##"
READ_QUERIES = {15: "device_type", 16: "firmware", 17: "hardware", 19: "uptime", 40: "update_status"}
UPDATE_STATES = {
    0: "normal",
    1: "recovery",
    2: "recovery_corrupted",
    3: "extra_corrupted",
    4: "normal_requires_recovery_for_update",
}


class ProtocolError(Exception):
    """A peer did not complete the expected exchange."""


class AuthenticationRequired(ProtocolError):
    """The connection is outside the device's trusted address range."""


class FrameStream:
    """Keep TCP fragmentation/coalescing invisible to the protocol caller."""

    MAX_FRAME = 4096

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buffer = bytearray()

    def receive(self, deadline: float) -> bytes:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError("Timed out waiting for an OpenWebNet reply")
            end = self.buffer.find(b"##")
            if end >= 0:
                end += 2
                if end > self.MAX_FRAME:
                    raise ProtocolError("OpenWebNet reply exceeds the frame limit")
                frame = bytes(self.buffer[:end])
                del self.buffer[:end]
                if not re.fullmatch(rb"\*[0-9*#]+##", frame):
                    raise ProtocolError("Malformed OpenWebNet reply")
                return frame
            if len(self.buffer) >= self.MAX_FRAME:
                raise ProtocolError("Unterminated OpenWebNet reply exceeds the frame limit")
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(self.MAX_FRAME)
            except TimeoutError as exc:
                raise ProtocolError("Timed out waiting for an OpenWebNet reply") from exc
            except OSError as exc:
                raise ProtocolError("Connection failed while waiting for a reply") from exc
            if not chunk:
                detail = " during a frame" if self.buffer else ""
                raise ProtocolError(f"Device disconnected{detail}")
            self.buffer.extend(chunk)


class ReadOnlyClient(AbstractContextManager):
    """Connect and query known read-only dimensions; never start an update."""

    def __init__(self, host: str, port: int = 20000, timeout: float = 5.0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be a finite positive number")
        self.host = host
        self.port = port
        self.timeout = timeout
        self.stream: FrameStream | None = None

    def __enter__(self):
        try:
            self.stream = FrameStream(socket.create_connection((self.host, self.port), self.timeout))
            deadline = time.monotonic() + self.timeout
            if self.stream.receive(deadline) != ACK:
                raise ProtocolError("Device did not acknowledge the connection")
            self._send(b"*99*0##", deadline)
            reply = self.stream.receive(deadline)
            if reply == NACK:
                raise ProtocolError("Device rejected the command session")
            if reply != ACK:
                # Never log nonce/challenge/authentication material.
                raise AuthenticationRequired(
                    "Device requires authentication; USB preflight must originate from "
                    "the stock trusted address 192.168.129.2"
                )
            return self
        except BaseException:
            self.close()
            raise

    def _send(self, frame: bytes, deadline: float):
        if self.stream is None:
            raise ProtocolError("Client is not connected")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProtocolError("Timed out before sending command")
        self.stream.sock.settimeout(remaining)
        try:
            self.stream.sock.sendall(frame)
        except OSError as exc:
            raise ProtocolError("Connection failed while sending command") from exc

    def query(self, dimension: int, *, family: int = 13) -> tuple[str, ...]:
        if not ((family == 13 and dimension in READ_QUERIES) or (family, dimension) == (1013, 1)):
            raise ValueError("Dimension is not in the verified read-only allowlist")
        if self.stream is None:
            raise ProtocolError("Client is not connected")
        deadline = time.monotonic() + self.timeout
        prefix = f"*#{family}**{dimension}*".encode("ascii")
        try:
            self._send(f"*#{family}**{dimension}##".encode("ascii"), deadline)
            reply = self.stream.receive(deadline)
            if reply == NACK:
                raise ProtocolError(f"Device rejected read-only query {dimension}")
            if not reply.startswith(prefix):
                raise ProtocolError(f"Unexpected response to read-only query {dimension}")
            values = reply[len(prefix):-2].decode("ascii").split("*")
            if not values or any(not value.isdecimal() for value in values):
                raise ProtocolError(f"Malformed values for read-only query {dimension}")
            if self.stream.receive(deadline) != ACK:
                raise ProtocolError(f"Missing final ACK for read-only query {dimension}")
            return tuple(values)
        except BaseException:
            # A failed exchange loses framing/session confidence. Do not reuse it.
            self.close()
            raise

    def inspect(self) -> dict[str, tuple[str, ...]]:
        result = {label: self.query(dimension) for dimension, label in READ_QUERIES.items()}
        # Device type 200 is shared by multiple products. The extended identity
        # must match the FWZ object model before an update can be planned.
        identity = self.query(1, family=1013)
        if len(identity) != 4:
            self.close()
            raise ProtocolError("Expected code, configuration, brand and line in extended identity")
        result["extended_identity"] = identity
        # BTESUXP.ETH uses field 3 (line), not field 1 (configuration).
        result["object_model"] = (identity[2], identity[3], identity[0])
        return result

    def close(self):
        if self.stream is not None:
            self.stream.sock.close()
            self.stream = None

    def __exit__(self, *exc):
        self.close()
