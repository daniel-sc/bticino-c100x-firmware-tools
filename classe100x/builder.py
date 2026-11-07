"""Private-workspace FWZ builder with trusted, ordered local payloads."""

from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import tempfile

from .download import STOCK_SIZE, publish
from .ext4 import Ext4
from .firmware import (ARCHIVE_KEY, FirmwareError, MAIN_SIZE, PROFILE, STOCK_SHA256,
                       check_main_image, filesystem_profile, prepare_firmware, regular_file)
from .host import find_tool, run_tool
from .diagnostics import details, failure, format_failure, protect_inputs, tool_error

MEMBER_ORDER = ("btweb_only.ext4.gz", "btweb_only_recovery.ext4.gz", "fwz.xml", "uImage.zip")
BUNDLED = Path(__file__).resolve().parent.parent / "payloads"


@contextmanager
def interrupted_build():
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    old = {}
    try:
        for sig in (signal.SIGTERM, signal.SIGHUP):
            old[sig] = signal.signal(sig, interrupt)
        yield
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


def resolve_payload(value: str) -> Path:
    local = Path(value).expanduser()
    return local.resolve() if local.is_dir() else (BUNDLED / value).resolve()


def load_payloads(paths: list[Path]) -> list[tuple[Path, dict]]:
    result, identities = [], set()
    for path in paths:
        with regular_file(path / "payload.json") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise FirmwareError("Payload manifest exceeds its size limit")
        try:
            manifest = json.loads(raw)
            identity, version = manifest["id"], manifest["version"]
            if not isinstance(identity, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identity):
                raise ValueError
            if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", version):
                raise ValueError
            if manifest["profile"] != PROFILE:
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise details(FirmwareError("Invalid or incompatible payload manifest"), manifest=path / "payload.json") from exc
        if identity in identities:
            raise FirmwareError("The same payload identity cannot be selected twice")
        identities.add(identity)
        if not (path / "apply.debugfs").is_file():
            raise FirmwareError("Payload requires apply.debugfs")
        if manifest.get("verification_required") and not (path / "verify.py").is_file():
            raise FirmwareError("Payload requires its verification hook")
        result.append((path, manifest))
    return result


def snapshot_payload(source: Path, target: Path) -> None:
    total, count = 0, 0
    for parent, directories, files in os.walk(source, followlinks=False):
        for name in directories + files:
            path = Path(parent) / name
            if path.is_symlink():
                raise FirmwareError("Payload source directories must not contain host symlinks")
        for name in files:
            with regular_file(Path(parent) / name) as stream:
                total += os.fstat(stream.fileno()).st_size
            count += 1
            if total > 256 * 1024**2 or count > 10000:
                raise FirmwareError("Payload assets exceed the supported limit")
    shutil.copytree(source, target)
    if (target / "generated").exists():
        raise FirmwareError("The generated/ name is reserved for payload preparation")


def hook(directory: Path, name: str, *, required: bool = False) -> bool:
    script = directory / name
    if not script.exists():
        if required:
            raise FirmwareError(f"Payload {directory.name} requires {name}")
        return False
    runner = Path(__file__).with_name("payload_runner.py")
    status, _, stderr = run_tool([sys.executable, "-I", "-B", str(runner), str(script), str(directory / "context.json")],
                            cwd=directory, timeout=120)
    if status:
        first = stderr.decode("utf-8", errors="replace").splitlines()
        summary = first[0][15:] if first and first[0].startswith("Payload error: ") and len(first[0]) <= 315 else "failed"
        raise tool_error(FirmwareError(f"Payload {directory.name} {name}: {summary}"), script, status, stderr)
    return True


def expand(source: Path, target: Path, *, recovery=False) -> str:
    digest = hashlib.sha256()
    size = 0
    with gzip.open(source, "rb") as src, target.open("xb") as dst:
        while chunk := src.read(1024 * 1024):
            size += len(chunk)
            if size > filesystem_profile(recovery)[0]:
                raise FirmwareError("Expanded filesystem exceeds its profile size")
            dst.write(chunk)
            digest.update(chunk)
    check_main_image(target, recovery=recovery)
    return digest.hexdigest()


def filesystem_layout(image: Path) -> bytes:
    with image.open("rb") as stream:
        stream.seek(1024)
        sb = stream.read(1024)
    # UUID, journal identity/inode/device, directory hash seed/version/descriptor size.
    # Allocation counters and timestamps legitimately change during payload application.
    return sb[104:120] + sb[208:232] + sb[236:256]


def check_shared_ssh(workspace, filename, tools):
    access = []
    for environment in ("main", "recovery"):
        image = Ext4(workspace / environment / filename, tools["debugfs"], tools["e2fsck"])
        fields = [image.read(path) for path in ("/etc/dropbear/classe100x_ecdsa_host_key",
                                                "/home/root/.ssh/authorized_keys", "/etc/default/c100x-ssh")]
        fields.append(b"\n".join(line for line in image.read("/etc/shadow").splitlines() if line.startswith(b"root2:")))
        access.append(fields)
    if access[0] != access[1]:
        raise FirmwareError("Main and recovery SSH identity or authentication differs")


def pack(directory: Path, destination: Path, sevenzip: str) -> None:
    # Public format password only. Device/user credentials never enter argv.
    # 7zip may STORE tiny/incompressible entries despite -mm; the final profile
    # check rejects that variant rather than silently broadening compatibility.
    status, out, err = run_tool([sevenzip, "a", "-tzip", "-mm=Deflate", "-mx=9", "-mem=ZipCrypto",
                            "-p" + ARCHIVE_KEY.decode(), "-mmt=1", "-bd", "-y",
                            str(destination), *MEMBER_ORDER], cwd=directory, timeout=600)
    if status:
        raise tool_error(FirmwareError("Encrypted FWZ packaging failed"), sevenzip, status, err, stdout=out)


def tool_versions(tools: dict) -> dict:
    versions = {"python": sys.version.split()[0]}
    for name, options in (("debugfs", ["-V"]), ("e2fsck", ["-V"]), ("7zip", ["i"])):
        status, stdout, stderr = run_tool([tools[name], *options], timeout=10)
        text = (stdout + stderr).decode("utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if status or not lines:
            raise tool_error(FirmwareError("Unable to identify a builder tool version"), tools[name], status, stderr, stdout=stdout)
        versions[name] = lines[0][:200]
    return versions


def builder_tools(overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    return {"debugfs": find_tool("debugfs", overrides.get("debugfs")),
            "e2fsck": find_tool("e2fsck", overrides.get("e2fsck")),
            "7zip": find_tool("7zz", overrides.get("7zip"))}


def build(source: Path, output: Path, *, payloads: list[Path] = (), inputs: dict | None = None,
          input_base: Path | None = None, overrides: dict | None = None,
          report_path: Path | None = None, allow_vendor_updates=False, progress=lambda message: None) -> dict:
    """Preserve failure evidence at the requested report path without overwriting."""
    if report_path is not None:
        report_path = report_path.absolute()
        if (report_path.resolve() in (output.resolve(), source.resolve()) or report_path.exists()
                or report_path.is_symlink() or not report_path.parent.is_dir()):
            raise FirmwareError("Report requires a separate, unused path in an existing directory")
    protect_inputs(inputs)
    stage = "validating build inputs and tools"

    def report_stage(message):
        nonlocal stage
        stage = message
        progress(message)

    try:
        return _build(source, output, payloads=payloads, inputs=inputs, input_base=input_base,
                      overrides=overrides, report_path=report_path, progress=report_stage,
                      allow_vendor_updates=allow_vendor_updates)
    except (Exception, KeyboardInterrupt) as exc:
        details(exc, build_stage=stage)
        if report_path is not None:
            try:
                save_report({"schema": 1, "profile": PROFILE, "status": "failed", "stage": stage,
                             "failure": failure(exc)}, report_path)
                details(exc, report=report_path)
            except (OSError, FirmwareError) as report_error:
                exc.add_note("Could not publish failure report:\n" + format_failure(report_error))
        raise


def save_report(report, path):
    fd, name = tempfile.mkstemp(prefix=".build-report-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        publish(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _build(source: Path, output: Path, *, payloads=(), inputs=None, input_base=None,
           overrides=None, report_path=None, allow_vendor_updates=False, progress=lambda message: None) -> dict:
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FirmwareError("Output already exists; originals and previous builds are never overwritten")
    if not output.parent.is_dir():
        raise FirmwareError("Output directory does not exist")
    selected = load_payloads(payloads)
    for path, manifest in selected:
        if manifest["id"] == "no-ota":
            raise FirmwareError("no-ota is now a default builder policy, not a selectable payload; use --allow-vendor-updates to opt out")
        if manifest["id"] == "ssh" and path.resolve() != (BUNDLED / "ssh").resolve():
            raise FirmwareError("The reserved ssh identity requires the bundled dual-filesystem payload")
    inputs = inputs or {}
    if not isinstance(inputs, dict) or any(not isinstance(v, dict) for v in inputs.values()):
        raise FirmwareError("Payload inputs must map payload identities to input objects")
    if set(inputs) - {manifest["id"] for _, manifest in selected}:
        raise FirmwareError("Inputs were supplied for an unselected payload")
    if not allow_vendor_updates:
        selected = load_payloads([BUNDLED / "no-ota"]) + selected
    tools = builder_tools(overrides)
    versions = tool_versions(tools)
    if shutil.disk_usage(output.parent).free < MAIN_SIZE * 3 + STOCK_SIZE * 3:
        raise FirmwareError("Insufficient workspace space (allow at least 3.5 GiB free)")
    with interrupted_build(), tempfile.TemporaryDirectory(prefix=".classe100x-build-", dir=output.parent) as tmp:
        workspace = Path(tmp).resolve()
        snapshot = workspace / "source.fwz"
        progress("Checking and snapshotting the original stock firmware")
        with regular_file(source) as src, snapshot.open("xb") as dst:
            if os.fstat(src.fileno()).st_size != STOCK_SIZE:
                raise FirmwareError("Builder requires the pinned original stock firmware")
            digest = hashlib.sha256()
            copied = 0
            while chunk := src.read(1024 * 1024):
                copied += len(chunk)
                if copied > STOCK_SIZE:
                    raise FirmwareError("Stock input changed or exceeded the pinned size")
                dst.write(chunk)
                digest.update(chunk)
            if copied != STOCK_SIZE or digest.hexdigest() != STOCK_SHA256:
                raise FirmwareError("Builder requires the pinned original stock SHA-256")
        shared = workspace / "shared-ssh"
        shared.mkdir(mode=0o700)
        records, hashes, layouts = [], {}, {}
        with prepare_firmware(snapshot, temporary_parent=workspace) as original:
            for environment, member in (("main", MEMBER_ORDER[0]), ("recovery", MEMBER_ORDER[1])):
                recovery = environment == "recovery"
                root = workspace / environment
                root.mkdir()
                image = root / "working.ext4"
                original_hash = expand(original.directory / member, image, recovery=recovery)
                layouts[environment] = filesystem_layout(image)
                filesystem = Ext4(image, tools["debugfs"], tools["e2fsck"])
                progress(f"Checking original {environment} filesystem")
                filesystem.check()
                active = [(p, m) for p, m in selected if not recovery or m["id"] in ("ssh", "no-ota")]
                for path, manifest in active:
                    directory = root / manifest["id"]
                    snapshot_payload(path, directory)
                    context = {"image": str(image), "directory": str(directory), "tools": tools,
                               "environment": environment, "shared_ssh": str(shared),
                               "input_base": str((input_base or Path.cwd()).resolve()),
                               "inputs": inputs.get(manifest["id"], {})}
                    context_path = directory / "context.json"
                    context_path.write_text(json.dumps(context))
                    context_path.chmod(0o600)
                    progress(f"Applying {manifest['id']} to {environment}")
                    hook(directory, "prepare.py")
                    filesystem.apply(directory / "apply.debugfs", directory)
                    verified = hook(directory, "verify.py", required=bool(manifest.get("verification_required")))
                    records.append({"id": manifest["id"], "version": manifest["version"], "environment": environment,
                                    "verification": "passed" if verified else "not supplied"})
                progress(f"Checking final {environment} filesystem and payload results")
                for record in (r for r in records if r["environment"] == environment):
                    hook(root / record["id"], "verify.py", required=record["verification"] == "passed")
                check_main_image(image, recovery=recovery)
                filesystem.check()
                if filesystem_layout(image) != layouts[environment]:
                    raise FirmwareError("Payload changed preserved filesystem layout/identity metadata")
                with image.open("rb") as raw:
                    hashes[environment] = hashlib.file_digest(raw, "sha256").hexdigest()
                if not active and hashes[environment] != original_hash:
                    raise FirmwareError("Unmodified round trip changed filesystem bytes")
                if active:
                    with image.open("rb") as raw, (original.directory / member).open("wb") as zipped:
                        with gzip.GzipFile(filename="", mode="wb", fileobj=zipped, mtime=0, compresslevel=9) as gz:
                            shutil.copyfileobj(raw, gz, 1024 * 1024)
            if any(m["id"] == "ssh" for _, m in selected):
                check_shared_ssh(workspace, "working.ext4", tools)
            progress("Packaging both checked filesystems")
            artifact = workspace / "output.fwz"
            pack(original.directory, artifact, tools["7zip"])
        progress("Reopening and verifying the finished FWZ")
        with prepare_firmware(artifact, temporary_parent=workspace) as finished:
            for environment, member in (("main", MEMBER_ORDER[0]), ("recovery", MEMBER_ORDER[1])):
                reopened = workspace / environment / "reopened.ext4"
                if expand(finished.directory / member, reopened, recovery=environment == "recovery") != hashes[environment]:
                    raise FirmwareError("Repacked filesystem differs from the checked working image")
                Ext4(reopened, tools["debugfs"], tools["e2fsck"]).check()
                for record in (r for r in records if r["environment"] == environment):
                    directory = workspace / environment / record["id"]
                    context_path = directory / "context.json"
                    context = json.loads(context_path.read_text())
                    context["image"] = str(reopened)
                    context_path.write_text(json.dumps(context))
                    hook(directory, "verify.py", required=record["verification"] == "passed")
                with reopened.open("rb") as raw:
                    if hashlib.file_digest(raw, "sha256").hexdigest() != hashes[environment]:
                        raise FirmwareError("Verification hook modified the reopened filesystem")
            if any(m["id"] == "ssh" for _, m in selected):
                check_shared_ssh(workspace, "reopened.ext4", tools)
            report = {"schema": 1, "profile": PROFILE, "source_sha256": STOCK_SHA256,
                      "output_sha256": finished.sha256, "main_filesystem_sha256": hashes["main"],
                      "recovery_filesystem_sha256": hashes["recovery"],
                      "vendor_updates": "allowed" if allow_vendor_updates else "blocked",
                      "payloads": records, "tools": versions, "offline_checks": "passed",
                      "hardware_acceptance": "not performed", "myhome_import": "not performed"}
        artifact.chmod(0o600)
        with artifact.open("rb") as stream:
            os.fsync(stream.fileno())
        publish(artifact, output)
        if report_path is not None:
            try:
                save_report(report, report_path)
            except (OSError, FirmwareError) as exc:
                raise FirmwareError(f"Firmware was published at {output}, but the optional report could not be published") from exc
        return report
