"""The researched C100X 1.5.8 update sequence, with no write retries.

See docs/PROTOCOL.md for evidence and the distinction between worker completion
and successful installation. A connection loss during a write is an ambiguous
outcome: stop, retain the current stage, and never reboot as error cleanup.
"""

import ftplib
from pathlib import Path
import time

from .firmware import MAIN_FILES, RECOVERY_FILES, Payload, PreparedFirmware
from .protocol import ACK, NACK, ProtocolError, ReadOnlyClient
from .vendor import Credentials, VendorProfile


class UpdateError(Exception):
    pass


class UncertainDelivery(UpdateError):
    pass


def uptime_seconds(values: tuple[str, ...]) -> int:
    try:
        days, hours, minutes, seconds = map(int, values)
        if days < 0 or not (0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 60):
            raise ValueError
        return days * 86400 + hours * 3600 + minutes * 60 + seconds
    except (TypeError, ValueError):
        raise UpdateError("Invalid device uptime") from None


def check_identity(info: dict, expected_status: int) -> None:
    expected = {
        "device_type": (200,), "firmware": (1, 5, 8),
        "hardware": (2, 6, 0), "object_model": (1, 0, 99),
        "update_status": (expected_status, 0),
    }
    for key, value in expected.items():
        try:
            actual = tuple(int(part) for part in info[key])
        except (KeyError, TypeError, ValueError):
            raise UpdateError(f"Missing or invalid {key} in device identity") from None
        if actual != value:
            raise UpdateError(f"Device {key} does not match the researched 1.5.8 update path")


class UpdateClient(ReadOnlyClient):
    """Explicit write-capable client; the preflight client remains read-only."""

    def _once(self, frame: bytes, label: str) -> None:
        deadline = time.monotonic() + self.timeout
        try:
            self._send(frame, deadline)
            reply = self.stream.receive(deadline)
        except (ProtocolError, OSError):
            self.close()
            raise UncertainDelivery(f"Delivery of {label} is uncertain; command was not retried") from None
        if reply != ACK:
            self.close()
            if reply == NACK:
                raise UpdateError(f"Device rejected {label}")
            raise UncertainDelivery(f"Unexpected reply to {label}; command was not retried")

    def begin(self, recovery: bool) -> None:
        self._once(b"*#13**#37*0##" if recovery else b"*#13**#36*0##", "start transfer")

    def commit(self, payload: Payload) -> None:
        self._once(f"*#13**#35*{payload.size}*0*{payload.cksum}##".encode(), "start payload write")

    def idle(self) -> bool:
        deadline = time.monotonic() + self.timeout
        try:
            self._send(b"*#13**42##", deadline)
            reply = self.stream.receive(deadline)
            if reply not in (ACK, NACK):
                raise ProtocolError("Unexpected update-worker status")
            return reply == ACK
        except BaseException:
            self.close()
            raise

    def finish(self) -> None:
        self._once(b"*#13**#33*0##", "close FTP")

    def invalidate_main_kernel(self) -> None:
        self._once(b"*13*25**##", "enter recovery (clear main kernel)")

    def reboot(self) -> None:
        self._once(b"*#13**43##", "reboot")


class NetworkDevice:
    def __init__(self, host: str, port: int = 20000, *, timeout: float = 30,
                 reboot_timeout: float = 240, write_timeout: float = 180):
        self.host, self.port, self.timeout = host, port, timeout
        self.reboot_timeout, self.write_timeout = reboot_timeout, write_timeout
        self.client: UpdateClient | None = None

    def connect(self) -> dict:
        self.close()
        client = UpdateClient(self.host, self.port, self.timeout)
        self.client = client.__enter__()
        return self.client.inspect()

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def upload(self, path: Path, credentials: Credentials) -> None:
        # FTP starts only after the explicit begin command. Each worker consumes
        # and deletes its input, so exactly one file must be present at commit.
        try:
            with ftplib.FTP(timeout=30) as ftp:
                ftp.connect(self.host, 21)
                ftp.login(credentials.username, credentials.password)
                ftp.set_pasv(True)
                if ftp.nlst():
                    raise UpdateError("FTP staging directory is not empty")
                with path.open("rb") as source:
                    ftp.storbinary("STOR " + path.name, source, blocksize=65536)
                ftp.voidcmd("TYPE I")
                if ftp.size(path.name) != path.stat().st_size:
                    raise UpdateError("FTP payload length mismatch")
                if ftp.nlst() != [path.name]:
                    raise UpdateError("Unexpected files in FTP staging directory")
        except ftplib.all_errors:
            # Server replies and exception messages are not safe credential logs.
            raise UpdateError("FTP transfer failed; payload write was not requested") from None

    def wait_idle(self) -> None:
        deadline = time.monotonic() + self.write_timeout
        while True:
            if self.client.idle():
                return
            if time.monotonic() >= deadline:
                raise UpdateError("Update worker is still busy; no reboot was requested")
            time.sleep(5)

    def reboot_and_wait(self, status: int) -> dict:
        before = uptime_seconds(self.client.query(19))
        started = time.monotonic()
        self.client.reboot()
        self.close()
        deadline = started + self.reboot_timeout
        while time.monotonic() < deadline:
            time.sleep(1)
            try:
                with ReadOnlyClient(self.host, self.port, timeout=2) as probe:
                    info = probe.inspect()
            except (ProtocolError, OSError):
                continue
            elapsed = time.monotonic() - started
            after = uptime_seconds(info["uptime"])
            # The version remains 1.5.8 throughout. An uptime reset distinguishes
            # a reboot from a stale reply or a transient network interruption.
            if after > elapsed + 2 or before + elapsed - after < 5:
                continue
            check_identity(info, status)
            info = self.connect()
            check_identity(info, status)
            return info
        raise UpdateError("Reboot/reconnection was not verified; no command was retried")

    def settle(self) -> None:
        # MyHOME waits 3 seconds after FTP close and 5 seconds before main reboot.
        time.sleep(8)


def flash(firmware: PreparedFirmware, device: NetworkDevice, profile: VendorProfile,
          report=print) -> dict:
    """Three verified reboot boundaries; any failure stops subsequent writes."""
    stage = "preflight"
    try:
        info = device.connect()
        check_identity(info, 4)
        for recovery, names, credentials in (
            (True, RECOVERY_FILES, profile.normal),
            (False, MAIN_FILES, profile.recovery),
        ):
            target = "recovery" if recovery else "main"
            stage = f"{target}: starting transfer"
            report(stage)
            device.wait_idle()
            device.client.begin(recovery)
            for name in names:
                payload = firmware.payload(name)
                stage = f"{target}: uploading {name}"
                report(stage)
                device.upload(firmware.directory / name, credentials)
                stage = f"{target}: writing {name}"
                report(stage)
                device.client.commit(payload)
                device.wait_idle()
            stage = f"{target}: closing transfer"
            device.client.finish()
            device.settle()
            stage = f"{target}: rebooting"
            report(stage)
            info = device.reboot_and_wait(4)
            if recovery:
                stage = "entering recovery: clearing main kernel"
                report(stage)
                device.client.invalidate_main_kernel()
                stage = "entering recovery: rebooting"
                report(stage)
                device.reboot_and_wait(1)
        report("Update sequence completed; verify calls, audio/video, door release and SSH")
        return info
    except (UpdateError, ProtocolError, OSError) as exc:
        raise UpdateError(f"Stopped at '{stage}': {exc}. Keep the device powered; no automatic retry or cleanup reboot.") from None
    except KeyboardInterrupt:
        raise UpdateError(f"Interrupted at '{stage}'. Keep the device powered; no automatic retry or cleanup reboot.") from None
    finally:
        device.close()
