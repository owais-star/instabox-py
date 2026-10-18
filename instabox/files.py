"""
File transfer and manipulation interface for InstaBox sandboxes.
"""
from __future__ import annotations
import base64
import random
import shlex
import string
from typing import Dict, List, Optional, Union

from .commands import Commands
from .errors import CommandExitError, InstaboxError
from .models import FileEntry

MAX_FILE_BYTES = 10 * 1024 * 1024
WRITE_CHUNK_B64 = 48 * 1024
READ_CHUNK_BYTES = 512 * 1024


def _arg(path: str) -> str:
    adjusted = f"./{path}" if path.startswith("-") else path
    return shlex.quote(adjusted)


class Files:
    """Read, write, list and manage files inside an active InstaBox sandbox."""

    def __init__(self, commands: Commands) -> None:
        self.commands = commands

    def read(
        self,
        path: str,
        max_bytes: int = MAX_FILE_BYTES,
        as_bytes: bool = False,
    ) -> Union[str, bytes]:
        """Reads a file from the sandbox up to max_bytes (default 10 MiB)."""
        p = _arg(path)
        check_script = (
            f'[ -f {p} ] || {{ echo "no such file: "{p} >&2; exit 3; }}; '
            f's=$(wc -c < {p}) || exit 1; '
            f'[ "$s" -le {max_bytes} ] || {{ echo "file too large: $s bytes" >&2; exit 4; }}; '
            f'printf \'%s\' "$s"'
        )
        r = self.commands.exec(check_script)
        if r.exit_code == 3:
            raise InstaboxError(f"file not found: {path}", status=404, code="not_found")
        if r.exit_code == 4:
            raise InstaboxError(f"{path} is larger than {max_bytes} bytes", code="file_too_large")
        if r.exit_code != 0:
            raise CommandExitError(r.exit_code, stdout=r.stdout, stderr=r.stderr)

        try:
            total_size = int(r.stdout.strip())
        except Exception as e:
            raise InstaboxError("invalid file size returned by exec", code="invalid_response") from e

        chunks: List[bytes] = []
        for offset in range(0, total_size, READ_CHUNK_BYTES):
            skip_blocks = offset // READ_CHUNK_BYTES
            dd_cmd = f"dd if={p} bs={READ_CHUNK_BYTES} skip={skip_blocks} count=1 2>/dev/null | base64 | tr -d '\\n'"
            chunk_res = self.commands.exec(dd_cmd)
            if chunk_res.exit_code != 0:
                raise CommandExitError(chunk_res.exit_code, stdout=chunk_res.stdout, stderr=chunk_res.stderr)
            chunk_data = base64.b64decode(chunk_res.stdout.strip())
            chunks.append(chunk_data)

        raw_data = b"".join(chunks)
        if len(raw_data) != total_size:
            raise InstaboxError(f"file size changed while reading: {path}", code="file_changed")

        if as_bytes:
            return raw_data
        return raw_data.decode("utf-8", errors="replace")

    def write(self, path: str, data: Union[str, bytes]) -> Dict[str, str]:
        """Writes data into a file atomically, creating parent directories if needed."""
        raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
        if len(raw_bytes) > MAX_FILE_BYTES:
            raise InstaboxError(f"data is larger than {MAX_FILE_BYTES} bytes", code="file_too_large")

        p = _arg(path)
        rand_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        tmp = _arg(f"{path}.instabox-{rand_suffix}.tmp")
        b64_str = base64.b64encode(raw_bytes).decode("ascii")

        chunks = []
        for i in range(0, len(b64_str), WRITE_CHUNK_B64):
            chunks.append(b64_str[i : i + WRITE_CHUNK_B64])
        if not chunks:
            chunks.append("")

        not_dir = f'if [ -d {p} ]; then echo "is a directory: "{p} >&2; exit 21; fi; '

        try:
            for i, chunk in enumerate(chunks):
                redirect = ">" if i == 0 else ">>"
                prefix = f'{not_dir}mkdir -p -- "$(dirname -- {p})" && ' if i == 0 else ""
                write_cmd = f"{prefix}printf '%s' '{chunk}' | base64 -d {redirect} {tmp}"
                res = self.commands.exec(write_cmd)
                if res.exit_code != 0:
                    if res.exit_code == 21:
                        raise InstaboxError(f"is a directory: {path}", code="is_a_directory")
                    raise CommandExitError(res.exit_code, stdout=res.stdout, stderr=res.stderr)

            mv_res = self.commands.exec(f"{not_dir}mv -f -- {tmp} {p}")
            if mv_res.exit_code != 0:
                if mv_res.exit_code == 21:
                    raise InstaboxError(f"is a directory: {path}", code="is_a_directory")
                raise CommandExitError(mv_res.exit_code, stdout=mv_res.stdout, stderr=mv_res.stderr)

        except Exception:
            self.commands.exec(f"rm -f -- {tmp}")
            raise

        return {"path": path}

    def list(self, path: str) -> List[FileEntry]:
        """Lists directory contents non-recursively."""
        p = _arg(path)
        script = (
            f'[ -d {p} ] || {{ echo "no such directory: "{p} >&2; exit 3; }}; '
            f'cd {p} && for f in .* *; do case "$f" in .|..) continue ;; esac; '
            f'[ -e "$f" ] || [ -L "$f" ] || continue; '
            f'if [ -d "$f" ]; then printf \'d\\t%s\\0\' "$f"; else printf \'f\\t%s\\0\' "$f"; fi; done'
        )
        res = self.commands.exec(script)
        if res.exit_code == 3:
            raise InstaboxError(f"directory not found: {path}", status=404, code="not_found")
        if res.exit_code != 0:
            raise CommandExitError(res.exit_code, stdout=res.stdout, stderr=res.stderr)

        base = path.rstrip("/")
        entries: List[FileEntry] = []
        for line in res.stdout.split("\0"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                kind, name = parts
                entries.append(
                    FileEntry(
                        name=name,
                        path=f"{base}/{name}",
                        type="dir" if kind == "d" else "file",
                    )
                )
        return entries

    def remove(self, path: str) -> None:
        """Removes a file or directory recursively."""
        res = self.commands.exec(f"rm -rf -- {_arg(path)}")
        if res.exit_code != 0:
            raise CommandExitError(res.exit_code, stdout=res.stdout, stderr=res.stderr)

    def exists(self, path: str) -> bool:
        """Checks if a path exists."""
        res = self.commands.exec(f"test -e {_arg(path)}")
        return res.exit_code == 0
