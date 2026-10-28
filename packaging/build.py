"""Build a relocatable macOS CLI, dependency sources and provenance manifest.

Run with mise Python after installing the documented build-only Homebrew tools.
Only copied binaries are rewritten. Firmware and local research never enter it.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
TETHERKIT_REVISION = "1ded051fd243c547fd6e250a898f0164cc30561d"
MAGICS = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def text(*args):
    return run(*args, capture_output=True, text=True).stdout.strip()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, destination, expected=None):
    with urllib.request.urlopen(url, timeout=120) as source, destination.open("wb") as output:
        shutil.copyfileobj(source, output)
    if expected and digest(destination) != expected:
        raise RuntimeError(f"Source hash mismatch: {destination.name}")


def macho(path):
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(4) in MAGICS


def archive_notices(source, destination):
    """Preserve notices that binary bottles may omit, including nested licenses."""
    with tarfile.open(source) as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if member.isfile() and re.search(r"(?i)license|^(copying|notice|copyright)(\.|$)", path.name):
                relative = Path(*path.parts[1:])
                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError("Invalid source notice path")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())


def linked(path):
    return [line.strip().split(" (", 1)[0] for line in text("otool", "-L", path).splitlines()[1:] if " (" in line]


def relocate(bundle, origins):
    """Copy the complete non-system dylib closure and rewrite to @loader_path."""
    libraries = bundle / "support/app/tools/lib"
    libraries.mkdir()
    copied = {source.resolve(): target for target, source in origins.items()}
    pending = list(origins)
    while pending:
        target = pending.pop()
        source = origins[target]
        for dependency in linked(source):
            if dependency.startswith(("/System/Library/", "/usr/lib/")):
                continue
            if dependency.startswith("@loader_path/"):
                resolved = source.parent / dependency.removeprefix("@loader_path/")
            elif dependency.startswith("@executable_path/"):
                resolved = source.parent / dependency.removeprefix("@executable_path/")
            elif dependency.startswith("@rpath/"):
                rpaths = re.findall(r"cmd LC_RPATH\n\s*cmdsize \d+\n\s*path (.*?) \(offset", text("otool", "-l", source))
                candidates = [Path(r.replace("@loader_path", str(source.parent))) / dependency.removeprefix("@rpath/") for r in rpaths]
                resolved = next((p for p in candidates if p.exists()), None)
                if resolved is None:
                    raise RuntimeError(f"Unresolved rpath in {source.name}: {dependency}")
            else:
                resolved = Path(dependency)
            resolved = resolved.resolve(strict=True)
            if resolved == source.resolve():
                continue  # dylib's own install ID
            destination = copied.get(resolved)
            if destination is None:
                destination = libraries / resolved.name
                if destination.exists():
                    raise RuntimeError(f"Conflicting library name: {resolved.name}")
                shutil.copy2(resolved, destination)
                destination.chmod(0o755)
                copied[resolved] = destination
                origins[destination] = resolved
                pending.append(destination)
            replacement = "@loader_path/" + os.path.relpath(destination, target.parent)
            run("install_name_tool", "-change", dependency, replacement, target)
        if target.suffix == ".dylib":
            run("install_name_tool", "-id", "@loader_path/" + target.name, target)
        # All non-system references now use loader-relative paths.
        for rpath in re.findall(r"cmd LC_RPATH\n\s*cmdsize \d+\n\s*path (.*?) \(offset", text("otool", "-l", target)):
            run("install_name_tool", "-delete_rpath", rpath, target)
    return origins


def audit(bundle):
    minimum = (15, 0)
    for path in bundle.rglob("*"):
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(bundle.resolve()):
            raise RuntimeError(f"External symlink: {path}")
        if not macho(path):
            continue
        if "arm64" not in text("lipo", "-archs", path).split():
            raise RuntimeError(f"Missing arm64 architecture: {path}")
        for dependency in linked(path):
            if dependency.startswith("@loader_path/"):
                resolved = (path.parent / dependency.removeprefix("@loader_path/")).resolve(strict=True)
                if not resolved.is_relative_to(bundle.resolve()):
                    raise RuntimeError(f"Library escaped bundle: {path}")
            elif not dependency.startswith(("/System/Library/", "/usr/lib/")):
                raise RuntimeError(f"Nonportable library reference in {path.name}: {dependency}")
        load = text("otool", "-l", path)
        if "cmd LC_RPATH\n" in load:
            raise RuntimeError(f"Unexpected runtime search path: {path}")
        versions = re.findall(r"\bminos ([\d.]+)", load)
        versions += re.findall(r"cmd LC_VERSION_MIN_MACOSX\n\s*cmdsize \d+\n\s*version ([\d.]+)", load)
        for version in versions:
            minimum = max(minimum, tuple(map(int, version.split("."))))
    return ".".join(map(str, minimum))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/release")
    parser.add_argument("--helper", type=Path, default=ROOT / ".local/tetherkit-build/bin/tetherkit-cli")
    args = parser.parse_args()
    if sys.platform != "darwin" or text("uname", "-m") != "arm64":
        raise RuntimeError("Build on an Apple Silicon Mac")
    if not re.fullmatch(r"v?\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", args.version):
        raise ValueError("Expected a release version")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bundle = out / "C100X"
    bundle.mkdir()  # Deliberately refuses to overwrite a previous bundle.
    app = bundle / "support/app"
    app.mkdir(parents=True)
    tools = app / "tools"
    tools.mkdir()
    sources = out / "sources"
    sources.mkdir()
    licenses = bundle / "licenses"
    licenses.mkdir()
    recipes = sources / "build-recipes"
    shutil.copytree(ROOT / "packaging", recipes, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "mise.toml", recipes / "mise.toml")
    shutil.copy2(ROOT / ".github/workflows/ci.yml", recipes / "ci.yml")
    shutil.copytree(ROOT / "classe100x", app / "classe100x", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "payloads", app / "payloads", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "docs", bundle / "docs")
    shutil.copy2(ROOT / "LICENSE", bundle / "LICENSE")
    shutil.copy2(ROOT / "packaging/README.txt", bundle / "README.txt")
    source_metadata = []

    # Building the interpreter from its source avoids relying on a developer's
    # installed packages or unknown statically bundled third-party libraries.
    python_version = sys.version.split()[0]
    python_tar = sources / f"Python-{python_version}.tar.xz"
    python_url = f"https://www.python.org/ftp/python/{python_version}/{python_tar.name}"
    download(python_url, python_tar)
    source_metadata.append({"name": "Python", "version": python_version, "url": python_url, "sha256": digest(python_tar)})
    build_dir = out / "python-build"
    build_dir.mkdir()
    with tarfile.open(python_tar) as archive:
        archive.extractall(build_dir, filter="data")
    python_source = build_dir / f"Python-{python_version}"
    runtime = bundle / "support/python"
    openssl = Path(text("brew", "--prefix", "openssl@3"))
    pkgconfig = [str(Path(text("brew", "--prefix", name)) / "lib/pkgconfig")
                 for name in ("openssl@3", "xz", "zstd")]
    env = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": "15.0",
           "PKG_CONFIG_PATH": os.pathsep.join(pkgconfig)}
    run("./configure", f"--prefix={runtime}", "--enable-shared", "--with-ensurepip=no",
        "--disable-test-modules", f"--with-openssl={openssl}", "--with-openssl-rpath=auto", cwd=python_source, env=env)
    run("make", "-j", str(min(os.cpu_count() or 2, 8)), cwd=python_source, env=env)
    # CPython's make can succeed after removing an extension that failed import.
    run("./python.exe", "-E", "-c",
        "import ssl, hashlib, lzma, compression.zstd, bz2, zlib, sqlite3, ctypes",
        cwd=python_source, env={**env, "DYLD_LIBRARY_PATH": str(python_source)})
    run("make", "install", cwd=python_source, env=env)
    shutil.copy2(python_source / "LICENSE", licenses / "Python.txt")
    for notice in python_source.rglob("*"):
        if notice.is_file() and re.match(r"(?i)^(license|copying|notice|copyright)(\.|$)", notice.name):
            destination = licenses / "Python" / notice.relative_to(python_source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(notice, destination)
    shutil.rmtree(runtime / "include")
    shutil.rmtree(runtime / "share", ignore_errors=True)
    shutil.rmtree(runtime / "lib/pkgconfig")
    stdlib = runtime / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    shutil.rmtree(stdlib / "ensurepip", ignore_errors=True)
    for directory in stdlib.glob("config-*"):
        shutil.rmtree(directory)
    for path in (runtime / "bin").iterdir():
        if path.name not in ("python3", f"python{sys.version_info.major}.{sys.version_info.minor}"):
            path.unlink()
    for path in runtime.rglob("__pycache__"):
        shutil.rmtree(path)
    for path in runtime.rglob("*.a"):
        path.unlink()

    origins = {p: p for p in runtime.rglob("*") if macho(p)}
    formula_paths = {}
    for formula, relative, name in (
        ("e2fsprogs", "sbin/debugfs", "debugfs"), ("e2fsprogs", "sbin/e2fsck", "e2fsck"),
        ("sevenzip", "bin/7zz", "7zz"), ("dropbear", "bin/dropbearkey", "dropbearkey"),
        ("openssl@3", "bin/openssl", "openssl"),
    ):
        source = (Path(text("brew", "--prefix", formula)) / relative).resolve(strict=True)
        destination = tools / name
        shutil.copy2(source, destination)
        destination.chmod(0o755)
        origins[destination] = source
    shutil.copy2(args.helper, tools / "tetherkit-cli")
    origins[tools / "tetherkit-cli"] = args.helper.resolve()
    run("clang", "-O2", "-mmacosx-version-min=15.0", ROOT / "packaging/launcher.c", "-o", bundle / "c100x")
    origins = relocate(bundle, origins)

    # Find precisely which Homebrew formulae contributed shipped code.
    for source in origins.values():
        parts = source.resolve().parts
        if "Cellar" in parts:
            index = parts.index("Cellar")
            prefix = Path(*parts[:index + 3])
            formula_paths[parts[index + 1]] = prefix
    for formula, prefix in sorted(formula_paths.items()):
        info = json.loads(text("brew", "info", "--json=v2", formula))["formulae"][0]
        if info["patches"] or info.get("resources"):
            raise RuntimeError(f"Source collection needs review for patched/resource formula {formula}")
        installed_version = prefix.name
        expected_version = info["versions"]["stable"] + (f"_{info['revision']}" if info["revision"] else "")
        if installed_version != expected_version:
            raise RuntimeError(f"Installed {formula} differs from available source metadata")
        source = info["urls"]["stable"]
        directory = sources / formula
        directory.mkdir()
        filename = directory / Path(source["url"]).name
        # Use the formula's mirrors/download strategy (some origins reject
        # urllib), then independently check the exact advertised source bytes.
        run("brew", "fetch", "--build-from-source", formula)
        shutil.copy2(Path(text("brew", "--cache", "--build-from-source", formula)), filename)
        if digest(filename) != source["checksum"]:
            raise RuntimeError(f"Source hash mismatch: {formula}")
        for recipe in (prefix / ".brew").glob("*.rb"):
            shutil.copy2(recipe, directory / recipe.name)
        notice_dir = licenses / formula
        notice_dir.mkdir()
        for notice in prefix.rglob("*"):
            if notice.is_file() and re.match(r"(?i)^(license|copying|notice|copyright|authors)", notice.name):
                target = notice_dir / notice.relative_to(prefix)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(notice, target)
        archive_notices(filename, notice_dir / "source")
        if not any(p.is_file() for p in notice_dir.rglob("*")):
            raise RuntimeError(f"No license notices found for {formula}")
        (directory / "homebrew.json").write_text(json.dumps(info, indent=2) + "\n")
        source_metadata.append({"name": formula, "version": installed_version, "license": info["license"],
                                "url": source["url"], "sha256": digest(filename)})

    # Include upstream helper source and its MIT notice independently of checkout.
    helper_source = sources / "TetherKit.tar.gz"
    download(f"https://github.com/XiaoMiku01/TetherKit/archive/{TETHERKIT_REVISION}.tar.gz", helper_source)
    archive_notices(helper_source, licenses / "TetherKit")
    source_metadata.append({"name": "TetherKit", "version": TETHERKIT_REVISION,
                            "sha256": digest(helper_source)})
    minimum = audit(bundle)
    manifest = {"version": args.version, "architecture": "arm64", "minimum_macos": minimum,
                "commit": text("git", "-C", ROOT, "rev-parse", "HEAD"),
                "tetherkit_revision": TETHERKIT_REVISION, "sources": source_metadata,
                "compiler": text("clang", "--version").splitlines()[0],
                "sdk": text("xcrun", "--show-sdk-version"),
                "hardware_acceptance": "not performed"}
    (app / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (sources / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (licenses / "README.txt").write_text("Each bundled tool retains its own license. Exact dependency sources and build recipes accompany this release.\n")
    # Ad-hoc signatures allow local smoke tests before CI applies Developer ID.
    for path in bundle.rglob("*"):
        if macho(path):
            run("codesign", "--force", "--sign", "-", path)
    with tarfile.open(out / f"c100x-{args.version}-dependency-sources.tar.gz", "w:gz") as archive:
        archive.add(sources, arcname="sources")
    print(f"Built {bundle}; minimum macOS {minimum}")


if __name__ == "__main__":
    main()
