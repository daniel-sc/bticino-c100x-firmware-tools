import hashlib
import http.client
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from classe100x import download
from classe100x.firmware import FirmwareError


class Response(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def geturl(self):
        return download.STOCK_URL


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.data = b"synthetic stock firmware"
        for name, value in (("STOCK_SIZE", len(self.data)),
                            ("STOCK_SHA256", hashlib.sha256(self.data).hexdigest())):
            p = patch.object(download, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_verified_download_and_cache_reuse_without_network(self):
        with patch.object(download.urllib.request, "urlopen", return_value=Response(self.data)) as get:
            path = download.fetch_stock(self.cache)
            self.assertEqual(path.read_bytes(), self.data)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(download.fetch_stock(self.cache), path)
            get.assert_called_once()

    def test_corrupt_truncated_oversized_and_wrong_length_responses_leave_no_file(self):
        for data, length in ((b"x" * len(self.data), None), (self.data[:-1], None),
                             (self.data + b"extra", None), (self.data, 1)):
            with self.subTest(length=length, size=len(data)):
                with patch.object(download.urllib.request, "urlopen", return_value=Response(data, length)):
                    with self.assertRaises(FirmwareError):
                        download.fetch_stock(self.cache)
                self.assertEqual(list(self.cache.iterdir()), [])

    def test_corrupt_cache_is_rejected_not_silently_replaced(self):
        with patch.object(download.urllib.request, "urlopen", return_value=Response(self.data)):
            path = download.fetch_stock(self.cache)
        path.write_bytes(b"bad")
        with patch.object(download.urllib.request, "urlopen") as get:
            with self.assertRaisesRegex(FirmwareError, "Cached"):
                download.fetch_stock(self.cache)
            get.assert_not_called()
        self.assertEqual(path.read_bytes(), b"bad")

    def test_cancellation_discards_partial(self):
        response = Response(self.data)
        response.read = lambda size: (_ for _ in ()).throw(KeyboardInterrupt())
        with patch.object(download.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(KeyboardInterrupt):
                download.fetch_stock(self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_broken_http_body_is_redacted_and_discarded(self):
        response = Response(self.data)
        def broken(size):
            raise http.client.IncompleteRead(b"private-partial-body", 100)
        response.read = broken
        with patch.object(download.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(FirmwareError, "Unable to download") as result:
                download.fetch_stock(self.cache)
        self.assertNotIn("private-partial-body", str(result.exception))
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_publication_never_overwrites_an_existing_file_or_symlink(self):
        src, dst = self.cache / "partial", self.cache / "output"
        src.write_bytes(b"new")
        dst.write_bytes(b"old")
        with self.assertRaises(FirmwareError):
            download.publish(src, dst)
        self.assertEqual(dst.read_bytes(), b"old")
        dst.unlink()
        dst.symlink_to(src)
        with self.assertRaises(FirmwareError):
            download.publish(src, dst)
        self.assertEqual(src.read_bytes(), b"new")
