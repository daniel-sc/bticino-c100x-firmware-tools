"""Exercise the actual relocatable CLI and native tools without USB or firmware."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from build import audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    original = args.bundle.resolve()
    # Tests exercise relocation, spaces, a fresh HOME and no package-manager PATH.
    with tempfile.TemporaryDirectory(prefix="c100x smoke ") as temporary:
        root = Path(temporary).resolve()
        bundle = root / "relocated bundle"
        shutil.copytree(original, bundle, symlinks=True)
        home = root / "home"
        home.mkdir()
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home), "TMPDIR": temporary,
               "LC_ALL": "C", "OPENSSL_CONF": "/dev/null"}
        def run(*command, input=None):
            return subprocess.run(list(map(str, command)), cwd=root, env=env, input=input,
                                  capture_output=True, check=True, timeout=120).stdout
        cli = bundle / "c100x"
        run(cli, "--version")
        for command in ("build-fw", "inspect-fw", "plan", "flash", "usb"):
            run(cli, command, "--help")
        doctor = json.loads(run(cli, "builder-doctor"))
        assert doctor["ssh_tools"]["openssl"]["sha512_crypt"]
        assert doctor["ssh_tools"]["dropbearkey"]["ecdsa_p256"]
        for path in doctor["paths"].values():
            assert Path(path).is_relative_to(bundle)
        tools = bundle / "support/app/tools"
        run(tools / "tetherkit-cli", "--help")  # Never enumerate/connect hardware.

        # Exercise the shipped askpass helper/IPC and OpenSSH argument handling
        # with local fake SSH processes, using the relocated isolated interpreter.
        run(bundle / "support/python/bin/python3", "-I", "-B", "-c",
            "import sys, unittest; sys.path.insert(0, sys.argv[1]); "
            "suite = unittest.defaultTestLoader.discover(sys.argv[2], pattern='test_ssh.py'); "
            "result = unittest.TextTestRunner().run(suite); "
            "raise SystemExit(not result.wasSuccessful())",
            bundle / "support/app", Path(__file__).resolve().parent.parent / "tests")

        # Fixture creation is a host build-time operation; all tested operations
        # below use only shipped tools. mke2fs is not an end-user dependency.
        mkfs = Path(subprocess.check_output(["brew", "--prefix", "e2fsprogs"], text=True).strip()) / "sbin/mke2fs"
        image = root / "fixture.ext4"
        with image.open("wb") as stream:
            stream.truncate(16 * 1024**2)
        subprocess.run([str(mkfs), "-q", "-t", "ext4", "-F", str(image)], check=True)
        (root / "asset").write_bytes(b"fixture\n")
        (root / "commands").write_text("write asset /fixture\nset_inode_field /fixture mode 0100644\n")
        run(tools / "debugfs", "-w", "-f", "commands", image)
        run(tools / "e2fsck", "-f", "-n", image)

        # The same subprocess entry point used by custom and bundled payloads.
        hook = root / "verify.py"
        hook.write_text("from classe100x.payload import Context\n"
                        "import asyncio, ctypes, decimal, sqlite3, ssl, secrets, lzma, compression.zstd\n"
                        "Context().image.require_file('/fixture', b'fixture\\n', mode=0o644)\n")
        context = root / "context.json"
        context.write_text(json.dumps({"directory": str(root), "image": str(image), "input_base": str(root),
                                      "inputs": {}, "tools": doctor["paths"]}))
        run(bundle / "support/python/bin/python3", "-I", "-B",
            bundle / "support/app/classe100x/payload_runner.py", hook, context)
        run(tools / "dropbearkey", "-t", "ecdsa", "-s", "256", "-f", root / "host-key")
        password_hash = run(tools / "openssl", "passwd", "-6", "-stdin", input=b"synthetic-only\n")
        assert password_hash.startswith(b"$6$")
        (root / "archive-input").write_bytes(b"fixture" * 1024)
        run(tools / "7zz", "a", "-tzip", "-mm=Deflate", "-mem=ZipCrypto", "-pC100X", "fixture.zip", "archive-input")
        with zipfile.ZipFile(root / "fixture.zip") as archive:
            assert archive.read("archive-input", pwd=b"C100X") == (root / "archive-input").read_bytes()
        minimum = audit(bundle)
        print(f"Packaged smoke tests passed; arm64, minimum macOS {minimum}, no USB access")


if __name__ == "__main__":
    main()
