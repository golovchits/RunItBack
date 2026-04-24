from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.errors import ConflictError, NotFoundError, UnavailableError
from backend.schemas.inputs import AuditRecord, AuditRequest
from backend.schemas.report import DiagnosticReport
from backend.util.time import utcnow_iso

router = APIRouter(prefix="/api/v1")
_log = logging.getLogger("runitback.api.audits")


@router.post("/audit", status_code=202)
async def create_audit(
    request: AuditRequest, http_request: Request
) -> JSONResponse:
    state = http_request.app.state
    if state.runner is None:
        raise UnavailableError(
            "Anthropic client not configured (ANTHROPIC_API_KEY missing or invalid)"
        )

    audit_id = str(uuid.uuid4())
    record = AuditRecord(
        id=audit_id,
        request=request,
        created_at=utcnow_iso(),
        phase="created",
        runtime_mode="messages_api" if request.force_fallback else "managed_agents",
    )
    await state.store.upsert(record)

    pipeline = state.pipeline_factory(
        record,
        state.store,
        state.bus,
        state.runner,
        state.normalizer,
        state.settings,
    )
    task = asyncio.create_task(
        _run_and_cleanup(pipeline, audit_id, state.running_tasks),
        name=f"audit-{audit_id}",
    )
    state.running_tasks[audit_id] = task

    return JSONResponse(
        status_code=202,
        content={
            "audit_id": audit_id,
            "status_url": f"/api/v1/audit/{audit_id}/status",
            "stream_url": f"/api/v1/audit/{audit_id}/stream",
            "report_url": f"/api/v1/audit/{audit_id}/report",
            "runtime_mode": record.runtime_mode,
            "phase": record.phase,
        },
    )


async def _run_and_cleanup(pipeline, audit_id: str, running_tasks: dict) -> None:
    try:
        await pipeline.run()
    except asyncio.CancelledError:
        _log.info("audit %s cancelled", audit_id)
    except Exception as e:
        _log.warning("audit %s failed: %s: %s", audit_id, type(e).__name__, e)
    finally:
        running_tasks.pop(audit_id, None)


@router.post("/audit/{audit_id}/resume", status_code=202)
async def resume_audit(
    audit_id: str, http_request: Request
) -> JSONResponse:
    """Re-invoke the pipeline for an existing audit id.

    The pipeline's phases each check the store for their artifact and
    skip if present, so resume picks up from the phase that failed.
    """
    state = http_request.app.state
    record = await state.store.get(audit_id)
    if record is None:
        raise NotFoundError(f"audit {audit_id!r} not found")
    if state.runner is None:
        raise UnavailableError(
            "Anthropic client not configured "
            "(ANTHROPIC_API_KEY missing or invalid)"
        )
    if audit_id in state.running_tasks:
        raise ConflictError(
            f"audit {audit_id!r} is already running",
            details={"phase": record.phase},
        )

    # Clear any previous terminal error so the pipeline doesn't trip
    # on a stale failure; phase will be set by the first phase it runs.
    record.error = None
    await state.store.upsert(record)

    pipeline = state.pipeline_factory(
        record,
        state.store,
        state.bus,
        state.runner,
        state.normalizer,
        state.settings,
    )
    task = asyncio.create_task(
        _run_and_cleanup(pipeline, audit_id, state.running_tasks),
        name=f"audit-{audit_id}-resume",
    )
    state.running_tasks[audit_id] = task

    return JSONResponse(
        status_code=202,
        content={
            "audit_id": audit_id,
            "status_url": f"/api/v1/audit/{audit_id}/status",
            "stream_url": f"/api/v1/audit/{audit_id}/stream",
            "report_url": f"/api/v1/audit/{audit_id}/report",
            "runtime_mode": record.runtime_mode,
            "phase": record.phase,
            "resumed": True,
        },
    )


@router.get("/audit/{audit_id}/status")
async def get_status(audit_id: str, http_request: Request) -> dict:
    state = http_request.app.state
    record = await state.store.get(audit_id)
    if record is None:
        raise NotFoundError(f"audit {audit_id!r} not found")

    findings_so_far = 0
    async for ev in state.store.read_events(audit_id):
        if ev.get("type") == "agent.finding_emitted":
            findings_so_far += 1

    report_ready = (
        await state.store.load_artifact(audit_id, "report", DiagnosticReport)
        is not None
    )

    return {
        "audit_id": audit_id,
        "phase": record.phase,
        "runtime_mode": record.runtime_mode,
        "created_at": record.created_at,
        "updated_at": utcnow_iso(),
        "findings_so_far": findings_so_far,
        "error": record.error,
        "report_ready": report_ready,
    }


@router.get("/audit/{audit_id}/report")
async def get_report(audit_id: str, http_request: Request) -> dict:
    state = http_request.app.state
    record = await state.store.get(audit_id)
    if record is None:
        raise NotFoundError(f"audit {audit_id!r} not found")

    if record.phase not in ("done", "failed"):
        raise ConflictError(
            f"audit {audit_id!r} is not yet complete (phase={record.phase})",
            details={"phase": record.phase},
        )

    report = await state.store.load_artifact(
        audit_id, "report", DiagnosticReport
    )
    if report is None:
        raise NotFoundError(f"no report artifact for audit {audit_id!r}")
    return report.model_dump(mode="json")


@router.delete("/audit/{audit_id}", status_code=204)
async def cancel_audit(audit_id: str, http_request: Request) -> None:
    state = http_request.app.state
    record = await state.store.get(audit_id)
    if record is None:
        raise NotFoundError(f"audit {audit_id!r} not found")

    task = state.running_tasks.pop(audit_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    if record.phase not in ("done", "failed"):
        record.phase = "failed"
        record.error = "cancelled by user"
        await state.store.upsert(record)
    return None
