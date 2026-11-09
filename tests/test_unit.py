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
    InvalidStateTransitionError,
)
from instabox.http import _error_from_response
from instabox.models import CommandResult, FileEntry, SandboxInfo, SandboxState


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

    def test_invalid_state_transition_error(self):
        err = InvalidStateTransitionError("terminated", "wake", valid_actions=[])
        self.assertEqual(err.code, "invalid_state_transition")
        self.assertIn("terminated", str(err))
        self.assertEqual(err.valid_actions, [])

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

    def test_sandbox_state_machine_model(self):
        info_running = SandboxInfo(sandbox_id="sbx-123", name="test", state="running")
        self.assertEqual(info_running.sandbox_state, SandboxState.RUNNING)
        self.assertTrue(info_running.is_running)
        self.assertFalse(info_running.is_terminal)
        self.assertIn("pause", info_running.valid_actions)
        self.assertIn("exec", info_running.valid_actions)

        info_term = SandboxInfo(sandbox_id="sbx-456", name="test", state="terminated")
        self.assertEqual(info_term.sandbox_state, SandboxState.TERMINATED)
        self.assertFalse(info_term.is_running)
        self.assertTrue(info_term.is_terminal)
        self.assertEqual(info_term.valid_actions, [])

        # Robust string normalization
        self.assertEqual(SandboxState.from_str("SUSPENDED"), SandboxState.SUSPENDED)
        self.assertEqual(SandboxState.from_str("some_unknown_val"), SandboxState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
