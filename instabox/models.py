"""
InstaBox SDK Data Models.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class SandboxState(str, Enum):
    """Explicit lifecycle states for an InstaBox Firecracker microVM."""
    PROVISIONING = "provisioning"
    RUNNING = "running"
    SUSPENDED = "suspended"
    STOPPED = "stopped"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ERROR = "error"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, val: Optional[str]) -> SandboxState:
        if not val:
            return cls.UNKNOWN
        try:
            return cls(str(val).lower())
        except ValueError:
            return cls.UNKNOWN


@dataclass
class CommandResult:
    """Result of a command execution."""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    truncated: bool = False
    error: Optional[str] = None


@dataclass
class BackgroundProcess:
    """Handle to a background command process."""
    pid: int
    kill: Callable[[], bool]


@dataclass
class FileEntry:
    """Directory listing entry."""
    name: str
    path: str
    type: str  # "file" | "dir"


@dataclass
class SandboxInfo:
    """Status and specification metadata of a Sandbox."""
    sandbox_id: str
    name: str
    state: str
    template_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)
    vault: bool = True
    started_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    archive_at: Optional[datetime] = None
    on_timeout: str = "pause"
    auto_suspend_ms: Optional[int] = None
    machine: Dict[str, Any] = field(default_factory=dict)

    @property
    def sandbox_state(self) -> SandboxState:
        """Returns typed SandboxState enum."""
        return SandboxState.from_str(self.state)

    @property
    def is_running(self) -> bool:
        """True if the sandbox is actively running and ready to accept commands."""
        return self.sandbox_state == SandboxState.RUNNING

    @property
    def is_terminal(self) -> bool:
        """True if the sandbox has reached a non-recoverable terminal state."""
        return self.sandbox_state in (SandboxState.TERMINATING, SandboxState.TERMINATED, SandboxState.ERROR)

    @property
    def valid_actions(self) -> List[str]:
        """Returns legal next actions for this state (AX / Agent Experience optimization)."""
        mapping = {
            SandboxState.PROVISIONING: ["settle", "kill"],
            SandboxState.RUNNING: ["pause", "stop", "kill", "exec"],
            SandboxState.SUSPENDED: ["resume", "wake", "stop", "kill"],
            SandboxState.STOPPED: ["wake", "resume", "kill"],
            SandboxState.TERMINATING: ["settle"],
            SandboxState.TERMINATED: [],
            SandboxState.ERROR: ["kill"],
            SandboxState.UNKNOWN: ["settle", "kill"],
        }
        return mapping.get(self.sandbox_state, [])


@dataclass
class MetricSample:
    """Single telemetry sample for CPU/RAM utilization."""
    timestamp: datetime
    cpu_used_pct: float
    cpu_count: int
    mem_used: int
    mem_total: int
    disk_total: int


@dataclass
class UsageReport:
    """Cumulative compute and storage usage."""
    from_time: datetime
    to_time: datetime
    running_seconds: float
    vcpu_seconds: float
    mem_gib_seconds: float
    disk_gib_seconds: float


@dataclass
class SSHCredentials:
    """Short-lived SSH connection credentials."""
    host: str
    port: int
    username: str
    certificate: str
    known_hosts_line: str
    expires_at: datetime
    connection_id: str


@dataclass
class StreamUrlResult:
    """Public viewer link for virtual desktop."""
    url: str
    expires_at: datetime
