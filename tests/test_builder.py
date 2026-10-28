"""Offline integration tests: synthetic ext4/FWZ only, never vendor files or devices."""

from contextlib import ExitStack
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from classe100x import builder, firmware
from classe100x.ext4 import Ext4, quote
from classe100x.firmware import FirmwareError
from classe100x.host import find_tool, run_tool
from classe100x.payload import Context
from test_firmware import MANIFEST


class ProcessTests(unittest.TestCase):
    def test_output_and_deadlines_are_bounded_without_exposing_output(self):
        for code, kwargs in (("import time; time.sleep(10)", {"timeout": 0.05}),
                             ("print('private-input' * 10000)", {"limit": 100})):
            with self.assertRaises(FirmwareError) as result:
                run_tool([sys.executable, "-c", code], **kwargs)
            self.assertNotIn("private-input", str(result.exception))

    def test_regular_input_gate_rejects_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(FirmwareError):
                firmware.regular_file(fifo)

    def test_ambiguous_debugfs_paths_are_rejected(self):
        self.assertEqual(quote("space ünicode"), '"space ünicode"')
        for path in ('a"b', "a\nb", "a\\b", "a\x00b"):
            with self.assertRaises(FirmwareError):
                quote(path)


class BuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.tools = builder.builder_tools()
            cls.mkfs = find_tool("mke2fs")
        except FirmwareError as exc:
            if os.environ.get("CLASSE100X_REQUIRE_BUILDER_TOOLS"):
                raise
            raise unittest.SkipTest("Install e2fsprogs and 7zip for builder integration tests") from exc

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="builder test ü ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "original.ext4"
        with self.image.open("wb") as stream:
            stream.truncate(16 * 1024**2)
        status, _, _ = run_tool([self.mkfs, "-q", "-t", "ext4", "-F", str(self.image)])
        self.assertEqual(status, 0)
        self.fs = Ext4(self.image, self.tools["debugfs"], self.tools["e2fsck"])
        self.fs.check()
        self.members = self.root / "members"
        self.members.mkdir()
        (self.members / "fwz.xml").write_bytes(MANIFEST)
        with zipfile.ZipFile(self.members / "uImage.zip", "w", compression=zipfile.ZIP_STORED) as kernel:
            kernel.writestr("uImage", b"synthetic kernel" * 1024)
        self.stock = self.root / "stock.fwz"
        self.output = self.root / "output.fwz"
        self.profile = ExitStack()
        self.addCleanup(self.profile.close)
        self.restock()

    def restock(self):
        self.profile.close()
        self.profile = ExitStack()
        self.addCleanup(self.profile.close)
        for name in ("btweb_only.ext4.gz", "btweb_only_recovery.ext4.gz"):
            with self.image.open("rb") as source, gzip.open(self.members / name, "wb") as target:
                shutil.copyfileobj(source, target)
        self.stock.unlink(missing_ok=True)
        builder.pack(self.members, self.stock, self.tools["7zip"])
        digest = hashlib.sha256(self.stock.read_bytes()).hexdigest()
        preserved = {name: hashlib.sha256((self.members / name).read_bytes()).hexdigest()
                     for name in firmware.PRESERVED_SHA256}
        with self.image.open("rb") as stream:
            geom = firmware.geometry(stream.read(2048))
        changes = ((firmware, "PRESERVED_SHA256", preserved), (firmware, "MAIN_GEOMETRY", geom),
                   (firmware, "MAIN_SIZE", self.image.stat().st_size),
                   (builder, "MAIN_SIZE", self.image.stat().st_size),
                   (builder, "STOCK_SIZE", self.stock.stat().st_size),
                   (builder, "STOCK_SHA256", digest))
        for module, name, value in changes:
            self.profile.enter_context(patch.object(module, name, value))

    def commands(self, text, image=None):
        commands = self.root / "commands.debugfs"
        commands.write_text(text)
        fs = self.fs if image is None else Ext4(image, self.tools["debugfs"], self.tools["e2fsck"])
        fs.apply(commands, self.root)

    def payload(self, name="example", commands="", verify=None):
        path = self.root / name
        path.mkdir()
        (path / "payload.json").write_text(json.dumps({"id": name, "version": "1", "profile": firmware.PROFILE}))
        (path / "apply.debugfs").write_text(commands)
        if verify:
            (path / "verify.py").write_text(verify)
        return path

    def build(self, **kwargs):
        return builder.build(self.stock, self.output, overrides=self.tools, **kwargs)

    def check_clean_failure(self):
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".classe100x-build-*")), [])

    def test_noop_roundtrip_preserves_rootfs_and_all_other_members(self):
        original = self.stock.read_bytes()
        report = self.build(report_path=self.root / "report.json")
        self.assertEqual(self.stock.read_bytes(), original)
        self.assertEqual(report["main_filesystem_sha256"], hashlib.sha256(self.image.read_bytes()).hexdigest())
        with firmware.prepare_firmware(self.output, temporary_parent=self.root) as prepared:
            for name, expected in firmware.PRESERVED_SHA256.items():
                self.assertEqual(hashlib.sha256((prepared.directory / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "report.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.glob(".classe100x-build-*")), [])

    def test_file_symlink_replacement_and_final_readback(self):
        data = self.root / "before"
        data.write_bytes(b"before")
        self.commands("write before /existing\n")
        self.restock()
        payload = self.payload(commands="rm /existing\nwrite asset /existing\nset_inode_field /existing mode 0100750\n"
                                       "set_inode_field /existing uid 17\nset_inode_field /existing gid 23\n"
                                       "symlink /link existing\n",
                               verify="from classe100x.payload import Context\nc=Context()\n"
                                      "c.image.require_file('/existing',b'after',mode=0o750,uid=17,gid=23)\n"
                                      "c.image.require_symlink('/link','existing')\n")
        (payload / "asset").write_bytes(b"after")
        result = self.build(payloads=[payload])
        self.assertEqual(result["payloads"][0]["verification"], "passed")

    def test_midbatch_failure_with_zero_exit_is_rejected(self):
        bad = self.payload(commands="write missing /missing\nmkdir /after_failure\n")
        with self.assertRaisesRegex(FirmwareError, "operation error"):
            self.build(payloads=[bad])
        self.check_clean_failure()

    def test_full_image_failure_is_not_accepted(self):
        bad = self.payload(commands="write enormous /enormous\n")
        (bad / "enormous").write_bytes(b"x" * (20 * 1024**2))
        with self.assertRaises(FirmwareError):
            self.build(payloads=[bad])
        self.check_clean_failure()

    def test_preexisting_filesystem_errors_stop_without_repair(self):
        (self.root / "asset").write_bytes(b"fixture")
        self.commands("write asset /broken\nset_inode_field /broken links_count 2\n")
        self.restock()
        before = self.stock.read_bytes()
        with self.assertRaisesRegex(FirmwareError, "Filesystem check failed"):
            self.build()
        self.assertEqual(self.stock.read_bytes(), before)
        self.check_clean_failure()

    def test_later_payload_breaking_an_earlier_result_fails(self):
        first = self.payload("first", "mkdir /required\n", "from classe100x.payload import Context\nContext().image.stat('/required')\n")
        second = self.payload("second", "rmdir /required\n")
        with self.assertRaisesRegex(FirmwareError, "verify.py"):
            self.build(payloads=[first, second])
        self.check_clean_failure()

    def test_duplicate_payloads_and_unsupported_profile_are_rejected(self):
        payload = self.payload()
        with self.assertRaisesRegex(FirmwareError, "twice"):
            self.build(payloads=[payload, payload])
        manifest = payload / "payload.json"
        manifest.write_text(manifest.read_text().replace("c100x-1.5.8", "other"))
        with self.assertRaisesRegex(FirmwareError, "incompatible"):
            self.build(payloads=[payload])
        self.check_clean_failure()

    def test_existing_outputs_and_input_aliases_are_never_overwritten(self):
        original = self.stock.read_bytes()
        for kind in ("existing", "symlink", "hardlink"):
            if kind == "existing":
                self.output.write_bytes(b"existing")
            elif kind == "symlink":
                self.output.symlink_to(self.stock)
            else:
                os.link(self.stock, self.output)
            with self.assertRaisesRegex(FirmwareError, "exists"):
                self.build()
            self.assertEqual(self.stock.read_bytes(), original)
            self.output.unlink()

    def test_cancellation_during_pack_leaves_no_output(self):
        with patch.object(builder, "pack", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.build()
        self.check_clean_failure()

    def test_termination_signals_cleanup_and_restore_handlers(self):
        for sig in (signal.SIGTERM, signal.SIGHUP):
            previous = signal.getsignal(sig)
            with self.subTest(signal=sig), patch.object(builder, "pack", side_effect=lambda *args: os.kill(os.getpid(), sig)):
                with self.assertRaises(KeyboardInterrupt):
                    self.build()
            self.assertEqual(signal.getsignal(sig), previous)
            self.check_clean_failure()

    def test_report_failure_preserves_verified_image_and_explains_publication(self):
        with patch.object(builder.tempfile, "mkstemp", side_effect=PermissionError):
            with self.assertRaisesRegex(FirmwareError, "Firmware was published"):
                self.build(report_path=self.root / "report.json")
        self.assertTrue(self.output.is_file())
        self.assertFalse((self.root / "report.json").exists())
        with firmware.prepare_firmware(self.output):
            pass

    def test_hook_errors_do_not_expose_arbitrary_exception_text(self):
        payload = self.payload()
        (payload / "prepare.py").write_text("raise RuntimeError('private-input-must-not-leak')\n")
        with self.assertRaises(FirmwareError) as error:
            self.build(payloads=[payload])
        self.assertNotIn("private-input-must-not-leak", str(error.exception))
        (payload / "prepare.py").write_text("from classe100x.firmware import FirmwareError\nraise FirmwareError('Missing required public-key input')\n")
        with self.assertRaisesRegex(FirmwareError, "Missing required public-key input"):
            self.build(payloads=[payload])

    def test_required_verifier_cannot_disappear_during_preparation(self):
        payload = self.payload(verify="pass\n")
        manifest = json.loads((payload / "payload.json").read_text())
        manifest["verification_required"] = True
        (payload / "payload.json").write_text(json.dumps(manifest))
        (payload / "prepare.py").write_text("from pathlib import Path\nPath('verify.py').unlink()\n")
        with self.assertRaisesRegex(FirmwareError, "requires verify.py"):
            self.build(payloads=[payload])
        self.check_clean_failure()

    def test_unicode_and_spaces_in_image_paths(self):
        payload = self.payload(commands='write "asset ü" "/target ü"\nset_inode_field "/target ü" mode 0100640\n',
                               verify="from classe100x.payload import Context\nContext().image.require_file('/target ü',b'fixture',mode=0o640)\n")
        (payload / "asset ü").write_bytes(b"fixture")
        self.build(payloads=[payload])

    def test_selected_legacy_compression_flags_remain_supported(self):
        data = bytearray(self.stock.read_bytes())
        with zipfile.ZipFile(self.stock) as archive:
            for entry in archive.infolist():
                struct.pack_into("<H", data, entry.header_offset + 6, 3)
            offset = archive.start_dir
            for _ in archive.infolist():
                self.assertEqual(data[offset:offset + 4], b"PK\x01\x02")
                struct.pack_into("<H", data, offset + 8, 3)
                name, extra, comment = struct.unpack_from("<3H", data, offset + 28)
                offset += 46 + name + extra + comment
        legacy = self.root / "legacy.fwz"
        legacy.write_bytes(data)
        with firmware.prepare_firmware(legacy):
            pass

    def test_vendor_stock_version_upper_byte_is_supported_and_compared(self):
        data = bytearray(self.stock.read_bytes())
        with zipfile.ZipFile(self.stock) as archive:
            for entry in archive.infolist():
                struct.pack_into("<H", data, entry.header_offset + 4, 0x0314)
            offset = archive.start_dir
            for _ in archive.infolist():
                struct.pack_into("<H", data, offset + 6, 0x0314)
                name, extra, comment = struct.unpack_from("<3H", data, offset + 28)
                offset += 46 + name + extra + comment
        variant = self.root / "vendor-headers.fwz"
        variant.write_bytes(data)
        with firmware.prepare_firmware(variant):
            pass
        # A mismatch between local and central high bytes is still rejected.
        data[5] = 0
        variant.write_bytes(data)
        with self.assertRaisesRegex(FirmwareError, "headers"):
            with firmware.prepare_firmware(variant):
                self.fail("mismatched version field")

    def test_firmware_inspection_does_not_import_builder_dependencies(self):
        # Simulate a flasher-only installation; even importing a builder module fails.
        from classe100x.__main__ import main
        import contextlib
        import io
        with patch.dict(sys.modules, {name: None for name in ("classe100x.builder", "classe100x.host", "classe100x.ext4")}), \
                patch.object(sys, "argv", ["classe100x", "inspect-fw", str(self.stock)]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            old_umask = os.umask(0o077)
            try:
                self.assertEqual(main(), 0)
            finally:
                os.umask(old_umask)

    def test_corrupt_original_and_changed_preserved_component_rejected(self):
        self.stock.write_bytes(b"corrupt")
        with self.assertRaises(FirmwareError):
            self.build()
        self.check_clean_failure()
        self.stock.unlink()
        (self.members / "fwz.xml").write_bytes(MANIFEST.replace(b"C100X", b"C300X"))
        builder.pack(self.members, self.stock, self.tools["7zip"])
        with self.assertRaises(FirmwareError):
            with firmware.prepare_firmware(self.stock, temporary_parent=self.root):
                self.fail("wrong model")

    def test_unsigned_and_duplicate_outer_archives_are_rejected(self):
        for duplicate in (False, True):
            archive = self.root / f"invalid-{duplicate}.fwz"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for name in builder.MEMBER_ORDER:
                    z.write(self.members / name, name)
                if duplicate:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        z.write(self.members / "fwz.xml", "fwz.xml")
            with self.assertRaises(FirmwareError):
                with firmware.prepare_firmware(archive, temporary_parent=self.root):
                    self.fail("invalid outer archive")

    def test_local_header_mismatch_and_changed_recovery_are_rejected(self):
        data = bytearray(self.stock.read_bytes())
        # Change only the local encryption flag; the central directory still claims encryption.
        data[6:8] = struct.pack("<H", 0)
        bad = self.root / "bad-local.fwz"
        bad.write_bytes(data)
        with self.assertRaisesRegex(FirmwareError, "headers"):
            with firmware.prepare_firmware(bad):
                self.fail("inconsistent encryption")
        (self.members / "btweb_only_recovery.ext4.gz").write_bytes(gzip.compress(self.image.read_bytes(), mtime=123))
        builder.pack(self.members, self.root / "changed-recovery.fwz", self.tools["7zip"])
        with self.assertRaisesRegex(FirmwareError, "Recovery/kernel"):
            with firmware.prepare_firmware(self.root / "changed-recovery.fwz"):
                self.fail("changed recovery")

    def test_guarded_replacement_rejects_xattrs_and_hardlinks(self):
        (self.root / "asset").write_bytes(b"fixture")
        self.commands("write asset /existing\n")
        context = Context.__new__(Context)
        context.image = self.fs
        expected = hashlib.sha256(b"fixture").hexdigest()
        self.assertEqual(context.stock_file("/existing", expected), b"fixture")
        self.commands("ea_set /existing user.test fixture\n")
        with self.assertRaises(FirmwareError):
            context.stock_file("/existing", expected)
        self.commands("ea_rm /existing user.test\nset_inode_field /existing links_count 2\n")
        with self.assertRaises(FirmwareError):
            context.stock_file("/existing", expected)

    def test_binary_service_example_installs_but_never_executes_assets(self):
        self.commands("mkdir /etc\nmkdir /etc/init.d\nmkdir /etc/rc5.d\nmkdir /usr\nmkdir /usr/bin\n")
        self.restock()
        binary = self.root / "device-binary"
        header = bytearray(4096)
        header[:6] = b"\x7fELF\x01\x01"
        header[18:20] = b"\x28\x00"
        binary.write_bytes(header)
        config = self.root / "config"
        config.write_text("broker=fixture\npassword=synthetic-private-value\n")
        service = self.root / "service"
        service.write_text("#!/bin/sh\nexit 77\n")
        result = self.build(payloads=[builder.BUNDLED / "binary-service"], inputs={"binary-service": {
            "binary": str(binary), "binary_sha256": hashlib.sha256(header).hexdigest(),
            "configuration": str(config), "service": str(service)}})
        self.assertEqual(result["payloads"][0]["verification"], "passed")
        self.assertNotIn("synthetic-private-value", json.dumps(result))

    def test_ssh_modes_on_synthetic_stock_and_sensitive_report_redaction(self):
        try:
            find_tool("dropbearkey")
            find_tool("openssl")
            keygen = find_tool("ssh-keygen")
        except FirmwareError as exc:
            self.skipTest(str(exc))
        # Vendor-free stock-shaped files; substitute only their hashes in a private
        # copy of the payload. Exercise the real preparation/apply/verification code.
        originals = {
            "/etc/init.d/dropbear": b"#!/bin/sh\n# synthetic init\n",
            "/etc/default/dropbear": b'\nDROPBEAR_EXTRA_ARGS="-B"\nDROPBEAR_RSAKEY_DIR=/var/lib/dropbear\n',
            "/etc/passwd": b"root:x:0:0:root:/home/root:/bin/sh\nvendor:x:1000:1000:vendor:/home/vendor:/bin/sh\n",
            "/etc/shadow": b"root:*:18033:0:99999:7:::\nvendor:*:18033:0:99999:7:::\n",
            "/etc/inittab": b"id:5:initdefault:\n",
            "/usr/sbin/dropbearmulti": b"synthetic daemon\n",
        }
        setup = "".join(f"mkdir {p}\n" for p in ("/etc", "/etc/init.d", "/etc/default", "/etc/dropbear", "/etc/rc5.d",
                                                     "/home", "/home/root", "/usr", "/usr/sbin"))
        setup += "set_inode_field /home/root mode 040700\n"
        for index, (target, data) in enumerate(originals.items()):
            name = f"stock-{index}"
            (self.root / name).write_bytes(data)
            setup += f"write {name} {target}\nset_inode_field {target} mode 0100755\n"
        setup += "symlink /usr/sbin/dropbear ./dropbearmulti\n"
        self.commands(setup)
        self.restock()
        payload = self.root / "ssh-source"
        shutil.copytree(builder.BUNDLED / "ssh", payload)
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in originals.items()}
        with (payload / "common.py").open("a") as stream:
            stream.write("\nHASHES = " + repr(hashes) + "\n")
        key = self.root / "login"
        status, _, _ = run_tool([keygen, "-q", "-t", "ecdsa", "-b", "256", "-N", "", "-f", str(key)])
        self.assertEqual(status, 0)
        password = "synthetic-password-never-report"
        for mode, values in (("key", {"public_key": str(key) + ".pub"}),
                             ("password", {"password": password}),
                             ("both", {"password": password, "public_key": str(key) + ".pub"})):
            with self.subTest(mode=mode):
                result = self.build(payloads=[payload], inputs={"ssh": values})
                self.assertNotIn(password, json.dumps(result))
                self.assertNotIn(key.with_suffix(".pub").read_text().split()[1], json.dumps(result))
                self.output.unlink()
