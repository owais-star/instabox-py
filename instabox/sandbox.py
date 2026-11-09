"""
Core Sandbox interface for InstaBox microVMs.
"""
from __future__ import annotations
import datetime
import random
import re
import string
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Union

from .commands import Commands
from .desktop import Desktop
from .errors import InstaboxError, InstaboxTimeoutError, InvalidStateTransitionError
from .files import Files
from .http import HttpClient
from .models import (
    MetricSample,
    SandboxInfo,
    SandboxState,
    SSHCredentials,
    UsageReport,
)

DEFAULT_TEMPLATE = "agent-browser"
FALLBACK_TEMPLATE = "universal"
METADATA_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _to_info(m: Dict[str, Any]) -> SandboxInfo:
    started_at = None
    if m.get("createdAt"):
        started_at = datetime.datetime.fromisoformat(m["createdAt"].replace("Z", "+00:00"))

    end_at = None
    if m.get("timeoutAt"):
        end_at = datetime.datetime.fromisoformat(m["timeoutAt"].replace("Z", "+00:00"))

    archive_at = None
    if m.get("archiveAt"):
        archive_at = datetime.datetime.fromisoformat(m["archiveAt"].replace("Z", "+00:00"))

    auto_suspend_ms = None
    if m.get("autoSuspendAfterSeconds") is not None:
        auto_suspend_ms = m["autoSuspendAfterSeconds"] * 1000

    template_id = m.get("template", {}).get("id") if isinstance(m.get("template"), dict) else None
    snapshot_id = m.get("snapshot", {}).get("id") if isinstance(m.get("snapshot"), dict) else None

    return SandboxInfo(
        sandbox_id=m["id"],
        name=m.get("name", ""),
        state=m.get("state", "unknown"),
        template_id=template_id,
        snapshot_id=snapshot_id,
        metadata=dict(m.get("metadata", {})),
        vault=bool(m.get("vault", True)),
        started_at=started_at,
        end_at=end_at,
        archive_at=archive_at,
        on_timeout=m.get("onTimeout", "pause"),
        auto_suspend_ms=auto_suspend_ms,
        machine=m,
    )


class Sandbox:
    """Represents an active or managed InstaBox Firecracker microVM."""

    def __init__(
        self,
        http: HttpClient,
        machine: Dict[str, Any],
        envs: Optional[Dict[str, str]] = None,
        on_exit: str = "kill",
    ) -> None:
        self.http = http
        self.sandbox_id = machine["id"]
        self.machine = machine
        self.on_exit = on_exit
        self.commands = Commands(http, self.sandbox_id, default_envs=envs)
        self.files = Files(self.commands)
        self.desktop = Desktop(http, self.sandbox_id, self.commands, self.files)

    def __enter__(self) -> Sandbox:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.on_exit == "kill":
            self.kill()
        elif self.on_exit == "pause":
            self.pause()

    @classmethod
    def create(
        cls,
        template_or_snapshot: Optional[str] = None,
        name: Optional[str] = None,
        envs: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, str]] = None,
        vault: bool = True,
        timeout_seconds: Optional[int] = None,
        archive_seconds: Optional[int] = None,
        auto_suspend_seconds: Optional[int] = None,
        on_timeout: str = "pause",
        on_exit: str = "kill",
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> Sandbox:
        """Provisions a new Sandbox and waits until it is fully ready."""
        http = HttpClient(api_key=api_key, api_url=api_url)
        box_name = name or f"sbx-{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"

        body: Dict[str, Any] = {"name": box_name}
        if timeout_seconds is not None:
            body["timeoutSeconds"] = timeout_seconds
        if archive_seconds is not None:
            body["archiveSeconds"] = archive_seconds
        if auto_suspend_seconds is not None:
            body["autoSuspendAfterSeconds"] = auto_suspend_seconds
        if on_timeout:
            body["onTimeout"] = on_timeout
        if metadata:
            body["metadata"] = metadata
        if not vault:
            body["vault"] = False

        target_ref = template_or_snapshot or cls._default_template(http)
        body.update(cls._resolve_source(http, target_ref))

        op = http.request("POST", "/v1/machines", body=body)
        done = http.wait_for_operation(op)
        machine_id = done.get("machineId") or op.get("machineId") or done.get("id")
        machine = http.request("GET", f"/v1/machines/{urllib.parse.quote(machine_id)}")
        return cls(http, machine, envs=envs, on_exit=on_exit)

    @classmethod
    def connect(
        cls,
        sandbox_id: str,
        resume: bool = True,
        envs: Optional[Dict[str, str]] = None,
        on_exit: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> Sandbox:
        """Attaches to an existing sandbox, optionally resuming it if paused or stopped."""
        http = HttpClient(api_key=api_key, api_url=api_url)
        machine = http.request("GET", f"/v1/machines/{urllib.parse.quote(sandbox_id)}")
        sbx = cls(http, machine, envs=envs, on_exit=on_exit or "none")
        sbx.settle(refresh=False)
        if resume:
            sbx.wake()
        return sbx

    @classmethod
    def list(
        cls,
        metadata: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> List[SandboxInfo]:
        """Lists all sandboxes belonging to the authenticated account."""
        http = HttpClient(api_key=api_key, api_url=api_url)
        meta_query: List[str] = []
        if metadata:
            for k, v in metadata.items():
                if not METADATA_KEY_RE.match(k):
                    raise InstaboxError(f"invalid metadata key: {k!r}", code="bad_request")
                meta_query.append(f"{k}:{v}")

        results: List[SandboxInfo] = []
        cursor: Optional[str] = None
        while True:
            query: Dict[str, Any] = {"limit": 100}
            if cursor:
                query["cursor"] = cursor
            if meta_query:
                query["metadata"] = meta_query

            page = http.request("GET", "/v1/machines", query=query)
            for m in page.get("machines", []):
                results.append(_to_info(m))
            cursor = page.get("nextCursor")
            if not cursor:
                break
        return results

    @classmethod
    def kill(
        cls,
        sandbox_id: str,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> bool:
        """Terminates and permanently deletes a sandbox by ID."""
        http = HttpClient(api_key=api_key, api_url=api_url)
        try:
            op = http.request("DELETE", f"/v1/machines/{urllib.parse.quote(sandbox_id)}")
            http.wait_for_operation(op)
            return True
        except InstaboxError as e:
            if e.status == 404 or e.code == "not_found":
                return False
            raise

    @classmethod
    def list_snapshots(cls, api_key: Optional[str] = None, api_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists private snapshots."""
        http = HttpClient(api_key=api_key, api_url=api_url)
        res = http.request("GET", "/v1/snapshots")
        return res.get("snapshots", [])

    @classmethod
    def get_snapshot(cls, snapshot_id: str, api_key: Optional[str] = None, api_url: Optional[str] = None) -> Dict[str, Any]:
        """Retrieves snapshot metadata by ID."""
        http = HttpClient(api_key=api_key, api_url=api_url)
        return http.request("GET", f"/v1/snapshots/{urllib.parse.quote(snapshot_id)}")

    @classmethod
    def delete_snapshot(cls, snapshot_id: str, api_key: Optional[str] = None, api_url: Optional[str] = None) -> bool:
        """Deletes a snapshot."""
        http = HttpClient(api_key=api_key, api_url=api_url)
        try:
            http.request("DELETE", f"/v1/snapshots/{urllib.parse.quote(snapshot_id)}")
            return True
        except InstaboxError as e:
            if e.status == 404 or e.code == "not_found":
                return False
            raise

    @classmethod
    def usage(cls, api_key: Optional[str] = None, api_url: Optional[str] = None) -> Dict[str, Any]:
        """Returns account resource counts and limits."""
        http = HttpClient(api_key=api_key, api_url=api_url)
        return http.request("GET", "/v1/usage")

    def get_info(self) -> SandboxInfo:
        """Fetches fresh status and specification."""
        self.machine = self.http.request("GET", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}")
        return _to_info(self.machine)

    def is_running(self) -> bool:
        """Checks if the sandbox is actively running."""
        return self.get_info().is_running

    def pause(self) -> None:
        """Suspends the sandbox, preserving RAM memory and active processes."""
        self.settle()
        state = SandboxState.from_str(self.machine.get("state"))
        if state == SandboxState.SUSPENDED:
            return  # Idempotent no-op
        if state in (SandboxState.TERMINATING, SandboxState.TERMINATED):
            raise InvalidStateTransitionError(state.value, "pause", [])
        if state == SandboxState.STOPPED:
            raise InvalidStateTransitionError(state.value, "pause", ["wake", "kill"])
        self._mutate("POST", "suspend")

    def resume(self) -> None:
        """Restores a suspended sandbox or starts a stopped one."""
        self.settle()
        self.wake()

    def wake(self) -> None:
        """Wakes machine based on current state with state machine guard."""
        self.settle(refresh=False)
        state = SandboxState.from_str(self.machine.get("state"))
        if state == SandboxState.RUNNING:
            return  # Idempotent no-op
        if state == SandboxState.PROVISIONING:
            self.settle(refresh=True)
            return
        if state == SandboxState.SUSPENDED:
            self._mutate("POST", "resume")
        elif state == SandboxState.STOPPED:
            self._mutate("POST", "start")
        elif state in (SandboxState.TERMINATING, SandboxState.TERMINATED):
            raise InvalidStateTransitionError(state.value, "wake", [])
        else:
            self.settle(refresh=True)
            refreshed = SandboxState.from_str(self.machine.get("state"))
            if refreshed == SandboxState.SUSPENDED:
                self._mutate("POST", "resume")
            elif refreshed == SandboxState.STOPPED:
                self._mutate("POST", "start")

    def stop(self) -> None:
        """Shuts down the guest OS cleanly while keeping persistent /data disk."""
        self.settle()
        state = SandboxState.from_str(self.machine.get("state"))
        if state == SandboxState.STOPPED:
            return  # Idempotent no-op
        if state in (SandboxState.TERMINATING, SandboxState.TERMINATED):
            raise InvalidStateTransitionError(state.value, "stop", [])
        if state == SandboxState.SUSPENDED:
            self._mutate("POST", "start")
        self._mutate("POST", "stop")

    def set_timeout(self, timeout_seconds: int, on_timeout: Optional[str] = None) -> None:
        """Sets hard deadline from now in seconds (0 clears timeout)."""
        body: Dict[str, Any] = {"timeoutSeconds": timeout_seconds}
        if on_timeout:
            body["onTimeout"] = on_timeout
        self.machine = self.http.request("PATCH", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}", body=body)

    def set_auto_suspend(self, idle_seconds: int) -> None:
        """Sets automatic idle pause threshold in seconds (0 disables auto-suspend)."""
        self.machine = self.http.request(
            "PATCH",
            f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}",
            body={"autoSuspendAfterSeconds": idle_seconds},
        )

    def set_metadata(self, metadata: Dict[str, str]) -> None:
        """Updates sandbox metadata labels."""
        self.machine = self.http.request(
            "PATCH",
            f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}",
            body={"metadata": metadata},
        )

    def vault(self) -> Dict[str, Any]:
        """Inspects secrets injected by Vault."""
        return self.http.request("GET", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/vault")

    def push_vault(self) -> Dict[str, Any]:
        """Pushes current Vault secrets into the running guest immediately."""
        return self.http.request("POST", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/vault")

    def disable_vault(self) -> None:
        """Permanently disables Vault injection for this sandbox."""
        self.machine = self.http.request(
            "PATCH",
            f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}",
            body={"vault": False},
        )

    def create_snapshot(self, name: str, description: Optional[str] = None, root_only: bool = False) -> Dict[str, Any]:
        """Captures disk state into a reusable snapshot."""
        self.settle()
        body: Dict[str, Any] = {"name": name, "rootOnly": root_only}
        if description:
            body["description"] = description
        return self.http.request("POST", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/snapshots", body=body)

    def ssh_credentials(self, public_key: str, ttl_seconds: int = 3600) -> SSHCredentials:
        """Mints an ephemeral SSH certificate for direct terminal access."""
        if not (1 <= ttl_seconds <= 86400):
            raise InstaboxError("ttl_seconds must be between 1 and 86400", code="bad_request")
        res = self.http.request(
            "POST",
            f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/connections",
            body={"publicKey": public_key.strip(), "ttlSeconds": ttl_seconds},
        )
        host = res["host"]
        port = res["port"]
        trust_key = res.get("hostTrust", {}).get("publicKey", "")
        return SSHCredentials(
            host=host,
            port=port,
            username=res["username"],
            certificate=res["certificate"],
            known_hosts_line=f"@cert-authority [{host}]:{port} {trust_key}",
            expires_at=datetime.datetime.fromisoformat(res["expiresAt"].replace("Z", "+00:00")),
            connection_id=res["id"],
        )

    def settle(self, refresh: bool = True) -> None:
        """Waits for any running operation on this sandbox to finish."""
        if refresh:
            self.machine = self.http.request("GET", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}")
        op_id = self.machine.get("operationId")
        if op_id:
            try:
                op = self.http.request("GET", f"/v1/operations/{urllib.parse.quote(op_id)}")
                self.http.wait_for_operation(op)
            except Exception:
                pass
            self.machine = self.http.request("GET", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}")

    def _mutate(self, method: str, action: str) -> None:
        op = self.http.request(method, f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/{action}")
        self.http.wait_for_operation(op)
        self.machine = self.http.request("GET", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}")

    @staticmethod
    def _default_template(http: HttpClient) -> str:
        res = http.request("GET", "/v1/templates")
        templates = res.get("templates", [])
        for t in templates:
            if t.get("id") == DEFAULT_TEMPLATE and not t.get("hidden"):
                return DEFAULT_TEMPLATE
        return FALLBACK_TEMPLATE

    @staticmethod
    def _resolve_source(http: HttpClient, ref: str) -> Dict[str, str]:
        if re.match(r"^sn_[a-z2-7]{26}$", ref):
            return {"snapshotId": ref}
        templates = http.request("GET", "/v1/templates").get("templates", [])
        if any(t.get("id") == ref for t in templates):
            return {"templateId": ref}
        snapshots = http.request("GET", "/v1/snapshots").get("snapshots", [])
        matches = [s for s in snapshots if s.get("name") == ref]
        if len(matches) > 1:
            raise InstaboxError(f"multiple snapshots named {ref}; use a snapshot ID", code="ambiguous_snapshot")
        if matches:
            return {"snapshotId": matches[0]["id"]}
        raise InstaboxError(f"template or snapshot not found: {ref}", status=404, code="not_found")
