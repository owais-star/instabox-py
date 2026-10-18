"""
InstaBox SDK Data Models.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


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
