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
from .usb_storage import unmount_usb_storage
from .updater import (NetworkDevice, UpdateError, check_identity, check_resume, flash, flash_recovery,
                      resume_recovery)
from .vendor import C100X_PROFILE
from .diagnostics import clear_secrets, failure, format_failure, text


def recovery_verification(args, firmware, check_transport):
    if args.command in ("plan-recovery", "recover") or not args.verify_recovery_ssh:
        return nullcontext(None)
    from .recovery import RecoveryVerifier
    from .ssh import SSHConnection
    password = None
    if args.ssh_password:
        if not sys.stdin.isatty():
            raise ValueError("SSH password verification needs an interactive terminal")
        password = getpass.getpass("Existing device SSH password (used again after reboot): ")
    connection = SSHConnection(args.ssh_user, key=args.ssh_key, password=password,
                               check_transport=check_transport,
                               warn=lambda text: print(text, file=sys.stderr))
    return RecoveryVerifier(firmware, connection, progress=lambda text: print(text, file=sys.stderr))


def wireless_command(args, firmware):
    from .wireless import Credentials, DEFAULT_HOST, Trust, Wireless, VerificationReader, awake, interruptible
    from .wireless_image import admit
    from .source_profiles import candidate_versions
    from .recovery import RecoveryVerifier

    def password(prompt):
        if not sys.stdin.isatty():
            raise ValueError("SSH password input needs an interactive terminal")
        return getpass.getpass(prompt)

    def confirm(host, fingerprint):
        if not sys.stdin.isatty():
            raise ValueError("First SSH identity enrollment requires an interactive terminal")
        print(f"First SSH identity for {host}: {fingerprint}", file=sys.stderr)
        return input("Trust this device fingerprint? Type yes: ") == "yes"

    existing = Credentials(args.ssh_user or "root2", key=args.ssh_key,
                           password=password("Existing device SSH password: ") if args.ssh_password else None)
    destination = Credentials(args.destination_ssh_user or existing.user,
                              key=args.destination_ssh_key if args.destination_ssh_key else
                              (None if args.destination_ssh_password else existing.key),
                              password=password("Destination images SSH password: ") if args.destination_ssh_password else
                              (None if args.destination_ssh_key else existing.password))
    host = args.host or DEFAULT_HOST
    wireless_options = {}
    if getattr(args, "accept_regenerated_host_key", False):
        wireless_options["accept_regenerated_key"] = True
        if args.ssh_password:
            print("Warning: if the intercom regenerates its SSH host key at boot, the key after the "
                  "reboot cannot be verified and the existing password is offered to whatever answers. "
                  "Prefer --ssh-key.", file=sys.stderr)
    progress = lambda text: print(text, file=sys.stderr, flush=True)
    try:
        with interruptible(), admit(firmware, destination) as image, Trust(host) as trust:
            with Wireless(host, existing, destination, image, trust, confirm=confirm, **wireless_options) as transport:
                reader = VerificationReader(transport)
                with RecoveryVerifier(firmware, reader, progress=progress) as verifier:
                    if args.command in ("plan-resume-recovery", "resume-recovery"):
                        # Interrupted after recovery was written and before the main kernel was cleared.
                        # Recovery is never written again: it is read back and verified first.
                        transport.resume_after_recovery()
                        device = NetworkDevice("127.0.0.1", transport=transport)
                        source_versions = candidate_versions(transport.source_candidates)
                        if args.command == "plan-resume-recovery":
                            info = check_resume(device, verifier, progress, source_versions=source_versions)
                            print(json.dumps({"firmware": firmware.report(), "device": info, "transport": "ssh",
                                              "resume_from": "recovery written, main kernel intact",
                                              "recovery_verification": verifier.record["verification"],
                                              "device_writes": False,
                                              "verification_report": str(verifier.directory / "report.json")},
                                             indent=2))
                        else:
                            with awake():
                                def final_verification():
                                    transport.verified()
                                    verifier.record["final_ssh"] = "verified"
                                resume_recovery(firmware, device, C100X_PROFILE, report=progress,
                                                verification=verifier, final_verification=final_verification,
                                                source_versions=source_versions)
                                transport.remember()
                    elif args.command == "plan":
                        endpoint, port, _, _ = transport.endpoints()
                        with ReadOnlyClient(endpoint, port) as client:
                            info = client.inspect()
                            check_identity(info, 4, source_versions=candidate_versions(
                                getattr(transport, "source_candidates", ())))
                            if not client.idle():
                                raise UpdateError("Update worker is busy; preflight stopped")
                        verifier.preflight()
                        print(json.dumps({"firmware": firmware.report(), "device": info, "transport": "ssh",
                                          "host": host, "vendor_updates": "allowed" if image.vendor_updates else "blocked",
                                          "device_writes": False, "verification_report": str(verifier.directory / "report.json")}, indent=2))
                    else:
                        with awake():
                            device = NetworkDevice("127.0.0.1", transport=transport)
                            def final_verification():
                                transport.verified()
                                verifier.record["final_ssh"] = "verified"
                            flash(firmware, device, C100X_PROFILE, report=progress, verification=verifier,
                                  final_verification=final_verification,
                                  source_versions=candidate_versions(getattr(transport, "source_candidates", ())))
                            transport.remember()
    finally:
        existing.password = destination.password = None


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "_usb-worker":
        def notify(interface):
            print(json.dumps({"interface": interface}), flush=True)
        def diagnostic(message):
            print(json.dumps({"diagnostic": text(message, limit=2000)}, ensure_ascii=False), flush=True)
        try:
            run_usb(Path(sys.argv[2]), notify=notify, diagnostic=diagnostic)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            diagnostic(format_failure(exc, debug=True))
            return 1
        return 0
    parser = argparse.ArgumentParser(description="Classe 100X native macOS firmware CLI")
    parser.add_argument("--version", action="version", version=f"c100x {version()}")
    parser.add_argument("--debug", action="store_true", help="Include Python stack traces in error output")
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
    build.add_argument("--allow-vendor-updates", action="store_true", help="Permit manufacturer installation; every build blocks it in both images by default")
    build.add_argument("--inputs", type=Path, help="Private JSON object mapping payload IDs to inputs")
    build.add_argument("--ssh-public-key", type=Path, help="Public login key for the explicitly selected ssh payload")
    build.add_argument("--ssh-password", action="store_true", help="Prompt privately for the ssh payload login password")
    build.add_argument("--ssh-password-file", type=Path, help="Read ssh login password from a private file")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--report", type=Path, help="Optional build result/failure report (must not already exist)")
    for command in (build, doctor):
        command.add_argument("--debugfs", help="Explicit debugfs executable")
        command.add_argument("--e2fsck", help="Explicit e2fsck executable")
        command.add_argument("--sevenzip", help="Explicit 7zz/7z executable")
    for name, help_text in (
        ("inspect-fw", "Validate firmware and calculate payload checksums offline"),
        ("plan", "Validate firmware and device identity without device writes"),
        ("flash", "Write recovery and main firmware, including recovery-mode transition and reboots"),
        ("plan-recovery", "Read-only preflight for main installation from running recovery"),
        ("recover", "Install main firmware from idle recovery state 1 and reboot to normal"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("firmware", type=Path)
        if name != "inspect-fw":
            command.add_argument("--tetherkit", type=Path, default=tetherkit(), help="Override the USB helper executable")
        if name in ("plan", "flash"):
            command.add_argument("--transport", choices=("usb", "ssh"), default="usb")
            command.add_argument("--host", help="Wireless hostname or IPv4 address (default: Bticino-Classe100X.local)")
            command.add_argument("--external-usb", action="store_true", help="Advanced: use an already running USB supervisor")
            command.add_argument("--verify-recovery-ssh", action="store_true", help="Optional: require installed recovery readback before clearing the main kernel (existing SSH required)")
            command.add_argument("--ssh-user", help="Existing administrative SSH account for recovery verification")
            auth = command.add_mutually_exclusive_group()
            auth.add_argument("--ssh-password", action="store_true", help="Prompt once for the existing SSH password; keep it only in memory")
            auth.add_argument("--ssh-key", type=Path, help="SSH identity file (encrypted keys must already be unlocked in your agent)")
            command.add_argument("--destination-ssh-user", help="Destination account; defaults to existing SSH user")
            destination_auth = command.add_mutually_exclusive_group()
            destination_auth.add_argument("--destination-ssh-key", type=Path, help="Destination login key; defaults to existing authentication")
            destination_auth.add_argument("--destination-ssh-password", action="store_true", help="Prompt for a different destination password")
            command.add_argument("--accept-regenerated-host-key", action="store_true",
                                 help="Accept the SSH host key that a source firmware regenerates at every boot, which cannot be verified (SSH transport; the update stops without it)")
    # Resuming an interrupted update is possible over SSH only.
    for name, help_text in (
        ("plan-resume-recovery", "Read-only check of an update interrupted after recovery was written (SSH)"),
        ("resume-recovery", "Continue an update interrupted after recovery was written: verify it, clear main, install main (SSH)"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("firmware", type=Path)
        command.add_argument("--host", help="Wireless hostname or IPv4 address (default: Bticino-Classe100X.local)")
        command.add_argument("--ssh-user", help="Existing administrative SSH account")
        auth = command.add_mutually_exclusive_group()
        auth.add_argument("--ssh-password", action="store_true", help="Prompt once for the existing SSH password; keep it only in memory")
        auth.add_argument("--ssh-key", type=Path, help="SSH identity file (encrypted keys must already be unlocked in your agent)")
        command.add_argument("--destination-ssh-user", help="Destination account; defaults to existing SSH user")
        destination_auth = command.add_mutually_exclusive_group()
        destination_auth.add_argument("--destination-ssh-key", type=Path, help="Destination login key; defaults to existing authentication")
        destination_auth.add_argument("--destination-ssh-password", action="store_true", help="Prompt for a different destination password")
        command.add_argument("--accept-regenerated-host-key", action="store_true",
                             help="Accept the SSH host key that a source firmware regenerates at every boot, which cannot be verified (the command stops without it)")
    for command in commands.choices.values():
        command.add_argument("--debug", action="store_true", default=argparse.SUPPRESS,
                             help="Include Python stack traces in error output")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command in ("plan", "flash"):
            if args.transport == "ssh":
                if args.external_usb:
                    raise ValueError("--external-usb cannot be combined with --transport ssh")
            elif (args.host or args.destination_ssh_user or args.destination_ssh_key or args.destination_ssh_password
                  or args.accept_regenerated_host_key):
                raise ValueError("Wireless host/destination options require --transport ssh")
            elif args.verify_recovery_ssh:
                if not args.ssh_user:
                    raise ValueError("--verify-recovery-ssh requires --ssh-user")
                if args.external_usb:
                    raise ValueError("SSH verification requires managed USB networking; omit --external-usb")
            elif args.ssh_user or args.ssh_password or args.ssh_key:
                raise ValueError("SSH authentication options require --verify-recovery-ssh")
        if args.command == "fetch-fw":
            from .download import fetch_stock
            from .builder import interrupted_build
            with interrupted_build():
                path = fetch_stock(args.cache)
            print(path)
            print(f"Stock firmware verified and available at: {path}", file=sys.stderr)
        elif args.command == "builder-doctor":
            from .builder import builder_tools, tool_versions
            from .host import find_tool, run_tool
            tools = builder_tools({"debugfs": args.debugfs, "e2fsck": args.e2fsck, "7zip": args.sevenzip})
            result = {"paths": tools, "versions": tool_versions(tools), "ssh_tools": {}}
            for name, options in (("dropbearkey", ["-h"]), ("openssl", ["version"])):
                try:
                    path = find_tool(name)
                    _, out, err = run_tool([path, *options], timeout=10)
                    lines = (out + err).decode(errors="replace").splitlines()
                    if name == "dropbearkey":
                        help_text = "\n".join(lines)
                        result["ssh_tools"][name] = {"path": path, "version": "not reported by keygen",
                                                     "ecdsa_p256": "ecdsa" in help_text and "256" in help_text}
                    else:
                        _, out, err = run_tool([path, "passwd", "-help"], timeout=10)
                        result["ssh_tools"][name] = {"path": path, "version": lines[0][:200] if lines else "unknown",
                                                     "sha512_crypt": b"-6" in out + err}
                except (FirmwareError, OSError) as exc:
                    result["ssh_tools"][name] = {"available": False, "failure": failure(exc)}
            print(json.dumps(result, indent=2))
            print("Core builder tools found and versions checked.", file=sys.stderr)
            missing = [name for name, capability in (("dropbearkey", "ecdsa_p256"), ("openssl", "sha512_crypt"))
                       if not result["ssh_tools"][name].get(capability)]
            if missing:
                print(f"Optional SSH tool checks incomplete: {', '.join(missing)} (missing tool or required capability).",
                      file=sys.stderr)
            else:
                print("Optional SSH tool checks passed.", file=sys.stderr)
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
                    if os.fstat(stream.fileno()).st_mode & 0o077:
                        raise ValueError("Payload inputs file must have private permissions (chmod 600)")
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
                               allow_vendor_updates=args.allow_vendor_updates,
                               overrides={"debugfs": args.debugfs, "e2fsck": args.e2fsck, "7zip": args.sevenzip},
                               report_path=args.report, progress=lambda msg: print(msg, file=sys.stderr))
            print(json.dumps(result, indent=2))
            print(f"Build completed. Offline checks passed. Image saved to: {args.output.absolute()}", file=sys.stderr)
        elif args.command == "probe":
            with ReadOnlyClient(args.host, args.port, args.timeout) as client:
                print(json.dumps(client.inspect(), indent=2))
            print("Device information read successfully.", file=sys.stderr)
        elif args.command == "usb":
            run_usb(args.tetherkit)
        else:
            print("Validating the complete firmware archive…", file=sys.stderr)
            with prepare_firmware(args.firmware) as firmware:
                if args.command == "inspect-fw":
                    print(json.dumps(firmware.report(), indent=2))
                elif (args.command in ("plan", "flash") and args.transport == "ssh") or args.command in (
                        "plan-resume-recovery", "resume-recovery"):
                    wireless_command(args, firmware)
                else:
                    from_recovery = args.command in ("plan-recovery", "recover")
                    external_usb = not from_recovery and args.external_usb
                    session = nullcontext(lambda: None) if external_usb else usb_session(args.tetherkit)
                    with session as check_transport, recovery_verification(args, firmware, check_transport) as verification:
                        check_transport()
                        if args.command in ("plan", "plan-recovery"):
                            with ReadOnlyClient("192.168.129.1") as client:
                                info = client.inspect()
                                check_identity(info, 1 if from_recovery else 4)
                                if from_recovery and not client.idle():
                                    raise UpdateError("Recovery update worker is busy; no transfer was started")
                            if verification is not None:
                                verification.preflight()
                            result = {
                                "firmware": firmware.report(), "device": info,
                                "sequence": ["recovery filesystem", "recovery kernel", "reboot to normal",
                                             "clear main kernel", "reboot to recovery", "main filesystem",
                                             "main kernel", "reboot to normal"],
                                "device_writes": False,
                            }
                            if from_recovery:
                                result["sequence"] = ["main filesystem", "main kernel", "reboot to normal"]
                                result["worker_idle"] = True
                            if verification is not None:
                                result["sequence"].insert(3, "SSH recovery integrity verification")
                                result["verification_report"] = str(verification.directory / "report.json")
                            print(json.dumps(result, indent=2))
                        else:
                            device = NetworkDevice("192.168.129.1", check_transport=check_transport,
                                                   before_reboot=unmount_usb_storage)
                            report = lambda text: print(text, flush=True)
                            if from_recovery:
                                flash_recovery(firmware, device, C100X_PROFILE, report=report)
                            else:
                                flash(firmware, device, C100X_PROFILE, report=report, verification=verification)
            if args.command == "inspect-fw":
                print("Firmware validation passed.", file=sys.stderr)
            elif args.command in ("plan", "plan-recovery", "plan-resume-recovery"):
                print("Preflight passed. All requested preflight checks passed. No firmware was written.", file=sys.stderr)
        return 0
    except Exception as exc:
        expected = isinstance(exc, (FirmwareError, UpdateError, ProtocolError, OSError,
                                   ValueError, subprocess.SubprocessError))
        print(f"{args.command} failed: {format_failure(exc, debug=args.debug or not expected)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        clear_secrets()


if __name__ == "__main__":
    sys.exit(main())
