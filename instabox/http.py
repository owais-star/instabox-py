"""
HTTP Client for InstaBox API (Pure Standard Library - Zero Dependencies).
"""
from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from .errors import (
    InstaboxAuthError,
    InstaboxError,
    InstaboxQuotaError,
    InstaboxTimeoutError,
)

DEFAULT_API_URL = "https://api.instabox.sh"
DEFAULT_REQUEST_TIMEOUT = 60.0
DEFAULT_OPERATION_TIMEOUT = 600.0
MAX_RETRIES = 3


def _error_from_response(status: int, body: Any, fallback: str) -> InstaboxError:
    env = body.get("error", {}) if isinstance(body, dict) else {}
    code = env.get("code") if isinstance(env, dict) and isinstance(env.get("code"), str) else f"http_{status}"
    msg = env.get("message") if isinstance(env, dict) and isinstance(env.get("message"), str) else fallback
    req_id = env.get("requestId") if isinstance(env, dict) else None
    retryable = env.get("retryable") if isinstance(env, dict) and isinstance(env.get("retryable"), bool) else (502 <= status <= 504)
    op_id = env.get("operationId") if isinstance(env, dict) else None

    if status in (401, 403):
        return InstaboxAuthError(msg, status=status, code=code, request_id=req_id, retryable=retryable, operation_id=op_id)
    if status == 429:
        return InstaboxQuotaError(msg, status=status, code=code, request_id=req_id, retryable=retryable, operation_id=op_id)
    return InstaboxError(msg, status=status, code=code, request_id=req_id, retryable=retryable, operation_id=op_id)


class HttpClient:
    """Synchronous HTTP client for interacting with InstaBox control plane."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        operation_timeout: float = DEFAULT_OPERATION_TIMEOUT,
        poll_interval: float = 0.25,
        retry_delay: float = 0.25,
    ) -> None:
        resolved_key = api_key or os.getenv("INSTABOX_API_KEY")
        if not resolved_key:
            raise InstaboxAuthError(
                "No InstaBox API key. Set INSTABOX_API_KEY environment variable or pass api_key parameter.",
                code="missing_api_key",
            )
        self.api_key = resolved_key.strip()
        self.api_url = (api_url or os.getenv("INSTABOX_API_URL") or DEFAULT_API_URL).rstrip("/")
        self.request_timeout = request_timeout
        self.operation_timeout = operation_timeout
        self.poll_interval = poll_interval
        self.retry_delay = retry_delay

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Any] = None,
        query: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        idempotent: Optional[bool] = None,
        retry: Optional[bool] = None,
    ) -> Any:
        method = method.upper()
        is_read = method in ("GET", "HEAD")
        is_idempotent = (not is_read) if idempotent is None else idempotent
        can_retry_default = (is_read or is_idempotent) if retry is None else retry

        url = f"{self.api_url}{path}"
        if query:
            filtered_query = {k: v for k, v in query.items() if v is not None}
            if filtered_query:
                # Support multi-value query params
                encoded_pairs = []
                for k, v in filtered_query.items():
                    if isinstance(v, (list, tuple)):
                        for item in v:
                            encoded_pairs.append((k, str(item)))
                    else:
                        encoded_pairs.append((k, str(v)))
                url += f"?{urllib.parse.urlencode(encoded_pairs)}"

        headers: Dict[str, str] = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "instabox-py/0.1.0",
        }
        if is_idempotent:
            headers["Idempotency-Key"] = str(uuid.uuid4())

        data_bytes: Optional[bytes] = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data_bytes = json.dumps(body).encode("utf-8")

        req_timeout = timeout or self.request_timeout

        for attempt in range(MAX_RETRIES + 1):
            can_retry = can_retry_default and (attempt < MAX_RETRIES)
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

            try:
                with urllib.request.urlopen(req, timeout=req_timeout) as resp:
                    resp_status = resp.status
                    if resp_status == 204:
                        return None
                    raw_content = resp.read()
                    if not raw_content:
                        return None
                    return json.loads(raw_content.decode("utf-8"))

            except urllib.error.HTTPError as http_err:
                resp_status = http_err.code
                if can_retry and (502 <= resp_status <= 504):
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue

                raw_body = http_err.read().decode("utf-8", errors="replace")
                parsed_json = None
                try:
                    parsed_json = json.loads(raw_body)
                except Exception:
                    pass

                raise _error_from_response(resp_status, parsed_json, f"{method} {path} returned {resp_status}") from http_err

            except urllib.error.URLError as url_err:
                if can_retry:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err).lower():
                    raise InstaboxTimeoutError(
                        f"{method} {path} timed out after {req_timeout}s",
                        code="request_timeout",
                    ) from url_err
                raise InstaboxError(
                    f"{method} {path} network error: {url_err.reason}",
                    code="network_error",
                    retryable=True,
                ) from url_err

            except TimeoutError as t_err:
                if can_retry:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise InstaboxTimeoutError(
                    f"{method} {path} timed out after {req_timeout}s",
                    code="request_timeout",
                ) from t_err

    def wait_for_operation(self, op: Dict[str, Any], timeout_seconds: Optional[float] = None) -> Dict[str, Any]:
        timeout = timeout_seconds or self.operation_timeout
        deadline = time.time() + timeout
        delay = self.poll_interval
        cur = op

        while cur.get("state") != "succeeded":
            if cur.get("state") == "failed":
                err = cur.get("error", {})
                msg = err.get("message") or f"operation {cur.get('id')} ({cur.get('type')}) failed"
                raise InstaboxError(
                    msg,
                    code=err.get("code", "operation_failed"),
                    request_id=err.get("requestId"),
                    retryable=err.get("retryable", False),
                    operation_id=cur.get("id"),
                )

            if time.time() + delay > deadline:
                phase_info = f", phase {cur.get('phase')}" if cur.get("phase") else ""
                raise InstaboxTimeoutError(
                    f"operation {cur.get('id')} ({cur.get('type')}) did not finish within {timeout}s (state {cur.get('state')}{phase_info})",
                    code="operation_timeout",
                    operation_id=cur.get("id"),
                )

            time.sleep(delay)
            delay = min(delay * 1.5, max(1.0, self.poll_interval))
            cur = self.request("GET", f"/v1/operations/{urllib.parse.quote(cur['id'])}")

        return cur
