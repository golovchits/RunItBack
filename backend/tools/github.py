from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Optional

from backend.errors import DataTooLargeError, InputError, UnavailableError

_FAILURE_PATTERNS_INPUT_ERROR = (
    "not found",
    "does not exist",
    "repository not found",
    "could not read",
    "invalid url",
    "authentication failed",
    "permission denied",
    "remote branch",
    "couldn't find remote ref",
)


async def clone_repo(
    url: str,
    dest: Path,
    *,
    ref: Optional[str] = None,
    depth: int = 1,
    timeout: float = 120.0,
    max_bytes: Optional[int] = None,
) -> Path:
    """Shallow-clone ``url`` into ``dest`` via the ``git`` binary.

    ``ref`` selects a branch/tag; None uses the repository's default
    branch. ``depth`` enables shallow clone (0 disables). ``max_bytes``
    rejects the clone post-checkout if its tree exceeds the limit.

    Raises:
      InputError: bad URL, auth failure, unknown ref.
      UnavailableError: timeout, network failure, ``git`` not installed.
      DataTooLargeError: clone size greater than ``max_bytes``.
    """
    if dest.exists() and dest.is_dir() and any(dest.iterdir()):
        raise InputError(f"clone destination {dest} is not empty")
    dest.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["git", "clone"]
    if depth > 0:
        cmd.extend(["--depth", str(depth)])
    if ref is not None:
        cmd.extend(["--branch", ref])
    cmd.extend([url, str(dest)])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except FileNotFoundError as e:
        raise UnavailableError("git is not installed on PATH") from e

    try:
        _, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError as e:
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass
        shutil.rmtree(dest, ignore_errors=True)
        raise UnavailableError(
            f"git clone timed out after {timeout}s",
            details={"url": url, "timeout": timeout},
        ) from e

    if proc.returncode != 0:
        msg = (stderr or b"").decode("utf-8", errors="replace").strip()
        shutil.rmtree(dest, ignore_errors=True)
        low = msg.lower()
        if any(s in low for s in _FAILURE_PATTERNS_INPUT_ERROR):
            raise InputError(
                f"git clone failed: {msg or 'no stderr'}",
                details={"url": url},
            )
        raise UnavailableError(
            f"git clone failed: {msg or 'no stderr'}",
            details={"url": url},
        )

    if max_bytes is not None:
        size = await asyncio.to_thread(_tree_size_bytes, dest)
        if size > max_bytes:
            shutil.rmtree(dest, ignore_errors=True)
            raise DataTooLargeError(
                f"cloned repo is {size} bytes (> {max_bytes})",
                details={"size_bytes": size, "max_bytes": max_bytes},
            )

    return dest


def _tree_size_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except OSError:
                continue
    return total
