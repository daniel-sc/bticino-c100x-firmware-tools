import argparse
from contextlib import nullcontext
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys

from .firmware import PROFILE, FirmwareError, prepare_firmware, regular_file
from .protocol import ProtocolError, ReadOnlyClient
from .transport import run_usb
from .resources import tetherkit, version
from .usb_session import usb_session
from .updater import NetworkDevice, UpdateError, check_identity, flash
from .vendor import C100X_PROFILE


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "_usb-worker":
        def notify(interface):
            print(json.dumps({"interface": interface}), flush=True)
        try:
            run_usb(Path(sys.argv[2]), notify=notify)
        except KeyboardInterrupt:
            return 130
        return 0
    parser = argparse.ArgumentParser(description="Classe 100X native macOS firmware CLI")
    parser.add_argument("--version", action="version", version=f"c100x {version()}")
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe", help="Read-only device identification and update status")
    probe.add_argument("--host", default="192.168.129.1")
    probe.add_argument("--port", type=int, default=20000)
    probe.add_argument("--timeout", type=float, default=5.0)
    usb = commands.add_parser("usb", help="Maintain native USB networking across device reboots (root)")
    usb.add_argument("--tetherkit", type=Path, default=tetherkit())
    fetch = commands.add_parser("fetch-fw", help="Download/cache the hash-pinned original stock image")
    fetch.add_argument("--stock", choices=[PROFILE], default=PROFILE)
    fetch.add_argument("--cache", type=Path, default=Path(".local/firmware-cache"))
    doctor = commands.add_parser("builder-doctor", help="Show builder tool paths and versions; no device access")
    build = commands.add_parser("build-fw", help="Build a new FWZ from pinned stock using trusted local payloads")
    build.add_argument("firmware", type=Path, nargs="?")
    build.add_argument("--stock", choices=[PROFILE], help="Fetch/cache the selected stock image if needed")
    build.add_argument("--cache", type=Path, default=Path(".local/firmware-cache"))
    build.add_argument("--payload", action="append", default=[], help="Bundled name or trusted local directory, in application order")
    build.add_argument("--inputs", type=Path, help="Private JSON object mapping payload IDs to inputs")
    build.add_argument("--ssh-public-key", type=Path, help="Public login key for the explicitly selected ssh payload")
    build.add_argument("--ssh-password", action="store_true", help="Prompt privately for the ssh payload login password")
    build.add_argument("--ssh-password-file", type=Path, help="Read ssh login password from a private file")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--report", type=Path, help="Optional redacted build report (must not already exist)")
    for command in (build, doctor):
        command.add_argument("--debugfs", help="Explicit debugfs executable")
        command.add_argument("--e2fsck", help="Explicit e2fsck executable")
        command.add_argument("--sevenzip", help="Explicit 7zz/7z executable")
    for name, help_text in (
        ("inspect-fw", "Validate firmware and calculate payload checksums offline"),
        ("plan", "Validate firmware and device identity without device writes"),
        ("flash", "Write recovery and main firmware, including recovery-mode transition and reboots"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("firmware", type=Path)
        if name in ("plan", "flash"):
            command.add_argument("--tetherkit", type=Path, default=tetherkit(), help="Override the USB helper executable")
            command.add_argument("--external-usb", action="store_true", help="Advanced: use an already running USB supervisor")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "fetch-fw":
            from .download import fetch_stock
            from .builder import interrupted_build
            with interrupted_build():
                print(fetch_stock(args.cache))
        elif args.command == "builder-doctor":
            from .builder import builder_tools, tool_versions
            from .host import find_tool, run_tool
            tools = builder_tools({"debugfs": args.debugfs, "e2fsck": args.e2fsck, "7zip": args.sevenzip})
            result = {"paths": tools, "versions": tool_versions(tools), "ssh_tools": {}}
            for name, options in (("dropbearkey", ["-h"]), ("openssl", ["version"])):
                try:
                    path = find_tool(name)
                    _, out, err = run_tool([path, *options], timeout=10)
                    text = (out + err).decode(errors="replace").splitlines()
                    if name == "dropbearkey":
                        help_text = "\n".join(text)
                        result["ssh_tools"][name] = {"path": path, "version": "not reported by keygen",
                                                     "ecdsa_p256": "ecdsa" in help_text and "256" in help_text}
                    else:
                        _, out, err = run_tool([path, "passwd", "-help"], timeout=10)
                        result["ssh_tools"][name] = {"path": path, "version": text[0][:200] if text else "unknown",
                                                     "sha512_crypt": b"-6" in out + err}
                except FirmwareError:
                    result["ssh_tools"][name] = {"available": False}
            print(json.dumps(result, indent=2))
        elif args.command == "build-fw":
            if os.geteuid() == 0:
                raise ValueError("Build firmware as your ordinary user, without sudo")
            from .builder import build, interrupted_build, resolve_payload
            from .download import fetch_stock
            if bool(args.firmware) == bool(args.stock):
                raise ValueError("Supply either a local firmware path or --stock")
            inputs, input_base = {}, Path.cwd()
            if args.inputs:
                with regular_file(args.inputs) as stream:
                    data = stream.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise ValueError("Payload inputs exceed the size limit")
                inputs = json.loads(data)
                if not isinstance(inputs, dict):
                    raise ValueError("Payload inputs must be an object")
                input_base = args.inputs.resolve().parent
            if args.ssh_public_key or args.ssh_password or args.ssh_password_file:
                ssh = inputs.setdefault("ssh", {})
                if not isinstance(ssh, dict):
                    raise ValueError("SSH inputs must be an object")
                if args.ssh_public_key:
                    ssh["public_key"] = str(args.ssh_public_key.expanduser().resolve())
                if args.ssh_password_file:
                    ssh["password_file"] = str(args.ssh_password_file.expanduser().resolve())
                if args.ssh_password:
                    if not sys.stdin.isatty():
                        raise ValueError("Password prompt needs a terminal; use a private password file")
                    ssh["password"] = getpass.getpass("New root2 SSH password: ")
            with interrupted_build():
                source = fetch_stock(args.cache) if args.stock else args.firmware
                result = build(source, args.output, payloads=[resolve_payload(p) for p in args.payload],
                               inputs=inputs, input_base=input_base,
                               overrides={"debugfs": args.debugfs, "e2fsck": args.e2fsck, "7zip": args.sevenzip},
                               report_path=args.report, progress=lambda msg: print(msg, file=sys.stderr))
            print(json.dumps(result, indent=2))
        elif args.command == "probe":
            with ReadOnlyClient(args.host, args.port, args.timeout) as client:
                print(json.dumps(client.inspect(), indent=2))
        elif args.command == "usb":
            run_usb(args.tetherkit)
        else:
            print("Validating the complete firmware archive…", file=sys.stderr)
            with prepare_firmware(args.firmware) as firmware:
                if args.command == "inspect-fw":
                    print(json.dumps(firmware.report(), indent=2))
                else:
                    session = nullcontext(lambda: None) if args.external_usb else usb_session(args.tetherkit)
                    with session as check_transport:
                        check_transport()
                        if args.command == "plan":
                            with ReadOnlyClient("192.168.129.1") as client:
                                info = client.inspect()
                            check_identity(info, 4)
                            print(json.dumps({
                                "firmware": firmware.report(), "device": info,
                                "sequence": ["recovery filesystem", "recovery kernel", "reboot to normal",
                                             "clear main kernel", "reboot to recovery", "main filesystem",
                                             "main kernel", "reboot to normal"],
                                "device_writes": False,
                            }, indent=2))
                        else:
                            flash(firmware, NetworkDevice("192.168.129.1", check_transport=check_transport),
                                  C100X_PROFILE, report=lambda text: print(text, flush=True))
        return 0
    except (FirmwareError, UpdateError, ProtocolError, OSError, ValueError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1
    except subprocess.SubprocessError:
        print(f"{args.command} failed: local helper did not complete successfully", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
