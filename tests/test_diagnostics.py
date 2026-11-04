import json
import subprocess
import unittest

from classe100x.diagnostics import clear_secrets, details, failure, format_failure, remember_secret, text


class DiagnosticsTests(unittest.TestCase):
    def tearDown(self):
        clear_secrets()

    def test_chains_notes_and_stack_survive_json_and_debug_rendering(self):
        try:
            try:
                raise ConnectionRefusedError(61, "Connection refused")
            except OSError as cause:
                raise details(RuntimeError("Preflight failed"), operation="SSH inspection") from cause
        except RuntimeError as error:
            record = json.loads(json.dumps(failure(error)))
            self.assertEqual(record["cause"]["errno"], 61)
            self.assertIn("test_chains_notes", record["traceback"])
            normal = format_failure(error)
            self.assertIn("Connection refused", normal)
            self.assertIn("operation: SSH inspection", normal)
            self.assertNotIn("Traceback (most recent", normal)
            self.assertIn("Traceback (most recent", format_failure(error, debug=True))

    def test_subprocess_details_exclude_argv_and_known_secret_but_keep_context(self):
        secret = "synthetic-private-password"
        remember_secret(secret)
        for error in (subprocess.CalledProcessError(7, ["/bin/tool", "hidden-argument"],
                                                  stderr=f"/Users/example/file: failed for root2 {secret}"),
                      subprocess.TimeoutExpired(["/bin/tool", "hidden-argument"], 5,
                                                stderr=b"partial diagnostic")):
            output = json.dumps(failure(error)) + format_failure(error, debug=True)
            self.assertNotIn(secret, output)
            self.assertNotIn("hidden-argument", output)
            self.assertIn("stderr", output)
        self.assertIn("/Users/example/file", format_failure(
            OSError(f"/Users/example/file: {secret}")))
        self.assertIn("[redacted]", text(secret))

    def test_bounded_text_control_characters_and_suppressed_or_cyclic_causes(self):
        self.assertEqual(text("before\x1b[2Jafter"), "before\\x1b[2Jafter")
        self.assertTrue(text("x" * 9000 + "last reason").endswith("last reason"))
        self.assertIn("truncated", text("x" * 9000))
        try:
            try:
                raise ValueError("intentionally hidden context")
            except ValueError:
                raise RuntimeError("replacement") from None
        except RuntimeError as error:
            self.assertNotIn("hidden context", format_failure(error))
            error.__cause__ = error
            self.assertEqual(failure(error)["message"], "replacement")
