"""Build the Linux SSH/builder bundle on Ubuntu 24.04, including dependency sources."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib

from build import ROOT, archive_notices, digest, download, run, text


# These libraries belong to the host's glibc; everything else is bundled.
SYSTEM_LIBRARIES = {
    "libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "librt.so.1",
    "libutil.so.1", "libresolv.so.2", "ld-linux-x86-64.so.2",
}


def elf(path):
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(4) == b"\x7fELF"


def linked(path):
    output = text("ldd", path)
    if "not found" in output:
        raise RuntimeError(f"Missing library for {path}: {output}")
    return re.findall(r"^\s*(\S+) => (/\S+) \(", output, re.MULTILINE)


def relocate(bundle, origins):
    libraries = bundle / "support/app/tools/lib"
    libraries.mkdir()
    pending = list(origins)
    # Discover the entire closure before rewriting any of the source runtime files.
    while pending:
        target = pending.pop()
        for name, filename in linked(origins[target]):
            if name in SYSTEM_LIBRARIES:
                continue
            source = Path(filename).resolve(strict=True)
            destination = libraries / name
            if destination in origins:
                if digest(source) != digest(origins[destination]):
                    raise RuntimeError(f"Conflicting library: {name}")
                continue
            shutil.copy2(source, destination)
            origins[destination] = source
            pending.append(destination)
    for target in origins:
        target.chmod(0o755)
        run("patchelf", "--set-rpath", "$ORIGIN/" + os.path.relpath(libraries, target.parent), target)
    return origins


def audit(bundle):
    bundle = bundle.resolve()
    libraries = bundle / "support/app/tools/lib"
    for path in bundle.rglob("*"):
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(bundle):
            raise RuntimeError(f"External symlink: {path}")
        if not elf(path):
            continue
        with path.open("rb") as stream:
            header = stream.read(20)
        if header[4:6] != b"\x02\x01" or header[18:20] != b"\x3e\x00":
            raise RuntimeError(f"Not an x86-64 ELF: {path}")
        expected = "$ORIGIN/" + os.path.relpath(libraries, path.parent)
        if text("patchelf", "--print-rpath", path) != expected:
            raise RuntimeError(f"Nonportable library search path: {path}")
        for name in text("patchelf", "--print-needed", path).splitlines():
            if "/" in name or (name not in SYSTEM_LIBRARIES and not (libraries / name).is_file()):
                raise RuntimeError(f"Unbundled library in {path}: {name}")
        for name, filename in linked(path):
            if name not in SYSTEM_LIBRARIES and not Path(filename).resolve().is_relative_to(bundle):
                raise RuntimeError(f"External library in {path}: {filename}")
        versions = re.findall(r"\bGLIBC_(\d+\.\d+)", text("readelf", "--version-info", path))
        if any(tuple(map(int, version.split("."))) > (2, 39) for version in versions):
            raise RuntimeError(f"Library requires glibc newer than 2.39: {path}")
    return "2.39"


def package_owner(path):
    # Ubuntu's merged-/usr filesystem still has some /lib entries in dpkg's database.
    candidates = [str(path)]
    if str(path).startswith("/usr/"):
        candidates.append(str(path).removeprefix("/usr"))
    for candidate in candidates:
        result = subprocess.run(["dpkg-query", "-S", candidate], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.splitlines()[0].rsplit(": ", 1)[0]
    raise RuntimeError(f"No Debian source provenance for {path}")


def collect_sources(bundle, origins, sources, licenses):
    packages = {package_owner(source) for source in origins.values()
                if not source.is_relative_to(bundle)}
    metadata, fetched = [], set()
    for package in sorted(packages):
        fields = text("dpkg-query", "-W", "-f=${Version}\t${source:Package}\t${source:Version}", package).split("\t")
        version, source_name, source_version = fields
        notice = Path("/usr/share/doc") / package.split(":")[0] / "copyright"
        shutil.copy2(notice, licenses / (package.replace(":", "-") + ".txt"))
        directory = sources / source_name
        if source_name not in fetched:
            directory.mkdir()
            run("apt-get", "source", "--download-only", f"{source_name}={source_version}", cwd=directory)
            fetched.add(source_name)
        metadata.append({"name": package, "version": version, "source_package": source_name,
                         "source_version": source_version,
                         "files": {p.name: digest(p) for p in sorted(directory.iterdir()) if p.is_file()}})
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/release-linux")
    args = parser.parse_args()
    if (sys.platform != "linux" or platform.machine() != "x86_64"
            or platform.freedesktop_os_release().get("ID") != "ubuntu"
            or platform.freedesktop_os_release().get("VERSION_ID") != "24.04"):
        raise RuntimeError("Build on Ubuntu 24.04 x86-64 using packaging/setup-linux.sh")
    if not re.fullmatch(r"v?\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", args.version):
        raise ValueError("Expected a release version")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bundle = out / "C100X"
    bundle.mkdir()  # Refuse to overwrite a previous build.
    app = bundle / "support/app"
    tools = app / "tools"
    tools.mkdir(parents=True)
    sources, licenses = out / "sources", bundle / "licenses"
    sources.mkdir()
    licenses.mkdir()
    for name in ("classe100x", "payloads"):
        shutil.copytree(ROOT / name, app / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "docs", bundle / "docs")
    for name in ("LICENSE", "GLOSSARY.md", "README.md"):
        shutil.copy2(ROOT / name, bundle / name)
    shutil.copy2(ROOT / "packaging/README.txt", bundle / "README.txt")
    recipes = sources / "build-recipes"
    shutil.copytree(ROOT / "packaging", recipes, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "mise.toml", recipes / "mise.toml")
    shutil.copytree(ROOT / ".github/workflows", recipes / "workflows")

    python_version = tomllib.loads((ROOT / "mise.toml").read_text())["tools"]["python"]
    python_tar = sources / f"Python-{python_version}.tar.xz"
    python_url = f"https://www.python.org/ftp/python/{python_version}/{python_tar.name}"
    download(python_url, python_tar)
    build_dir = out / "python-build"
    build_dir.mkdir()
    with tarfile.open(python_tar) as archive:
        archive.extractall(build_dir, filter="data")
    python_source = build_dir / f"Python-{python_version}"
    runtime = bundle / "support/python"
    env = {**os.environ, "LDFLAGS": f"-Wl,-rpath,{runtime}/lib"}
    run("./configure", f"--prefix={runtime}", "--enable-shared", "--with-ensurepip=no",
        "--disable-test-modules", "--with-openssl=/usr", cwd=python_source, env=env)
    run("make", "-j", str(min(os.cpu_count() or 2, 8)), cwd=python_source, env=env)
    run("./python", "-E", "-c", "import ssl, hashlib, lzma, compression.zstd, bz2, zlib, sqlite3, ctypes",
        cwd=python_source, env={**env, "LD_LIBRARY_PATH": str(python_source)})
    run("make", "install", cwd=python_source, env=env)
    archive_notices(python_tar, licenses / "Python")
    shutil.rmtree(runtime / "include")
    shutil.rmtree(runtime / "share", ignore_errors=True)
    shutil.rmtree(runtime / "lib/pkgconfig")
    for directory in (runtime / "lib").glob("python*/config-*"):
        shutil.rmtree(directory)
    for path in (runtime / "bin").iterdir():
        if path.name not in ("python3", "python" + ".".join(python_version.split(".")[:2])):
            path.unlink()
    for path in runtime.rglob("__pycache__"):
        shutil.rmtree(path)
    for path in runtime.rglob("*.a"):
        path.unlink()

    origins = {p: p for p in runtime.rglob("*") if elf(p)}
    # Ubuntu's 7z launcher is a shell script; ship the ELF and its format module.
    for name, filename in {
        "debugfs": "/usr/sbin/debugfs", "e2fsck": "/usr/sbin/e2fsck",
        "7zz": "/usr/lib/7zip/7z", "7z.so": "/usr/lib/7zip/7z.so",
        "dropbearkey": "/usr/bin/dropbearkey", "openssl": "/usr/bin/openssl",
    }.items():
        source = Path(filename).resolve(strict=True)
        shutil.copy2(source, tools / name)
        origins[tools / name] = source
    run("gcc", "-O2", ROOT / "packaging/launcher.c", "-o", bundle / "c100x")
    origins[bundle / "c100x"] = bundle / "c100x"
    relocate(bundle, origins)
    metadata = [{"name": "Python", "version": python_version, "url": python_url, "sha256": digest(python_tar)}]
    metadata.extend(collect_sources(bundle, origins, sources, licenses))
    minimum = audit(bundle)
    manifest = {"version": args.version, "platform": "linux", "architecture": "x86_64",
                "minimum_glibc": minimum, "transports": ["ssh"],
                "commit": text("git", "-C", ROOT, "rev-parse", "HEAD"),
                "compiler": text("gcc", "--version").splitlines()[0], "sources": metadata,
                "hardware_acceptance": "not performed"}
    for destination in (app / "release.json", out / "release-linux-x86_64.json", sources / "manifest.json"):
        destination.write_text(json.dumps(manifest, indent=2) + "\n")
    (licenses / "README.txt").write_text("Bundled dependencies retain their own licenses. Exact sources and build recipes accompany this release.\n")
    for name, directory in ((f"c100x-{args.version}-linux-x86_64.tar.gz", bundle),
                            (f"c100x-{args.version}-linux-x86_64-dependency-sources.tar.gz", sources)):
        with tarfile.open(out / name, "w:gz") as archive:
            archive.add(directory, arcname=directory.name)
    print(f"Built {bundle}; x86-64 Linux, glibc {minimum}+")


if __name__ == "__main__":
    main()
