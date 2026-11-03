"""Best-effort host-only unmount of storage belonging to the C100X USB device."""

import plistlib
import re
import subprocess
import sys
import time


def unmount_usb_storage(*, warn=lambda text: print(text, file=sys.stderr)):
    """Ordinary unmount only, with a total 10-second budget; never eject USB."""
    if sys.platform != "darwin":
        return
    deadline = time.monotonic() + 10

    def run(command):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("USB storage preparation", 10)
        result = subprocess.run(command, capture_output=True, timeout=min(5, remaining))
        if result.returncode:
            raise OSError("USB storage command failed")
        return result.stdout

    def discover():
        data = run(["/usr/sbin/ioreg", "-a", "-r", "-c", "IOUSBHostDevice"])
        if not data.strip():
            return None
        devices = [node for node in plistlib.loads(data)
                   if node.get("idVendor") == 0x1da4 and node.get("idProduct") == 0x0056]
        if not devices:
            return None
        if len(devices) != 1:
            raise ValueError("Ambiguous USB device")
        media = []

        def visit(node):
            if node.get("IOObjectClass") == "IOMedia" and node.get("Whole") is True:
                media.append(node)
            for child in node.get("IORegistryEntryChildren", []):
                visit(child)

        visit(devices[0])
        if not media:
            return None
        if len(media) != 1:
            raise ValueError("Ambiguous USB storage")
        disk = media[0].get("BSD Name", "")
        usb_id, media_id = devices[0].get("IORegistryEntryID"), media[0].get("IORegistryEntryID")
        if (not re.fullmatch(r"disk[0-9]+", disk)
                or not isinstance(usb_id, int) or not isinstance(media_id, int)):
            raise ValueError("Unidentified USB storage")
        return disk, usb_id, media_id

    def mounted(node):
        if isinstance(node, dict):
            return bool(node.get("MountPoint")) or any(mounted(value) for value in node.values())
        return isinstance(node, list) and any(mounted(value) for value in node)

    try:
        original = discover()
        if original is None:
            return
        disk = original[0]
        listing = plistlib.loads(run(["/usr/sbin/diskutil", "list", "-plist", "/dev/" + disk]))
        roots = listing["AllDisksAndPartitions"]
        if len(roots) != 1 or roots[0]["DeviceIdentifier"] != disk:
            raise ValueError("Disk identity changed")
        if not mounted(roots[0]):
            return
        # Disk numbers can be reused. Require the same USB and media registry
        # identities immediately before acting; names and volume labels are not identity.
        if discover() != original:
            raise ValueError("USB storage changed during discovery")
        run(["/usr/sbin/diskutil", "unmountDisk", "/dev/" + disk])
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, AttributeError):
        warn("Warning: C100X USB storage unmount was skipped or failed; continuing the planned reboot")
