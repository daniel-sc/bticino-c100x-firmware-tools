"""One managed USB session: readiness, route checks, supervision and local cleanup."""

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import sys
import threading
import time

from .resources import child_command
from .diagnostics import TEXT_LIMIT, details, text, tool_error


class USBError(OSError):
    pass


def native_usb_interface():
    """Find a macOS-owned Ethernet interface beneath exactly one C100X USB device."""
    try:
        result = subprocess.run(["/usr/sbin/ioreg", "-a", "-r", "-c", "IOUSBHostDevice"],
                                capture_output=True, timeout=5)
        if result.returncode:
            raise tool_error(USBError("Could not inspect native USB networking"), "ioreg", result.returncode, result.stderr)
        if not result.stdout.strip():
            return None
        devices = [node for node in plistlib.loads(result.stdout)
                   if node.get("idVendor") == 0x1da4 and node.get("idProduct") == 0x0056]
    except (subprocess.TimeoutExpired, ValueError, TypeError, plistlib.InvalidFileException) as exc:
        raise USBError("Could not inspect native USB networking") from exc
    if len(devices) > 1:
        raise USBError("Connect only one C100X USB device")
    interfaces = set()

    def visit(node):
        if node.get("IOObjectClass") in ("IOEthernetInterface", "IOSkywalkLegacyEthernetInterface"):
            name = node.get("BSD Name", node.get("IORegistryEntryName", ""))
            if re.fullmatch(r"en[0-9]+", name):
                interfaces.add(name)
        for child in node.get("IORegistryEntryChildren", []):
            visit(child)

    for device in devices:
        visit(device)
    if len(interfaces) > 1:
        raise USBError("C100X native USB network interface is ambiguous")
    return next(iter(interfaces), None)


def check_native_usb(interface):
    """Configure only the discovered USB interface; reject any other destination route."""
    try:
        configured = subprocess.run(["/sbin/ifconfig", interface], capture_output=True,
                                    text=True, timeout=5)
        address = r"\binet 192\.168\.129\.2 netmask 0xfffffffc\b"
        if configured.returncode or not re.search(address, configured.stdout):
            result = subprocess.run(["/sbin/ifconfig", interface, "inet", "192.168.129.2",
                                     "netmask", "255.255.255.252", "up"],
                                    capture_output=True, timeout=5)
            if result.returncode:
                raise details(tool_error(USBError("Could not configure the native C100X USB interface"),
                                         "ifconfig", result.returncode, result.stderr), interface=interface)
        route = subprocess.run(["/sbin/route", "-n", "get", "192.168.129.1"],
                               capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise USBError("Native USB network check timed out") from exc
    match = re.search(r"^\s*interface:\s*(\S+)\s*$", route.stdout, re.MULTILINE)
    if route.returncode or not match or match[1] != interface:
        raise details(tool_error(USBError("Intercom route is not through the native C100X USB interface"),
                                 "route", route.returncode, route.stderr, stdout=route.stdout),
                      expected_interface=interface)


@contextmanager
def usb_session(binary: Path):
    """Own USB networking across normal RNDIS and recovery native ECM boots."""
    if os.geteuid() != 0:
        raise PermissionError("USB networking needs root; run the device command with sudo")
    binary = binary.resolve(strict=True)
    helper = None
    helper_failed = False
    ready = None
    previous = {}

    def interrupt(signum, frame):
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        raise KeyboardInterrupt

    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, interrupt)
        with ExitStack() as stack:
            def check(timeout=10):
                nonlocal helper, helper_failed, ready
                if helper_failed:
                    raise USBError("USB helper startup failed; reconnection is unverified")
                deadline = time.monotonic() + timeout
                while True:
                    interface = native_usb_interface()
                    if interface is not None:
                        if helper is not None:
                            # Release the old feth route before configuring ECM.
                            stack.close()
                            helper = None
                            # Cleanup may overlap re-enumeration; never configure
                            # an interface that no longer belongs to this USB device.
                            interface = native_usb_interface()
                        if interface is not None:
                            check_native_usb(interface)
                            if ready != interface:
                                print(f"USB networking ready on {interface} (native ECM)", file=sys.stderr)
                            ready = interface
                            return
                    if helper is None:
                        helper_failed = True
                        helper = stack.enter_context(_helper_session(binary))
                        helper_failed = False
                    try:
                        # Do not block in the feth-only waiter: recovery may now
                        # be available through ECM while the helper waits for RNDIS.
                        helper.check(timeout=0)
                    except USBError:
                        if helper.ended or helper.process.poll() is not None or time.monotonic() >= deadline:
                            raise
                        time.sleep(min(0.2, max(0, deadline - time.monotonic())))
                        continue
                    if ready != helper.interface:
                        print(f"USB networking ready on {helper.interface} (RNDIS helper)", file=sys.stderr)
                    ready = helper.interface
                    return

            print("Waiting for USB networking…", file=sys.stderr)
            check(timeout=45)
            yield check
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


class Session:
    def __init__(self, process):
        self.process = process
        self.condition = threading.Condition()
        self.interface = None
        self.ended = False
        self.diagnostic = ""
        self.reader_error = None
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while line := self.process.stdout.readline(4097):
                if len(line) > 4096:
                    raise ValueError("USB worker message exceeds 4096 characters")
                event = json.loads(line)
                if "diagnostic" in event:
                    if not isinstance(event["diagnostic"], str):
                        raise ValueError("Invalid USB worker diagnostic")
                    with self.condition:
                        self.diagnostic = text(self.diagnostic + event["diagnostic"] + "\n", limit=TEXT_LIMIT)
                    continue
                interface = event["interface"]
                if interface is not None and not re.fullmatch(r"feth[0-9]+", interface):
                    raise ValueError("Invalid USB worker interface")
                with self.condition:
                    self.interface = interface
                    self.condition.notify_all()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.reader_error = exc
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
                    raise details(USBError("USB networking is not ready; check the cable and device power"),
                                  helper_output=self.diagnostic)
                self.condition.wait(remaining)
            if self.ended or self.process.poll() is not None:
                raise details(USBError("USB supervisor stopped; no update command was retried"),
                              exit_status=self.process.poll(), helper_output=self.diagnostic) from self.reader_error
            interface = self.interface
        try:
            route = subprocess.run(["/sbin/route", "-n", "get", "192.168.129.1"],
                                   capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise USBError("USB route verification timed out") from exc
        match = re.search(r"^\s*interface:\s*(\S+)\s*$", route.stdout, re.MULTILINE)
        with self.condition:
            if (self.ended or self.interface != interface or route.returncode
                    or not match or match[1] != interface):
                raise details(tool_error(USBError("Intercom route is not through the managed USB interface"),
                                         "route", route.returncode, route.stderr, stdout=route.stdout),
                              expected_interface=interface, helper_output=self.diagnostic)


@contextmanager
def _helper_session(binary: Path):
    """Start without waiting for feth, allowing the owner to notice native ECM."""
    process = None
    session = None
    try:
        process = subprocess.Popen(child_command("_usb-worker", str(binary)),
                                   stdout=subprocess.PIPE, text=True, start_new_session=True)
        session = Session(process)
        yield session
    finally:
        if process is not None:
            # ExitStack removes this callback before running it during a handover.
            # Defer cancellation until teardown is complete: it cannot be resumed
            # by the outer context if a signal interrupts process.wait().
            interrupted = False
            previous = {}

            def defer(signum, frame):
                nonlocal interrupted
                interrupted = True

            try:
                for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                    previous[sig] = signal.getsignal(sig)
                    if previous[sig] != signal.SIG_IGN:
                        signal.signal(sig, defer)
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
            if interrupted:
                raise KeyboardInterrupt
