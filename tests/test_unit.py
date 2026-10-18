"""
Unit tests for instabox-py SDK.
"""
import unittest
from instabox.errors import (
    CommandExitError,
    InstaboxAuthError,
    InstaboxError,
    InstaboxQuotaError,
    InstaboxTimeoutError,
)
from instabox.http import _error_from_response
from instabox.models import CommandResult, FileEntry, SandboxInfo


class TestInstaboxErrors(unittest.TestCase):
    def test_error_mapping(self):
        err401 = _error_from_response(401, {"error": {"code": "invalid_api_key", "message": "Unauthorized"}}, "fallback")
        self.assertIsInstance(err401, InstaboxAuthError)
        self.assertEqual(err401.code, "invalid_api_key")
        self.assertEqual(str(err401), "Unauthorized")

        err403 = _error_from_response(403, {"error": {"code": "insufficient_scope", "message": "Forbidden"}}, "fallback")
        self.assertIsInstance(err403, InstaboxAuthError)

        err429 = _error_from_response(429, {"error": {"code": "quota_exceeded", "message": "Limit hit"}}, "fallback")
        self.assertIsInstance(err429, InstaboxQuotaError)

        err500 = _error_from_response(500, {"error": {"code": "server_error", "message": "Crash"}}, "fallback")
        self.assertIsInstance(err500, InstaboxError)

    def test_command_exit_error(self):
        err = CommandExitError(127, stdout="", stderr="command not found: foobar\n")
        self.assertEqual(err.exit_code, 127)
        self.assertIn("foobar", str(err))
        self.assertEqual(err.code, "command_exit")


class TestInstaboxModels(unittest.TestCase):
    def test_command_result(self):
        res = CommandResult(stdout="hello\n", stderr="", exit_code=0)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.stdout, "hello\n")
        self.assertFalse(res.timed_out)

    def test_file_entry(self):
        entry = FileEntry(name="main.rs", path="/data/home/main.rs", type="file")
        self.assertEqual(entry.name, "main.rs")
        self.assertEqual(entry.type, "file")


if __name__ == "__main__":
    unittest.main()
