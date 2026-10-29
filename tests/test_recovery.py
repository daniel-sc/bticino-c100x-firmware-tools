"""Offline recovery gate: real ext4 analysis, synthetic SSH partition reads."""

import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from classe100x import recovery
from classe100x.firmware import FirmwareError, Payload, PreparedFirmware
from classe100x.host import find_tool, run_tool
from classe100x.ssh import SSHError
from classe100x.updater import UpdateError, flash
from classe100x.vendor import C100X_PROFILE
from test_updater import SimulatedDevice


MIB = 1024**2
IMAGE_BYTES = 8 * MIB
SIZES = {"mmcblk2p2": IMAGE_BYTES, "mmcblk2p3": IMAGE_BYTES + MIB}


def inspection(*, devices=(178, 179), mounted="0:1", sizes=None):
    lines = []
    for (name, size), minor in zip((sizes or SIZES).items(), devices):
        lines.extend((f"PARTITION:{name}", str(size // 512), f"179:{minor}",
                      f"b3:{minor:x}", name[-1]))
    # The source path intentionally conceals the underlying recovery device.
    lines.extend(("MOUNTS", f"24 1 {mounted} / /alias rw,relatime - ext4 /dev/disk/by-label/alias rw"))
    return ("\n".join(lines) + "\n").encode()


class FixtureSSH:
    """The SSH boundary's length-checked output contract, backed by local images."""

    def __init__(self, images):
        self.images = images
        self.uid, self.gid = os.getuid(), os.getgid()
        self.host_keys = [{"fingerprint": "SHA256:synthetic", "status": "first_seen"}]
        self.calls = []
        self.inspection = inspection()
        self.fault = None
        self.closed = False
        self.after_read = None

    def __enter__(self):
        return self

    def close(self):
        self.closed = True

    def run(self, command, *, timeout, output=None, expected_size=None):
        assert timeout > 0
        self.calls.append(command)
        if self.fault == "authentication":
            raise SSHError("Synthetic authentication failure")
        if command == recovery.inspection_command():
            return self.inspection
        if command == "true":
            if self.fault == "readiness":
                raise SSHError("Synthetic SSH not ready")
            return b""
        if output is not None:
            name = command.split("if=/dev/", 1)[1].split()[0]
            assert command == f"dd if=/dev/{name} bs=1048576 count={SIZES[name] // MIB}"
            assert expected_size == SIZES[name]
            shutil.copyfile(self.images[name], output)
            if self.fault == "cancel":
                raise KeyboardInterrupt
            if self.fault == "short":
                with output.open("r+b") as stream:
                    stream.truncate(expected_size - 1)
            if output.stat().st_size != expected_size:
                raise SSHError("Synthetic partition read length mismatch")
            if self.fault == "transfer":
                raise SSHError("Synthetic established transfer failed")
            if self.after_read:
                self.after_read()
            return b""
        if command.startswith("sha256sum /dev/"):
            name = command.rsplit("/", 1)[1]
            value = hashlib.sha256(self.images[name].read_bytes()).hexdigest()
            if self.fault == "hash":
                value = "0" * 64
            if self.fault == "malformed-hash":
                return b"not a checksum\n"
            return f"{value}  /dev/{name}\n".encode()
        raise AssertionError(f"Unexpected remote command: {command}")


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(recovery, "PARTITIONS", SIZES))

    def test_unmounted_devices_identified_by_matching_node_and_sysfs_numbers(self):
        self.assertEqual(recovery.parse_inspection(inspection()), {
            "mmcblk2p2": {"device": "179:178", "bytes": IMAGE_BYTES},
            "mmcblk2p3": {"device": "179:179", "bytes": IMAGE_BYTES + MIB},
        })

    def test_mount_alias_is_rejected_by_device_number(self):
        for device in ("179:178", "179:179"):
            with self.subTest(device=device), self.assertRaisesRegex(UpdateError, "mounted"):
                recovery.parse_inspection(inspection(mounted=device))

    def test_ambiguous_or_inconsistent_identity_is_rejected(self):
        for data in (inspection(devices=(178, 178)),
                     inspection().replace(b"b3:b2", b"b3:b4"),
                     inspection(sizes={**SIZES, "mmcblk2p3": IMAGE_BYTES}),
                     inspection().replace(b"MOUNTS\n", b""),
                     inspection().split(b"MOUNTS")[0] + b"MOUNTS\n",
                     b"\xff", b""):
            with self.subTest(data=data), self.assertRaises(UpdateError):
                recovery.parse_inspection(data)


class RecoveryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.tools = {name: find_tool(name) for name in ("mke2fs", "debugfs", "e2fsck")}
        except FirmwareError as exc:
            if os.environ.get("CI") or os.environ.get("CLASSE100X_REQUIRE_BUILDER_TOOLS"):
                raise
            raise unittest.SkipTest("Install e2fsprogs for recovery integration tests") from exc
        cls.fixtures = tempfile.TemporaryDirectory(prefix="recovery fixtures ü ")
        cls.addClassCleanup(cls.fixtures.cleanup)
        cls.source = Path(cls.fixtures.name)
        kernel_files = cls.source / "kernel-files"
        kernel_files.mkdir()
        for name in ["uImage", *(f"board-{index}.dtb" for index in range(20))]:
            (kernel_files / name).write_bytes((f"synthetic {name}\n" * 50).encode())
        root_files = cls.source / "root-files"
        root_files.mkdir()
        (root_files / "payload").write_bytes(b"synthetic recovery data\n" * 100)
        for name, contents in (("kernel.ext4", kernel_files), ("root.ext4", root_files)):
            image = cls.source / name
            with image.open("wb") as stream:
                stream.truncate(IMAGE_BYTES)
            cls.command([cls.tools["mke2fs"], "-q", "-t", "ext4", "-F", "-d", str(contents), str(image)])
            if name == "kernel.ext4":
                cls.command([cls.tools["debugfs"], "-w", "-R", "rmdir /lost+found", str(image)])
            cls.command([cls.tools["e2fsck"], "-f", "-n", str(image)])
        with gzip.open(cls.source / "btweb_only_recovery.ext4.gz", "wb") as target:
            target.write((cls.source / "root.ext4").read_bytes())
        with zipfile.ZipFile(cls.source / "uImage.zip", "w") as archive:
            for path in sorted(kernel_files.iterdir()):
                archive.write(path, path.name)

    @staticmethod
    def command(args, **kwargs):
        status, out, err = run_tool(args, **kwargs)
        if status:
            raise AssertionError(f"Synthetic fixture command failed: {args}: {out!r} {err!r}")

    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix="recovery run ü "))
        self.root = Path(directory)
        self.images = {}
        for partition, source in (("mmcblk2p2", "kernel.ext4"), ("mmcblk2p3", "root.ext4")):
            self.images[partition] = self.root / f"{partition}.img"
            shutil.copyfile(self.source / source, self.images[partition])
        with self.images["mmcblk2p3"].open("ab") as target:
            target.write(b"outside-reference-extent".ljust(MIB, b"!"))
        self.enterContext(patch.object(recovery, "PARTITIONS", SIZES))
        self.enterContext(patch.object(recovery, "ROOTFS_BYTES", IMAGE_BYTES))
        self.firmware = PreparedFirmware(self.source, "synthetic-firmware-sha256", tuple(
            Payload(name, 100, "synthetic", 123) for name in (
                "btweb_only.ext4.gz", "btweb_only_recovery.ext4.gz", "uImage.zip")))
        self.ssh = FixtureSSH(self.images)
        self.messages = []
        self.verifier = recovery.RecoveryVerifier(self.firmware, self.ssh, parent=self.root,
                                                  progress=self.messages.append)
        self.device = SimulatedDevice()

    def update(self):
        with self.verifier:
            return flash(self.firmware, self.device, C100X_PROFILE, report=self.messages.append,
                         verification=self.verifier)

    def report(self):
        return json.loads((self.verifier.directory / "report.json").read_text())

    def assert_stopped_before_invalidation(self, *, preflight=False, message=None):
        with self.assertRaises(UpdateError) as caught:
            self.update()
        if message:
            self.assertIn(message, str(caught.exception))
        self.assertNotIn("invalidate-main-kernel", self.device.events)
        self.assertNotIn("begin-main", self.device.events)
        self.assertEqual(self.device.events[-1], "close")
        if preflight:
            self.assertEqual(self.device.events, ["connect", "close"])
        else:
            self.assertEqual(self.device.events.count("reboot-4"), 1)
        record = self.report()
        self.assertEqual(record["update_sequence"], "stopped")
        self.assertEqual(record["raw_copies"], "removed")
        self.assertFalse(self.verifier.workspace.exists())
        self.assertTrue(self.ssh.closed)
        return record

    def debugfs(self, partition, commands):
        script = self.root / "fixture.debugfs"
        script.write_text(commands)
        self.command([self.tools["debugfs"], "-w", "-f", str(script), str(self.images[partition])],
                     cwd=self.root)

    def test_exact_extent_excludes_tail_and_publishes_private_evidence(self):
        invalidate = self.device.invalidate_main_kernel

        def checked_invalidate():
            persisted = self.report()
            self.assertEqual(persisted["verification"], "passed")
            self.assertEqual(persisted["update_sequence"], "in_progress")
            images = list(self.verifier.workspace.glob("*.img"))
            self.assertEqual(len(images), 2)
            for image in images:
                self.assertEqual(image.stat().st_mode & 0o777, 0o600)
                self.assertEqual(image.stat().st_uid, os.getuid())
            invalidate()

        with patch.object(self.device, "invalidate_main_kernel", side_effect=checked_invalidate):
            self.update()
        record = self.report()
        self.assertEqual(record["verification"], "passed")
        self.assertEqual(record["update_sequence"], "completed")
        self.assertEqual(record["functional_acceptance"], "not_performed")
        self.assertEqual(record["reference"]["rootfs_bytes"], IMAGE_BYTES)
        self.assertTrue(record["rootfs_matches"])
        self.assertTrue(record["kernel_files_match"])
        self.assertEqual(len(record["reference"]["kernel_files"]), 21)
        for name in SIZES:
            self.assertEqual(record["partitions"][name]["bytes"], SIZES[name])
            self.assertEqual(record["partitions"][name]["filesystem_check"], "passed")
            self.assertEqual(sum(c.startswith(f"dd if=/dev/{name} ") for c in self.ssh.calls), 1)
            self.assertEqual(self.ssh.calls.count(f"sha256sum /dev/{name}"), 1)
        self.assertEqual(self.verifier.directory.stat().st_mode & 0o777, 0o700)
        report_path = self.verifier.directory / "report.json"
        self.assertEqual(report_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(report_path.stat().st_uid, os.getuid())
        self.assertEqual(list(self.verifier.directory.iterdir()), [report_path])
        self.assertTrue(any(str(self.verifier.directory) in message for message in self.messages))
        self.assertTrue(self.ssh.closed)

    def test_corrupt_kernel_content_blocks_gate(self):
        original = (self.source / "kernel-files" / "uImage").read_bytes()
        (self.root / "changed").write_bytes(b"X" * len(original))
        self.debugfs("mmcblk2p2", "rm /uImage\nwrite changed /uImage\n")
        self.assert_stopped_before_invalidation(message="content differs from stock")
        self.assertFalse(self.report().get("kernel_files_match", False))

    def test_unexpected_kernel_file_blocks_gate(self):
        (self.root / "changed").write_bytes(b"unexpected")
        self.debugfs("mmcblk2p2", "write changed /unexpected.dtb\n")
        self.assert_stopped_before_invalidation(message="file set or lengths differ from stock")

    def test_rootfs_data_difference_blocks_gate(self):
        (self.root / "changed").write_bytes(b"modified recovery contents")
        self.debugfs("mmcblk2p3", "rm /payload\nwrite changed /payload\n")
        self.assert_stopped_before_invalidation(message="filesystem bytes differ from stock")

    def test_rootfs_metadata_difference_is_not_tolerated(self):
        self.debugfs("mmcblk2p3", "set_inode_field /payload mode 0100600\n")
        record = self.assert_stopped_before_invalidation(message="filesystem bytes differ from stock")
        self.assertEqual(record["partitions"]["mmcblk2p3"]["filesystem_check"], "passed")
        self.assertFalse(record.get("rootfs_matches", False))

    def test_filesystem_corruption_fails_read_only_check(self):
        # A bad free-block count leaves the files intact but makes fsck fail.
        image = self.images["mmcblk2p2"]
        with image.open("r+b") as stream:
            stream.seek(1024 + 12)
            stream.write(struct.pack("<I", 0))
        before = hashlib.sha256(image.read_bytes()).hexdigest()
        record = self.assert_stopped_before_invalidation()
        self.assertNotIn("filesystem_check", record["partitions"]["mmcblk2p2"])
        self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), before)

    def test_readback_failures_and_cancellation_block_gate_without_retry(self):
        for fault in ("short", "transfer", "hash", "malformed-hash", "cancel"):
            with self.subTest(fault=fault):
                self.ssh = FixtureSSH(self.images)
                self.ssh.fault = fault
                self.verifier = recovery.RecoveryVerifier(self.firmware, self.ssh, parent=self.root,
                                                          progress=self.messages.append)
                self.device = SimulatedDevice()
                self.assert_stopped_before_invalidation()
                self.assertEqual(sum(c.startswith("dd ") for c in self.ssh.calls), 1)

    def test_identity_drift_after_read_blocks_gate(self):
        self.ssh.after_read = lambda: setattr(self.ssh, "inspection", inspection(devices=(180, 181)))
        self.assert_stopped_before_invalidation()

    def test_mount_alias_appearing_after_read_blocks_gate(self):
        self.ssh.after_read = lambda: setattr(self.ssh, "inspection", inspection(mounted="179:178"))
        self.assert_stopped_before_invalidation()

    def test_preflight_authentication_failure_permits_no_writes(self):
        self.ssh.fault = "authentication"
        record = self.assert_stopped_before_invalidation(preflight=True)
        self.assertEqual(record["preflight"], "failed")
        self.assertEqual(record["verification"], "not_started")

    def test_preflight_missing_tool_permits_no_writes(self):
        with patch.object(recovery, "find_tool", side_effect=FirmwareError("Missing tool")):
            self.assert_stopped_before_invalidation(preflight=True)
        self.assertEqual(self.ssh.calls, [])

    def test_preflight_mounted_partition_permits_no_writes(self):
        self.ssh.inspection = inspection(mounted="179:179")
        self.assert_stopped_before_invalidation(preflight=True, message="mounted")

    def test_partition_length_drift_after_preflight_blocks_gate(self):
        self.ssh.after_read = lambda: setattr(self.ssh, "inspection", inspection(
            sizes={**SIZES, "mmcblk2p3": IMAGE_BYTES}))
        self.assert_stopped_before_invalidation(message="identity or size")

    def test_preflight_insufficient_storage_permits_no_writes(self):
        usage = SimpleNamespace(free=1)
        with patch.object(recovery.shutil, "disk_usage", return_value=usage):
            self.assert_stopped_before_invalidation(preflight=True)
        self.assertEqual(self.ssh.calls, [])

    def test_readiness_timeout_is_bounded_without_partition_reads(self):
        clock = [0]
        self.ssh.fault = "readiness"

        def sleep(seconds):
            clock[0] += seconds

        with patch.object(recovery.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(recovery.time, "sleep", side_effect=sleep):
            self.assert_stopped_before_invalidation()
        self.assertEqual(clock[0], 120)
        self.assertFalse(any(c.startswith("dd ") for c in self.ssh.calls))

    def test_acquisition_deadline_stops_without_second_read(self):
        clock = [0]
        self.ssh.after_read = lambda: clock.__setitem__(0, 901)
        with patch.object(recovery.time, "monotonic", side_effect=lambda: clock[0]):
            self.assert_stopped_before_invalidation()
        self.assertEqual(sum(c.startswith("dd ") for c in self.ssh.calls), 1)

    def test_analysis_shares_acquisition_deadline(self):
        clock = [0]
        original = recovery.run_tool

        def tool(arguments, **kwargs):
            result = original(arguments, **kwargs)
            if "-f" in arguments and "-n" in arguments:
                clock[0] += 901
            return result

        with patch.object(recovery.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(recovery, "run_tool", side_effect=tool):
            self.assert_stopped_before_invalidation(message="time limit")
        self.assertEqual(sum(c.startswith("dd ") for c in self.ssh.calls), 1)

    def test_preflight_report_publication_failure_permits_no_writes(self):
        # Fail only the prerequisite publication, after startup created evidence.
        with self.assertRaises(UpdateError):
            with self.verifier:
                with patch.object(recovery.os, "replace", side_effect=PermissionError("Synthetic disk failure")):
                    flash(self.firmware, self.device, C100X_PROFILE, report=self.messages.append,
                          verification=self.verifier)
        self.assertEqual(self.device.events, ["connect", "close"])
        self.assertEqual(self.report()["update_sequence"], "stopped")
        self.assertFalse(self.verifier.workspace.exists())
        self.assertTrue(self.ssh.closed)

    def test_publication_failure_before_invalidation_blocks_gate(self):
        real_replace = os.replace
        failed = []

        def replace(source, target, *args, **kwargs):
            if self.verifier.record["verification"] == "passed" and not failed:
                failed.append(True)
                raise PermissionError("Synthetic report publication failure")
            return real_replace(source, target, *args, **kwargs)

        with patch.object(recovery.os, "replace", side_effect=replace):
            self.assert_stopped_before_invalidation()
        self.assertEqual(failed, [True])
        self.assertFalse(any(p.name.startswith(".report-") for p in self.verifier.directory.iterdir()))

    def test_later_write_failure_preserves_integrity_evidence(self):
        self.device.fail = "commit-btweb_only.ext4.gz"
        with self.assertRaises(UpdateError):
            self.update()
        record = self.report()
        self.assertEqual(record["verification"], "passed")
        self.assertEqual(record["update_sequence"], "stopped")
        self.assertEqual(record["update_stage"], "main: writing btweb_only.ext4.gz")
        self.assertEqual(record["functional_acceptance"], "not_performed")
        self.assertFalse(self.verifier.workspace.exists())
