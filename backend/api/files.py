from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request

from backend.errors import InputError, NotFoundError

router = APIRouter(prefix="/api/v1")


@router.get("/audit/{audit_id}/file")
async def get_file(
    audit_id: str,
    http_request: Request,
    path: str,
    start: Optional[int] = None,
    end: Optional[int] = None,
) -> dict:
    state = http_request.app.state
    record = await state.store.get(audit_id)
    if record is None:
        raise NotFoundError(f"audit {audit_id!r} not found")

    if record.repo_path is None:
        raise NotFoundError(
            f"audit {audit_id!r} has no repo checkout yet"
        )

    repo_root = Path(record.repo_path).resolve()

    # Early-reject obvious traversal patterns
    if path.startswith("/") or ".." in Path(path).parts:
        raise InputError(
            f"path traversal attempt: {path!r}",
            details={"path": path},
        )

    target = (repo_root / path).resolve()
    try:
        target.relative_to(repo_root)
    except ValueError as e:
        raise InputError(
            f"path escapes repo root: {path!r}",
            details={"path": path},
        ) from e

    if not target.exists() or not target.is_file():
        raise NotFoundError(f"file not found: {path!r}")

    content = target.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    if start is not None or end is not None:
        s = max(1, start or 1) - 1
        e = min(total_lines, end or total_lines)
        selected = "".join(lines[s:e])
        effective_start = s + 1
        effective_end = e
    else:
        selected = content
        effective_start = 1
        effective_end = total_lines

    return {
        "audit_id": audit_id,
        "path": path,
        "start": effective_start,
        "end": effective_end,
        "total_lines": total_lines,
        "content": selected,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
