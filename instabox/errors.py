"""
InstaBox SDK Exceptions.
"""
from __future__ import annotations
from typing import Any, Optional


class InstaboxError(Exception):
    """Base exception for all InstaBox API errors."""

    def __init__(
        self,
        message: str,
        status: int = 0,
        code: str = "unknown",
        request_id: Optional[str] = None,
        retryable: bool = False,
        operation_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id
        self.retryable = retryable
        self.operation_id = operation_id

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message={str(self)!r}, "
            f"status={self.status}, code={self.code!r}, "
            f"request_id={self.request_id!r}, retryable={self.retryable})"
        )


class InstaboxAuthError(InstaboxError):
    """Raised when authentication fails (401 or 403 insufficient scope or missing key)."""
    pass


class InstaboxQuotaError(InstaboxError):
    """Raised when account quotas or rate limits are exceeded (429 quota_exceeded)."""
    pass


class InstaboxTimeoutError(InstaboxError):
    """Raised when a request or long-running operation exceeds its timeout deadline."""
    pass


class CommandExitError(InstaboxError):
    """Raised when an executed command terminates with a non-zero exit status."""

    def __init__(
        self,
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
        timed_out: bool = False,
        truncated: bool = False,
        error: Optional[str] = None,
    ) -> None:
        tail = stderr.strip().split("\n")[-1] if stderr.strip() else ""
        msg = f"command exited with code {exit_code}"
        if tail:
            msg += f": {tail}"
        super().__init__(msg, code="command_exit")
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.truncated = truncated
        self.error = error
