"""
Command execution interface for InstaBox sandboxes.
"""
from __future__ import annotations
import shlex
import urllib.parse
from typing import Any, Callable, Dict, Optional, Union

from .errors import CommandExitError, InstaboxError
from .http import HttpClient
from .models import BackgroundProcess, CommandResult

MAX_STDIN_BYTES = 1024 * 1024


class Commands:
    """Manages command execution inside an active InstaBox sandbox."""

    def __init__(self, http: HttpClient, sandbox_id: str, default_envs: Optional[Dict[str, str]] = None) -> None:
        self.http = http
        self.sandbox_id = sandbox_id
        self.default_envs = default_envs or {}

    def run(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        envs: Optional[Dict[str, str]] = None,
        stdin: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        background: bool = False,
        on_stdout: Optional[Callable[[str], None]] = None,
        on_stderr: Optional[Callable[[str], None]] = None,
    ) -> Union[CommandResult, BackgroundProcess]:
        """Runs a command inside the sandbox.

        Raises CommandExitError if the command exits with non-zero status.
        If background=True, starts detached process and returns BackgroundProcess with PID and kill().
        """
        if background:
            if stdin is not None:
                raise InstaboxError("stdin is not supported for background commands", code="bad_request")
            quoted = shlex.quote(cmd)
            wrapped = f"command -v setsid >/dev/null || {{ echo 'setsid not found' >&2; exit 127; }}; setsid nohup sh -c {quoted} >/dev/null 2>&1 & echo $!"
            res = self.exec(wrapped, cwd=cwd, envs=envs, timeout_seconds=timeout_seconds)
            if res.exit_code != 0:
                raise CommandExitError(
                    res.exit_code,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    timed_out=res.timed_out,
                    truncated=res.truncated,
                    error=res.error,
                )
            try:
                pid = int(res.stdout.strip())
                if pid <= 0:
                    raise ValueError()
            except Exception as e:
                raise InstaboxError("exec returned an invalid background PID", code="invalid_response") from e

            return BackgroundProcess(
                pid=pid,
                kill=lambda: self.exec(f"kill -s TERM -- -{pid}").exit_code == 0,
            )

        res = self.exec(cmd, cwd=cwd, envs=envs, stdin=stdin, timeout_seconds=timeout_seconds)
        if on_stdout and res.stdout:
            on_stdout(res.stdout)
        if on_stderr and res.stderr:
            on_stderr(res.stderr)

        if res.exit_code != 0:
            raise CommandExitError(
                res.exit_code,
                stdout=res.stdout,
                stderr=res.stderr,
                timed_out=res.timed_out,
                truncated=res.truncated,
                error=res.error,
            )
        return res

    def exec(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        envs: Optional[Dict[str, str]] = None,
        stdin: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> CommandResult:
        """Low-level execution that returns exit code and output without raising CommandExitError."""
        merged_envs = {**self.default_envs, **(envs or {})}
        body: Dict[str, Any] = {"cmd": cmd}
        if cwd is not None:
            body["cwd"] = cwd
        if merged_envs:
            body["envs"] = merged_envs
        if stdin is not None:
            encoded_len = len(stdin.encode("utf-8"))
            if encoded_len > MAX_STDIN_BYTES:
                raise InstaboxError(f"stdin is longer than {MAX_STDIN_BYTES} bytes", code="bad_request")
            body["stdin"] = stdin
        if timeout_seconds is not None:
            if timeout_seconds <= 0 or timeout_seconds > 600:
                raise InstaboxError("command timeout_seconds must be between 1 and 600", code="bad_request")
            body["timeoutSeconds"] = timeout_seconds

        timeout_margin = (timeout_seconds or 60) + 30
        res = self.http.request(
            "POST",
            f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/exec",
            body=body,
            retry=False,
            idempotent=False,
            timeout=float(timeout_margin),
        )
        return CommandResult(
            stdout=res.get("stdout", ""),
            stderr=res.get("stderr", ""),
            exit_code=int(res.get("exitCode", 0)),
            timed_out=bool(res.get("timedOut", False)),
            truncated=bool(res.get("truncated", False)),
            error=res.get("error"),
        )
