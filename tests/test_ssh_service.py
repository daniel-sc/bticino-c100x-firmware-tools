"""Execute the SSH init scripts offline with simulated process-control effects."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


SERVICE = Path(__file__).resolve().parents[1] / "payloads/ssh/files/init.sh"
# Vendor-free fixture for the pinned stock script's configuration gate and dispatch.
VENDOR_INIT = '''#!/bin/sh
NO_START=0
. "/etc/default/dropbear"
test "$NO_START" = 0 || exit 0
case "$1" in
    start) start-stop-daemon -S -p "/var/run/dropbear.pid" -x "/usr/sbin/dropbear" ;;
    stop) start-stop-daemon -K -p "/var/run/dropbear.pid" -x "/usr/sbin/dropbear" ;;
esac
'''


class SSHServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ssh service ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "mock-bin"
        self.bin.mkdir()
        for name in ("etc/default", "etc/dropbear", "usr/sbin", "var/run"):
            (self.root / name).mkdir(parents=True)
        self.key = self.root / "etc/dropbear/classe100x_ecdsa_host_key"
        self.key.write_text("simulated existing key")
        self.config = self.root / "etc/default/c100x-ssh"
        self.config.write_text("PASSWORD_AUTH=1\n")
        (self.root / "etc/default/dropbear").write_text("NO_START=1\n")
        (self.root / "usr/sbin/dropbear").write_text("fixture")
        (self.root / "usr/sbin/dropbear").chmod(0o755)
        self.state = self.root / "state.json"
        self.events = self.root / "events.jsonl"
        # Simulate BusyBox matching by both executable and pidfile. No real process
        # is signalled, and no device executable is run on the host.
        mock = self.bin / "start-stop-daemon"
        mock.write_text(f'''#!{sys.executable}
import json, os, pathlib, sys
a = sys.argv[1:]
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
state = root / "state.json"
current = json.loads(state.read_text()) if state.exists() else None
pidfile = a[a.index("-p") + 1]
daemon = a[a.index("-x") + 1]
matches = bool(current and current["pidfile"] == pidfile and current["daemon"] == daemon)
if "-t" in a:
    sys.exit(0 if matches else 1)
with (root / "events.jsonl").open("a") as f:
    f.write(json.dumps(a) + "\\n")
if "-S" in a:
    if (root / "fail-start").exists(): sys.exit(1)
    if matches: sys.exit(1)
    state.write_text(json.dumps({{"pidfile": pidfile, "daemon": daemon, "args": a}}))
    pathlib.Path(pidfile).write_text("1234\\n")
elif "-K" in a:
    if not matches: sys.exit(1)
    if not (root / "stuck-stop").exists():
        state.unlink()
        pathlib.Path(pidfile).unlink()
else:
    sys.exit(99)
''')
        mock.chmod(0o755)
        sleep = self.bin / "sleep"
        sleep.write_text("#!/bin/sh\nexit 0\n")
        sleep.chmod(0o755)
        self.service = self.rebase(SERVICE.read_text(), "service")
        self.vendor = self.rebase(VENDOR_INIT, "vendor")
        self.env = {**os.environ, "PATH": f"{self.bin}:/usr/bin:/bin", "FIXTURE_ROOT": str(self.root)}

    def rebase(self, text, name):
        text = re.sub(r"/(?:etc|var|usr/sbin)/", lambda match: str(self.root) + match[0], text)
        text = "\n".join(f'PATH="{self.bin}:/usr/bin:/bin"' if line.startswith("PATH=") else line
                         for line in text.splitlines()) + "\n"
        path = self.root / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def invoke(self, action, *, script=None, status=0):
        result = subprocess.run(["/bin/sh", str(script or self.service), action],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        return result

    def test_vendor_calls_cannot_disable_listener_in_either_order(self):
        for vendor_first in (True, False):
            with self.subTest(vendor_first=vendor_first):
                self.invoke("stop")
                if vendor_first:
                    self.invoke("stop", script=self.vendor)
                self.invoke("start")
                before = self.events.read_bytes()
                for action in ("start", "stop", "restart", "stop"):
                    self.invoke(action, script=self.vendor)
                    self.invoke("status")
                self.assertEqual(self.events.read_bytes(), before)
                self.assertTrue(self.state.exists())

    def test_idempotent_start_restart_and_shutdown_own_the_pidfile(self):
        self.invoke("start")
        before = self.events.read_bytes()
        self.invoke("start")
        self.assertEqual(self.events.read_bytes(), before)
        args = json.loads(self.state.read_text())["args"]
        self.assertEqual(args[args.index("-P") + 1], str(self.root / "var/run/c100x-ssh.pid"))
        self.assertEqual(args[args.index("-r") + 1], str(self.key))
        self.assertNotIn("-s", args)
        self.invoke("restart")
        self.invoke("status")
        self.invoke("stop")
        self.invoke("stop")
        self.invoke("status", status=3)
        self.assertFalse(self.state.exists())

    def test_authentication_modes_and_start_failures(self):
        self.config.write_text("PASSWORD_AUTH=0\n")
        self.invoke("start")
        self.assertIn("-s", json.loads(self.state.read_text())["args"])
        self.invoke("stop")
        self.key.unlink()
        self.invoke("start", status=1)
        self.assertFalse(self.state.exists())
        self.key.write_text("fixture")
        (self.root / "fail-start").touch()
        self.invoke("start", status=1)
        self.assertFalse(self.state.exists())

    def test_failed_stop_blocks_restart_and_stop_does_not_need_config_or_key(self):
        self.invoke("start")
        (self.root / "stuck-stop").touch()
        before = len(self.events.read_text().splitlines())
        self.invoke("restart", status=1)
        events = [json.loads(line) for line in self.events.read_text().splitlines()][before:]
        self.assertFalse(any("-S" in event for event in events))
        (self.root / "stuck-stop").unlink()
        self.config.unlink()
        self.key.unlink()
        self.invoke("stop")
        self.assertFalse(self.state.exists())
