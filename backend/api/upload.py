from __future__ import annotations

import secrets

from fastapi import APIRouter, File, Request, UploadFile

from backend.errors import DataTooLargeError, InputError

router = APIRouter(prefix="/api/v1")

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/audit/upload-pdf", status_code=201)
async def upload_pdf(
    http_request: Request, file: UploadFile = File(...)
) -> dict:
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise InputError(
            f"expected application/pdf, got {file.content_type!r}",
            details={"content_type": file.content_type},
        )

    contents = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise DataTooLargeError(
            f"upload exceeds {_MAX_UPLOAD_BYTES} bytes",
            details={"max_bytes": _MAX_UPLOAD_BYTES},
        )
    if not contents.startswith(b"%PDF-"):
        raise InputError(
            "uploaded file does not start with the %PDF- magic bytes"
        )

    state = http_request.app.state
    uploads_dir = state.settings.data_root_path() / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    upload_id = f"pdf_{secrets.token_hex(8)}"
    (uploads_dir / f"{upload_id}.pdf").write_bytes(contents)

    return {"upload_id": upload_id, "size_bytes": len(contents)}
