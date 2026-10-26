import gzip
from pathlib import Path
import tempfile
import unittest
import zipfile

from classe100x.firmware import FirmwareError, _validate_payload, posix_cksum, prepare_firmware, validate_manifest


MANIFEST = b'''<fwz><name>C100X</name><fwz_ver>1.5.8</fwz_ver><xml_ver>3.0</xml_ver>
<device act_id="1"><object_models><object_model>1.0.99</object_model></object_models></device>
<actions id="1"><action provider="btesuv3" type="firmware">
<attr type="file">btweb_only.ext4.gz</attr><attr type="file">uImage.zip</attr></action>
<action provider="btesuv3" type="recovery_firmware">
<attr type="file">btweb_only_recovery.ext4.gz</attr><attr type="file">uImage.zip</attr>
</action></actions></fwz>'''


class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def test_posix_checksum_vectors(self):
        path = self.directory / "payload"
        for data, checksum in ((b"", 4294967295), (b"123456789", 930766865)):
            path.write_bytes(data)
            self.assertEqual(posix_cksum(path), checksum)

    def test_unresearched_image_rejected_without_staging(self):
        path = self.directory / "unknown.fwz"
        path.write_bytes(b"unresearched input")
        with self.assertRaisesRegex(FirmwareError, "SHA-256"):
            with prepare_firmware(path, b"unused", temporary_parent=self.directory):
                self.fail("must not yield an unresearched image")
        self.assertEqual(list(self.directory.iterdir()), [path])
        self.assertEqual(path.read_bytes(), b"unresearched input")

    def test_manifest_identity_and_payload_order(self):
        validate_manifest(MANIFEST)
        for data in (
            MANIFEST.replace(b"C100X", b"C300X"),
            MANIFEST.replace(b"1.0.99", b"1.0.98"),
            MANIFEST.replace(b"act_id=\"1\"", b"act_id=\"2\""),
            MANIFEST.replace(b"btweb_only.ext4.gz", b"../btweb_only.ext4.gz"),
            MANIFEST.replace(b"<attr type=\"file\">btweb_only.ext4.gz</attr><attr type=\"file\">uImage.zip</attr>",
                             b"<attr type=\"file\">uImage.zip</attr><attr type=\"file\">btweb_only.ext4.gz</attr>"),
            b'<!DOCTYPE fwz [<!ENTITY x "C100X">]>' + MANIFEST,
        ):
            with self.subTest(data=data[:40]), self.assertRaises(FirmwareError):
                validate_manifest(data)

    def test_gzip_trailer_is_checked_even_with_valid_ext_header(self):
        data = bytearray(4096)
        data[1080:1082] = b"\x53\xef"
        path = self.directory / "btweb_only.ext4.gz"
        path.write_bytes(gzip.compress(data))
        _validate_payload(path)
        path.write_bytes(path.read_bytes()[:-5])
        with self.assertRaises(EOFError):
            _validate_payload(path)

    def test_kernel_path_traversal_is_rejected(self):
        path = self.directory / "uImage.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../uImage", b"bad")
        with self.assertRaisesRegex(FirmwareError, "member"):
            _validate_payload(path)
