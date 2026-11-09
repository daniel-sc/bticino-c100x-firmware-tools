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
from .source_profiles import SourceProfile
from .diagnostics import details, format_failure, remember_secret


class UpdateError(Exception):
    pass


class UncertainDelivery(UpdateError):
    pass


class ForwardedFTP(ftplib.FTP):
    """Keep passive data on the authenticated loopback forward, never PASV's host."""
    data_port = None

    def makepasv(self):
        _, port = super().makepasv()
        if port != 11111:
            raise UpdateError("Unexpected vendor passive FTP port")
        return "127.0.0.1", self.data_port


def uptime_seconds(values: tuple[str, ...]) -> int:
    try:
        days, hours, minutes, seconds = map(int, values)
        if days < 0 or not (0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 60):
            raise ValueError
        return days * 86400 + hours * 3600 + minutes * 60 + seconds
    except (TypeError, ValueError) as exc:
        raise details(UpdateError("Invalid device uptime"), received=values) from exc


def check_identity(info: dict, expected_status: int, *, source_versions=None) -> None:
    """Check the device identity.

    source_versions: firmware versions accepted instead of the target, used only while the
    still-running source MAIN is checked. Every other field stays strict.
    """
    expected = {
        "device_type": (200,), "firmware": (1, 5, 8),
        "hardware": (2,), "object_model": (1, 0, 99),
        "update_status": (expected_status, 0),
    }
    for key, value in expected.items():
        try:
            actual = tuple(int(part) for part in info[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise UpdateError(f"Missing or invalid {key} in device identity") from exc
        if key == "hardware":
            if len(actual) != 3 or any(part < 0 for part in actual):
                raise UpdateError("Missing or invalid hardware in device identity")
            # MyHOME BTESUXP compares only the hardware family (PrecisionRequired.v).
            # Revision coverage is recorded separately in docs/ACCEPTANCE.md.
            matches = actual[:1] == value
            expected_value = "family 02.*.*"
        elif key == "firmware" and source_versions is not None:
            matches = actual in source_versions
            expected_value = "one of " + ", ".join(
                ".".join(map(str, version)) for version in sorted(source_versions))
        else:
            matches = actual == value
            expected_value = value
        if not matches:
            raise UpdateError(f"Device {key} does not match the researched 1.5.8 update path: expected {expected_value}, received {actual}")


class UpdateClient(ReadOnlyClient):
    """Explicit write-capable client; the preflight client remains read-only."""

    def _once(self, frame: bytes, label: str) -> None:
        deadline = time.monotonic() + self.timeout
        try:
            self._send(frame, deadline)
            reply = self.stream.receive(deadline)
        except (ProtocolError, OSError) as exc:
            self.close()
            raise UncertainDelivery(f"Delivery of {label} is uncertain; command was not retried") from exc
        if reply != ACK:
            self.close()
            if reply == NACK:
                raise UpdateError(f"Device rejected {label}")
            raise UncertainDelivery(f"Unexpected reply to {label}; command was not retried")

    def begin(self, recovery: bool) -> None:
        self._once(b"*#13**#37*0##" if recovery else b"*#13**#36*0##", "start transfer")

    def commit(self, payload: Payload) -> None:
        self._once(f"*#13**#35*{payload.size}*0*{payload.cksum}##".encode(), "start payload write")

    def finish(self) -> None:
        self._once(b"*#13**#33*0##", "close FTP")

    def invalidate_main_kernel(self) -> None:
        self._once(b"*13*25**##", "enter recovery (clear main kernel)")

    def reboot(self) -> None:
        self._once(b"*#13**43##", "reboot")


class NetworkDevice:
    def __init__(self, host: str, port: int = 20000, *, timeout: float = 30,
                 reboot_timeout: float = 240, write_timeout: float = 180,
                 check_transport=lambda: None, before_reboot=None, transport=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.reboot_timeout, self.write_timeout = reboot_timeout, write_timeout
        self.client: UpdateClient | None = None
        self.check_transport = check_transport
        self.before_reboot = before_reboot
        self.transport = transport
        self.ftp_port, self.data_port = 21, None

    def _transport_ready(self):
        self.check_transport()
        if self.transport is not None:
            self.host, self.port, self.ftp_port, self.data_port = self.transport.endpoints()

    def connect(self) -> dict:
        self.reconnect()
        return self.client.inspect()

    def reconnect(self) -> None:
        """Replace the command session without restarting the device transfer."""
        self.close()
        self._transport_ready()
        client = UpdateClient(self.host, self.port, self.timeout)
        self.client = client.__enter__()

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def _connect_ftp(self, ftp):
        # The vendor start-transfer ACK follows a background vsftpd launch,
        # not listener readiness. An SSH forward reports remote refusal as EOF.
        # Only connect/banner reads are repeatable; never retry login or upload.
        # This is a polling budget; in-flight socket/transport checks may overrun.
        deadline = time.monotonic() + 10
        last_error = None
        while (remaining := deadline - time.monotonic()) > 0:
            self._transport_ready()
            try:
                greeting = ftp.connect(self.host, self.ftp_port, timeout=min(2, remaining))
            except (EOFError, ConnectionRefusedError, ConnectionResetError, TimeoutError) as exc:
                last_error = exc
                ftp.close()
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
                continue
            ftp.timeout = 30
            ftp.sock.settimeout(30)
            return greeting
        raise UpdateError("FTP greeting readiness budget exhausted (10 seconds); payload write was not requested") from last_error

    def upload(self, path: Path, credentials: Credentials) -> None:
        # FTP starts only after the explicit begin command. Each worker consumes
        # and deletes its input, so exactly one file must be present at commit.
        self._transport_ready()
        remember_secret(credentials.password)
        operation = "connect"
        try:
            factory = ForwardedFTP if self.data_port is not None else ftplib.FTP
            with factory(timeout=30) as ftp:
                if self.data_port is not None:
                    ftp.data_port = self.data_port
                self._connect_ftp(ftp)
                operation = "login"
                ftp.login(credentials.username, credentials.password)
                operation = "inspect staging directory"
                ftp.set_pasv(True)
                if ftp.nlst():
                    raise UpdateError("FTP staging directory is not empty")
                operation = "upload " + path.name
                with path.open("rb") as source:
                    ftp.storbinary("STOR " + path.name, source, blocksize=65536)
                operation = "check uploaded size"
                ftp.voidcmd("TYPE I")
                actual, expected = ftp.size(path.name), path.stat().st_size
                if actual != expected:
                    raise UpdateError(f"FTP payload length mismatch: expected {expected}, received {actual}")
                operation = "check uploaded directory"
                if ftp.nlst() != [path.name]:
                    raise UpdateError("Unexpected files in FTP staging directory")
                operation = "close FTP connection"
        except UpdateError as exc:
            details(exc, operation=operation, endpoint=f"{self.host}:{self.ftp_port}", payload=path.name)
            raise
        except ftplib.all_errors as exc:
            raise details(UpdateError("FTP transfer failed; payload write was not requested"),
                           operation=operation, endpoint=f"{self.host}:{self.ftp_port}", payload=path.name) from exc

    def wait_idle(self) -> None:
        deadline = time.monotonic() + self.write_timeout
        while True:
            self.check_transport()
            if self.client.idle():
                return
            if time.monotonic() >= deadline:
                raise UpdateError(f"Update worker is still busy after {self.write_timeout:g} seconds; no reboot was requested")
            time.sleep(5)

    def reboot_and_wait(self, status: int, *, source_versions=None) -> dict:
        self.check_transport()
        if self.before_reboot is not None:
            # Refresh openserver's 30-second idle timer before the bounded
            # (10-second total) host unmount. Sample reboot uptime afterward.
            self.client.query(19)
            self.before_reboot()
            self.check_transport()
        before = uptime_seconds(self.client.query(19))
        started = time.monotonic()
        self.client.reboot()
        self.close()
        if self.transport is not None:
            self.transport.rebooting(status)
        deadline = started + self.reboot_timeout
        last_error = None
        observation = None
        while time.monotonic() < deadline:
            time.sleep(1)
            try:
                self._transport_ready()
                with ReadOnlyClient(self.host, self.port, timeout=2) as probe:
                    info = probe.inspect()
            except (ProtocolError, OSError) as exc:
                from .ssh import HostIdentityError
                if isinstance(exc, HostIdentityError):
                    raise
                last_error = exc
                continue
            elapsed = time.monotonic() - started
            after = uptime_seconds(info["uptime"])
            # The firmware version is constant within one environment. An uptime reset distinguishes
            # a reboot from a stale reply or a transient network interruption.
            if after > elapsed + 2 or before + elapsed - after < 5:
                observation = f"uptime before={before}s, after={after}s, elapsed={elapsed:.1f}s; reset not established; status={info.get('update_status')}"
                last_error = None
                continue
            check_identity(info, status, source_versions=source_versions)
            if self.transport is not None:
                self.transport.arrived(status)
            info = self.connect()
            check_identity(info, status, source_versions=source_versions)
            return info
        raise details(UpdateError("Reboot/reconnection was not verified; no command was retried"),
                      timeout_seconds=self.reboot_timeout, expected_status=(status, 0),
                      last_observation=observation) from last_error

    def settle(self) -> None:
        # MyHOME waits 3 seconds after FTP close and 5 seconds before main reboot.
        time.sleep(8)


def flash(firmware: PreparedFirmware, device: NetworkDevice, profile: VendorProfile,
          report=print, *, verification=None, final_verification=None,
          source_versions=None) -> dict:
    """Three verified reboot boundaries; any failure stops subsequent writes."""
    return _flash(firmware, device, profile, report, verification=verification,
                  final_verification=final_verification, source_versions=source_versions)


def flash_recovery(firmware: PreparedFirmware, device: NetworkDevice, profile: VendorProfile,
                   report=print) -> dict:
    """Explicit main installation from already running recovery; never a write retry."""
    return _flash(firmware, device, profile, report, from_recovery=True)


def _flash(firmware, device, profile, report, *, verification=None, from_recovery=False,
           final_verification=None, source_versions=None):
    if from_recovery and source_versions:
        raise ValueError("Source firmware versions apply only to an update started from the normal MAIN")
    stage = "preflight"
    try:
        info = device.connect()
        check_identity(info, 1 if from_recovery else 4, source_versions=source_versions)
        if verification is not None and not from_recovery:
            verification.preflight()
            verification.update_result("in_progress", stage)
            # SSH work can outlast openserver's 30-second command idle timer.
            info = device.connect()
            check_identity(info, 4, source_versions=source_versions)
        transfers = (
            (True, RECOVERY_FILES, profile.normal),
            (False, MAIN_FILES, profile.recovery),
        )
        for recovery, names, credentials in transfers[1:] if from_recovery else transfers:
            target = "recovery" if recovery else "main"
            stage = f"{target}: starting transfer"
            report(stage)
            if from_recovery:
                if not device.client.idle():
                    raise UpdateError("Recovery update worker is busy; no transfer was started")
            else:
                device.wait_idle()
            device.client.begin(recovery)
            for name in names:
                payload = firmware.payload(name)
                stage = f"{target}: uploading {name}"
                report(stage)
                device.upload(firmware.directory / name, credentials)
                # Like the vendor updater, use a fresh command session after FTP:
                # an upload can outlast openserver's 30-second idle timeout.
                stage = f"{target}: reconnecting before writing {name}"
                report(stage)
                device.reconnect()
                stage = f"{target}: writing {name}"
                report(stage)
                device.client.commit(payload)
                device.wait_idle()
            stage = f"{target}: closing transfer"
            device.client.finish()
            device.settle()
            stage = f"{target}: rebooting"
            report(stage)
            # Only the transfer to recovery is followed by a reboot into the still-running
            # source MAIN, which may report a source version. Nothing else gets the argument.
            reboot_options = {"source_versions": source_versions} if recovery and source_versions else {}
            info = device.reboot_and_wait(4, **reboot_options)
            if recovery:
                if verification is not None:
                    stage = "recovery: verifying installed contents over SSH"
                    report(stage)
                    verification.verify()
                    stage = "recovery: reconnecting after SSH verification"
                    info = device.connect()
                    check_identity(info, 4, source_versions=source_versions)
                stage = "entering recovery: clearing main kernel"
                report(stage)
                device.client.invalidate_main_kernel()
                stage = "entering recovery: rebooting"
                report(stage)
                device.reboot_and_wait(1)
        if final_verification is not None:
            stage = "final destination SSH verification"
            report(stage)
            final_verification()
        stage = "update sequence completed"
        if verification is not None:
            verification.update_result("completed", stage)
        report("Update sequence completed; verify calls, audio/video, door release and any enabled SSH/MQTT features")
        return info
    except Exception as exc:
        if verification is not None:
            _record_stop(verification, stage, report)
        if not isinstance(exc, (UpdateError, ProtocolError, OSError)):
            details(exc, update_stage=stage,
                    device_state="Keep the device powered; no automatic retry or cleanup reboot")
            raise
        raise UpdateError(f"Stopped at '{stage}': {exc}. Keep the device powered; no automatic retry or cleanup reboot.") from exc
    except KeyboardInterrupt as exc:
        if verification is not None:
            _record_stop(verification, stage, report)
        raise UpdateError(f"Interrupted at '{stage}'. Keep the device powered; no automatic retry or cleanup reboot.") from exc
    finally:
        device.close()


def _record_stop(verification, stage, report):
    try:
        # The device sequence may have completed even if final report publication
        # failed. Preserve that distinction from an interrupted device operation.
        verification.update_result("completed" if stage == "update sequence completed" else "stopped", stage)
    except (OSError, UpdateError) as exc:
        report("Warning: could not save update outcome in the verification report\n" + format_failure(exc))


def check_source_identity(info: dict, profile: SourceProfile, expected_status: int) -> None:
    """Validate a running source MAIN against one explicit profile."""
    expected = {
        "device_type": profile.device_type,
        "firmware": profile.version,
        "object_model": profile.object_model,
        "update_status": (expected_status, 0),
    }
    for key, value in expected.items():
        try:
            actual = tuple(int(part) for part in info[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise UpdateError(f"Missing or invalid {key} in source identity") from exc
        if actual != value:
            raise UpdateError(
                f"Source {key} differs from profile {profile.version}: "
                f"expected {value}, received {actual}"
            )
    try:
        hardware = tuple(int(part) for part in info["hardware"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError("Missing or invalid hardware in source identity") from exc
    if len(hardware) != 3 or hardware[:1] != profile.hardware_family:
        raise UpdateError(
            f"Source hardware is outside profile family "
            f"{profile.hardware_family}: {hardware}"
        )


def _checked_source_main(device, verification, source_versions, mark, *, recording):
    """Everything that proves a resume is safe. Reads only: no write, no reboot."""
    mark("resume: checking the running source MAIN")
    info = device.connect()
    check_identity(info, 4, source_versions=source_versions)
    if not device.client.idle():
        raise UpdateError("Update worker is busy; resume stopped")
    verification.preflight()
    if recording:
        verification.update_result("in_progress", "resume: checking the running source MAIN")
    mark("resume: verifying the already written recovery over SSH")
    verification.verify()
    mark("resume: reconnecting after SSH verification")
    # The SSH readback can outlast the 30-second command idle timer: use a fresh session.
    info = device.connect()
    check_identity(info, 4, source_versions=source_versions)
    return info


def check_resume(device, verification, report=print, *, source_versions) -> dict:
    """Read-only plan of resume_recovery(): same checks, nothing is cleared, written or rebooted."""
    if not source_versions:
        raise ValueError("Resuming needs the source firmware versions matched by the preflight")
    try:
        return _checked_source_main(device, verification, source_versions, report, recording=False)
    finally:
        device.close()


def resume_recovery(firmware: PreparedFirmware, device: NetworkDevice, profile: VendorProfile,
                    report=print, *, verification, final_verification=None, source_versions) -> dict:
    """Continue an update whose recovery was written but whose main kernel was not cleared yet.

    The installed recovery is read back and proven identical to the firmware before anything is
    cleared; it is never written again. Source versions are accepted only until the main kernel is
    cleared. Afterwards this is the ordinary installation of the main system from recovery.
    """
    if not source_versions:
        raise ValueError("Resuming needs the source firmware versions matched by the preflight")
    stage = "resume: checking the running source MAIN"
    clear_attempted = False

    def mark(text):
        nonlocal stage
        stage = text
        report(text)

    try:
        _checked_source_main(device, verification, source_versions, mark, recording=True)
        mark("entering recovery: clearing main kernel")
        clear_attempted = True
        device.client.invalidate_main_kernel()
        mark("entering recovery: rebooting")
        device.reboot_and_wait(1)
    except (Exception, KeyboardInterrupt) as exc:
        device.close()
        _record_stop(verification, stage, report)
        state = "" if clear_attempted else " The main kernel was not cleared; the source MAIN is unchanged."
        if isinstance(exc, KeyboardInterrupt):
            raise UpdateError(f"Interrupted at '{stage}'.{state} Keep the device powered; "
                              "no automatic retry or cleanup reboot.") from exc
        if not isinstance(exc, (UpdateError, ProtocolError, OSError)):
            details(exc, update_stage=stage,
                    device_state="Keep the device powered; no automatic retry or cleanup reboot")
            raise
        raise UpdateError(f"Stopped at '{stage}': {exc}.{state} Keep the device powered; "
                          "no automatic retry or cleanup reboot.") from exc
    return _flash(firmware, device, profile, report, from_recovery=True, verification=verification,
                  final_verification=final_verification)
