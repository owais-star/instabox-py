"""
Desktop GUI and visual automation interface for InstaBox sandboxes.
"""
from __future__ import annotations
import datetime
import random
import re
import shlex
import string
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple, Union

from .commands import Commands
from .errors import CommandExitError, InstaboxError, InstaboxTimeoutError
from .files import Files
from .http import HttpClient
from .models import StreamUrlResult

DESKTOP_DISPLAY = ":1"
BUTTONS = {"left": 1, "middle": 2, "right": 3}
WHEEL = {"up": 4, "down": 5, "left": 6, "right": 7}
KEYS = {
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "space": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "meta": "super",
    "cmd": "super",
    "command": "super",
    "super": "super",
    "win": "super",
    "+": "plus",
}


def _keysym(key: str) -> str:
    if not isinstance(key, str) or not key or any(c.isspace() for c in key):
        raise InstaboxError(f"invalid key: {key!r}", code="bad_request")
    lower = key.lower()
    if lower in KEYS:
        return KEYS[lower]
    if re.match(r"^f([1-9]|1[0-9]|2[0-4])$", lower):
        return lower.upper()
    return key


class Desktop:
    """Controls Xfce desktop, Chromium, and mouse/keyboard automation in agent-browser sandboxes."""

    def __init__(self, http: HttpClient, sandbox_id: str, commands: Commands, files: Files) -> None:
        self.http = http
        self.sandbox_id = sandbox_id
        self.commands = commands
        self.files = files

    def start(self, width: int = 1280, height: int = 800) -> Dict[str, Any]:
        """Starts the virtual desktop with the specified resolution."""
        if not (800 <= width <= 2560):
            raise InstaboxError("width must be between 800 and 2560", code="bad_request")
        if not (600 <= height <= 1600):
            raise InstaboxError("height must be between 600 and 1600", code="bad_request")

        s = self._call({"action": "start", "width": width, "height": height})
        if not s.get("installed"):
            if not s.get("installing"):
                s = self._call({"action": "install"})
            deadline = time.time() + self.http.operation_timeout
            while not s.get("installed"):
                if s.get("failed"):
                    raise InstaboxError(
                        f"the desktop could not be installed: {s.get('log', 'see /tmp/instabox-desktop-install.log')}",
                        code="desktop_install_failed",
                    )
                if time.time() > deadline:
                    raise InstaboxTimeoutError(
                        f"the desktop was not installed within {self.http.operation_timeout}s",
                        code="operation_timeout",
                    )
                time.sleep(self.http.poll_interval * 8)
                s = self._call({"action": "status"})
            s = self._call({"action": "start", "width": width, "height": height})

        if not s.get("running"):
            raise InstaboxError("the desktop did not start", code="desktop_not_running")

        return self.status()

    def status(self) -> Dict[str, Any]:
        """Returns installation status, running state, and current screen resolution."""
        s = self._call({"action": "status"})
        out = {"installed": bool(s.get("installed")), "running": bool(s.get("running"))}
        if out["running"]:
            geo_res = self._xdo("getdisplaygeometry")
            dims = geo_res.stdout.strip().split()
            if len(dims) == 2 and dims[0].isdigit() and dims[1].isdigit():
                out["width"] = int(dims[0])
                out["height"] = int(dims[1])
        return out

    def screenshot(self) -> bytes:
        """Captures a PNG screenshot of the entire desktop."""
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        path = f"/tmp/instabox-screenshot-{rand}.png"
        p = shlex.quote(path)
        try:
            self._run(
                f"if command -v scrot >/dev/null; then scrot -o {p}; "
                f"elif command -v import >/dev/null; then import -window root png:{p}; "
                f"else echo 'no screenshot tool in sandbox' >&2; exit 127; fi"
            )
            return self.files.read(path, as_bytes=True)
        finally:
            self.commands.exec(f"rm -f {p}")

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        """Clicks at (x, y) coordinates."""
        btn_code = BUTTONS.get(button.lower())
        if not btn_code:
            raise InstaboxError(f"button must be left, right or middle; got {button}", code="bad_request")
        repeat_arg = " --repeat 2 --delay 80" if double else ""
        self._xdo(f"mousemove {x} {y} click{repeat_arg} {btn_code}")

    def move(self, x: int, y: int) -> None:
        """Moves cursor to (x, y) position."""
        self._xdo(f"mousemove {x} {y}")

    def drag(self, from_pt: Tuple[int, int], to_pt: Tuple[int, int]) -> None:
        """Drags from start point to destination point."""
        self._xdo(
            f"mousemove {from_pt[0]} {from_pt[1]} mousedown 1 sleep 0.1 "
            f"mousemove {to_pt[0]} {to_pt[1]} sleep 0.1 mouseup 1"
        )

    def scroll(self, direction: str = "down", amount: int = 3) -> None:
        """Scrolls the mouse wheel."""
        wheel_btn = WHEEL.get(direction.lower())
        if not wheel_btn:
            raise InstaboxError("direction must be up, down, left or right", code="bad_request")
        self._xdo(f"click --repeat {amount} --delay 30 {wheel_btn}")

    def type(self, text: str, delay_ms: int = 12) -> None:
        """Types text with optional keystroke delay into the focused window."""
        if not text:
            return
        self._xdo(f"type --delay {delay_ms} --file -", stdin=text)

    def press(self, keys: Union[str, List[str]]) -> None:
        """Presses a single key or chord combination (e.g. ['ctrl', 'l'])."""
        key_list = [keys] if isinstance(keys, str) else keys
        if not key_list:
            raise InstaboxError("press requires at least one key", code="bad_request")
        syms = "+".join(_keysym(k) for k in key_list)
        self._xdo(f"key -- {shlex.quote(syms)}")

    def open(self, url: str) -> None:
        """Opens URL in the sandbox's Chromium browser."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise InstaboxError(f"only http and https URLs allowed; got {parsed.scheme}", code="bad_request")
        quoted_url = shlex.quote(url)
        self._run(
            f'b=$(command -v chromium || command -v chromium-browser || command -v google-chrome) || '
            f'{{ echo "no browser in the sandbox" >&2; exit 127; }}; '
            f'setsid nohup "$b" --no-first-run --no-default-browser-check --password-store=basic {quoted_url} >/dev/null 2>&1 </dev/null &'
        )

    def cursor_position(self) -> Tuple[int, int]:
        """Gets current (x, y) coordinates of the cursor."""
        res = self._xdo("getmouselocation --shell")
        x_match = re.search(r"X=(\d+)", res.stdout)
        y_match = re.search(r"Y=(\d+)", res.stdout)
        if not x_match or not y_match:
            raise InstaboxError("could not read cursor position", code="invalid_response")
        return int(x_match.group(1)), int(y_match.group(1))

    def stream_url(self, view_only: bool = True, ttl_seconds: int = 3600) -> StreamUrlResult:
        """Generates a public web viewer URL to view or interact with the desktop."""
        if not (60 <= ttl_seconds <= 86400):
            raise InstaboxError("ttl_seconds must be between 60 and 86400", code="bad_request")
        res = self.http.request(
            "POST",
            f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/desktop/stream",
            body={"viewOnly": view_only, "ttlSeconds": ttl_seconds},
        )
        return StreamUrlResult(
            url=res["url"],
            expires_at=datetime.datetime.fromisoformat(res["expiresAt"].replace("Z", "+00:00")),
        )

    def revoke_stream_urls(self) -> None:
        """Revokes all active viewer URLs for this sandbox."""
        self.http.request("DELETE", f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/desktop/stream")

    def _call(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return self.http.request(
            "POST",
            f"/v1/machines/{urllib.parse.quote(self.sandbox_id)}/desktop",
            body=body,
            timeout=90.0,
        )

    def _xdo(self, args: str, stdin: Optional[str] = None) -> Any:
        return self._run(f"xdotool {args}", stdin=stdin)

    def _run(self, cmd: str, stdin: Optional[str] = None) -> Any:
        r = self.commands.exec(f"export DISPLAY={DESKTOP_DISPLAY}; {cmd}", stdin=stdin)
        if r.exit_code != 0:
            raise CommandExitError(r.exit_code, stdout=r.stdout, stderr=r.stderr)
        return r
