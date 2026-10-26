import argparse
import getpass
import json
from pathlib import Path
import subprocess
import sys

from .firmware import FirmwareError, prepare_firmware
from .protocol import ProtocolError, ReadOnlyClient
from .transport import run_usb
from .updater import NetworkDevice, UpdateError, check_identity, flash
from .vendor import key_from_builder, load_profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Classe 100X native macOS firmware CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe", help="Read-only device identification and update status")
    probe.add_argument("--host", default="192.168.129.1")
    probe.add_argument("--port", type=int, default=20000)
    probe.add_argument("--timeout", type=float, default=5.0)
    usb = commands.add_parser("usb", help="Maintain native USB networking across device reboots (root)")
    usb.add_argument("--tetherkit", type=Path, default=Path(".local/tetherkit-build/bin/tetherkit-cli"))
    for name, help_text in (
        ("inspect-fw", "Validate firmware and calculate payload checksums offline"),
        ("plan", "Validate firmware, vendor settings and device identity without device writes"),
        ("flash", "Write recovery and main firmware, including recovery-mode transition and reboots"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("firmware", type=Path)
        command.add_argument("--key-from-builder", type=Path, help="Read the archive key from an existing legacy main.py; otherwise prompt")
        if name != "inspect-fw":
            command.add_argument("--myhome-installer", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "probe":
            with ReadOnlyClient(args.host, args.port, args.timeout) as client:
                print(json.dumps(client.inspect(), indent=2))
        elif args.command == "usb":
            run_usb(args.tetherkit)
        else:
            profile = None
            if args.command != "inspect-fw":
                try:
                    profile = load_profile(args.myhome_installer)
                except ImportError:
                    raise ValueError("Run mise run setup, then use .venv/bin/python for this command") from None
                except Exception:
                    raise ValueError("Unable to read the researched C100X settings from the MyHOME installer") from None
            if args.key_from_builder:
                key = key_from_builder(args.key_from_builder)
            else:
                if not sys.stdin.isatty():
                    raise ValueError("Archive-key prompt needs a terminal, or use --key-from-builder")
                key = getpass.getpass("FWZ archive key: ").encode()
            print("Validating the complete firmware archive…", file=sys.stderr)
            local = Path(".local")
            local.mkdir(exist_ok=True)
            with prepare_firmware(args.firmware, key, temporary_parent=local) as firmware:
                if args.command == "inspect-fw":
                    print(json.dumps(firmware.report(), indent=2))
                elif args.command == "plan":
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
                    flash(firmware, NetworkDevice("192.168.129.1"), profile,
                          report=lambda text: print(text, flush=True))
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
