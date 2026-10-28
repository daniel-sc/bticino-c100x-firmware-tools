"""One managed USB session: readiness, route checks, supervision and local cleanup."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

from .resources import child_command


class USBError(OSError):
    pass


class Session:
    def __init__(self, process):
        self.process = process
        self.condition = threading.Condition()
        self.interface = None
        self.ended = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while line := self.process.stdout.readline(4097):
                if len(line) > 4096:
                    break
                event = json.loads(line)
                interface = event["interface"]
                if interface is not None and not re.fullmatch(r"feth[0-9]+", interface):
                    break
                with self.condition:
                    self.interface = interface
                    self.condition.notify_all()
        except (OSError, ValueError, KeyError, TypeError):
            pass
        finally:
            with self.condition:
                self.ended = True
                self.condition.notify_all()

    def check(self, timeout: float = 10) -> None:
        """Wait for transport and require the destination route to our current feth."""
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.interface is None and not self.ended:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise USBError("USB networking is not ready; check the cable and device power")
                self.condition.wait(remaining)
            if self.ended or self.process.poll() is not None:
                raise USBError("USB supervisor stopped; no update command was retried")
            interface = self.interface
        try:
            route = subprocess.run(["/sbin/route", "-n", "get", "192.168.129.1"],
                                   capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            raise USBError("USB route verification timed out") from None
        match = re.search(r"^\s*interface:\s*(\S+)\s*$", route.stdout, re.MULTILINE)
        with self.condition:
            if (self.ended or self.interface != interface or route.returncode
                    or not match or match[1] != interface):
                raise USBError("Intercom route is not through the managed USB interface")


@contextmanager
def usb_session(binary: Path):
    if os.geteuid() != 0:
        raise PermissionError("USB networking needs root; run plan/flash with sudo")
    binary = binary.resolve(strict=True)
    previous = {}

    def interrupt(signum, frame):
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        raise KeyboardInterrupt

    process = None
    session = None
    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, interrupt)
        process = subprocess.Popen(child_command("_usb-worker", str(binary)),
                                   stdout=subprocess.PIPE, text=True, start_new_session=True)
        session = Session(process)
        print("Waiting for USB networking…", file=sys.stderr)
        session.check(timeout=45)
        print("USB networking ready", file=sys.stderr)
        yield session.check
    finally:
        try:
            if process is not None:
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        # Worker and helper share an isolated process group.
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                        print("USB supervisor forced to stop; local interface cleanup is unverified", file=sys.stderr)
                if session is not None:
                    session.reader.join(timeout=2)
                process.stdout.close()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
