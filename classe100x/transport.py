"""Supervise the pinned TetherKit CLI across expected USB re-enumerations."""

import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

PAIR_READY = re.compile(r"virtual interface pair ready: system side (feth[0-9]+) <-> driver side feth[0-9]+")


def run_usb(binary: Path) -> None:
    if os.geteuid() != 0:
        raise PermissionError("USB networking needs root; run the usb command with sudo")
    binary = binary.resolve(strict=True)
    previous = {}

    def interrupt(signum, frame):
        # Let finally stop/reap the isolated child even when the terminal closes.
        # A second termination signal must not interrupt that cleanup.
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        raise KeyboardInterrupt

    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, interrupt)
        _supervise(binary)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _supervise(binary: Path) -> None:
    while True:
        process = subprocess.Popen(
            [str(binary), "--vid", "1da4", "--pid", "0056", "--lang", "en", "--no-color", "--stats", "0"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,
        )
        try:
            for line in process.stdout:
                print(line.rstrip(), flush=True)
                match = PAIR_READY.search(line)
                if match:
                    interface = match.group(1)
                    subprocess.run(
                        ["/sbin/ifconfig", interface, "inet", "192.168.129.2", "netmask", "255.255.255.252", "up"],
                        check=True, capture_output=True, timeout=10,
                    )
                    print(f"USB network ready on {interface}: 192.168.129.2/30", flush=True)
            process.wait()
        finally:
            try:
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                        print("USB helper required forced termination; feth cleanup is unverified", file=sys.stderr)
            finally:
                process.stdout.close()
        print("Waiting for the intercom USB connection…", flush=True)
        time.sleep(2)
