"""
InstaBox Python SDK: Firecracker microVM sandboxes for agents and dev workloads.
"""
from __future__ import annotations

from .commands import Commands
from .desktop import Desktop
from .errors import (
    CommandExitError,
    InstaboxAuthError,
    InstaboxError,
    InstaboxQuotaError,
    InstaboxTimeoutError,
)
from .files import Files
from .http import DEFAULT_API_URL, HttpClient
from .models import (
    BackgroundProcess,
    CommandResult,
    FileEntry,
    MetricSample,
    SandboxInfo,
    SSHCredentials,
    StreamUrlResult,
    UsageReport,
)
from .sandbox import DEFAULT_TEMPLATE, FALLBACK_TEMPLATE, Sandbox

__version__ = "0.1.0"

__all__ = [
    "Sandbox",
    "Commands",
    "Files",
    "Desktop",
    "HttpClient",
    "InstaboxError",
    "InstaboxAuthError",
    "InstaboxQuotaError",
    "InstaboxTimeoutError",
    "CommandExitError",
    "CommandResult",
    "BackgroundProcess",
    "FileEntry",
    "SandboxInfo",
    "MetricSample",
    "UsageReport",
    "SSHCredentials",
    "StreamUrlResult",
    "DEFAULT_API_URL",
    "DEFAULT_TEMPLATE",
    "FALLBACK_TEMPLATE",
]
