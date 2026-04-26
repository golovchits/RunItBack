from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.config import Settings
from backend.main import create_app, setup_app_state, teardown_app_state
from backend.schemas.claims import PaperClaims
from backend.schemas.events import (
    EvtAuditError,
    EvtAuditStatus,
    EvtClaimsExtracted,
    EvtReportFinal,
)
from backend.schemas.inputs import (
    AuditRecord,
    AuditRequest,
    CodeSourceGit,
    DataSourceSkip,
    PaperSourceArxiv,
)
from backend.schemas.report import DiagnosticReport, Verdict


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-ant-test",
        DATA_ROOT=tmp_path,
    )


def _minimal_record(audit_id: str = "aud1") -> AuditRecord:
    return AuditRecord(
        id=audit_id,
        request=AuditRequest(
            paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/pdf/2504.01848"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
        ),
        created_at="2026-04-22T14:00:00Z",
        phase="paper_analyst",
        runtime_mode="managed_agents",
    )


def _minimal_report(audit_id: str = "aud1") -> DiagnosticReport:
    return DiagnosticReport(
        audit_id=audit_id,
        generated_at="2026-04-22T14:30:00Z",
        verdict=Verdict.LIKELY_REPRODUCIBLE,
        confidence=0.9,
        headline="ok",
        executive_summary="",
        claim_verifications=[],
        findings=[],
        config_comparison=[],
        recommendations=[],
        runtime_mode_used="managed_agents",
        runtime_ms_total=1,
    )


def _minimal_claims() -> PaperClaims:
    return PaperClaims(
        paper_title="T",
        authors=["A"],
        abstract_summary="s",
        metrics=[],
        datasets=[],
        architectures=[],
        training_config=[],
        evaluation_protocol=[],
        extraction_confidence=0.8,
    )


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    settings = _settings(tmp_path)
    _app = create_app(settings)
    setup_app_state(_app, settings)
    try:
        yield _app
    finally:
        await teardown_app_state(_app)


def _parse_events(body: str) -> list[str]:
    """Return ordered list of SSE 'event:' types from a response body."""
    return [
        line[len("event: "):]
        for line in body.splitlines()
        if line.startswith("event: ")
    ]


async def _wait_for_subscriber(app: FastAPI, audit_id: str) -> None:
    """Poll until the SSE handler has subscribed to the bus."""
    for _ in range(500):  # up to ~5s
        if app.state.bus.subscriber_count(audit_id) >= 1:
            return
        await asyncio.sleep(0.01)
    raise RuntimeError("SSE handler never subscribed")


# ---- basic contract ----


async def test_stream_nonexistent_audit_404(app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=5.0
    ) as c:
        resp = await c.get("/api/v1/audit/no-such-audit/stream")
    assert resp.status_code == 404


async def test_stream_content_type_and_headers(app: FastAPI):
    await app.state.store.upsert(_minimal_record("aud_headers"))
    await app.state.store.append_event(
        "aud_headers",
        EvtReportFinal(
            audit_id="aud_headers",
            seq=1,
            ts="t",
            report=_minimal_report("aud_headers"),
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=5.0
    ) as c:
        resp = await c.get("/api/v1/audit/aud_headers/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"


# ---- replay ----


async def test_stream_replays_stored_events_and_terminates(app: FastAPI):
    audit_id = "aud_replay"
    await app.state.store.upsert(_minimal_record(audit_id))
    await app.state.store.append_event(
        audit_id,
        EvtAuditStatus(audit_id=audit_id, seq=1, ts="t1", phase="normalizing"),
    )
    await app.state.store.append_event(
        audit_id,
        EvtClaimsExtracted(
            audit_id=audit_id, seq=2, ts="t2", claims=_minimal_claims()
        ),
    )
    await app.state.store.append_event(
        audit_id,
        EvtReportFinal(
            audit_id=audit_id, seq=3, ts="t3", report=_minimal_report(audit_id)
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=5.0
    ) as c:
        resp = await c.get(f"/api/v1/audit/{audit_id}/stream")

    assert resp.status_code == 200
    assert _parse_events(resp.text) == [
        "audit.status", "claims.extracted", "report.final",
    ]


async def test_stream_last_event_id_header_skips_earlier_events(app: FastAPI):
    audit_id = "aud_resume"
    await app.state.store.upsert(_minimal_record(audit_id))
    for seq in range(1, 4):
        await app.state.store.append_event(
            audit_id,
            EvtAuditStatus(
                audit_id=audit_id, seq=seq, ts=f"t{seq}", phase="normalizing"
            ),
        )
    await app.state.store.append_event(
        audit_id,
        EvtReportFinal(
            audit_id=audit_id, seq=4, ts="t4", report=_minimal_report(audit_id)
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=5.0
    ) as c:
        resp = await c.get(
            f"/api/v1/audit/{audit_id}/stream",
            headers={"Last-Event-ID": "2"},
        )

    assert resp.status_code == 200
    assert _parse_events(resp.text) == ["audit.status", "report.final"]


async def test_stream_terminates_on_nonrecoverable_error(app: FastAPI):
    audit_id = "aud_err"
    await app.state.store.upsert(_minimal_record(audit_id))
    await app.state.store.append_event(
        audit_id,
        EvtAuditStatus(
            audit_id=audit_id, seq=1, ts="t1", phase="paper_analyst"
        ),
    )
    await app.state.store.append_event(
        audit_id,
        EvtAuditError(
            audit_id=audit_id,
            seq=2,
            ts="t2",
            error_type="api_error",
            message="boom",
            recoverable=False,
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=5.0
    ) as c:
        resp = await c.get(f"/api/v1/audit/{audit_id}/stream")

    assert _parse_events(resp.text) == ["audit.status", "audit.error"]


async def test_stream_continues_past_recoverable_error_in_replay(app: FastAPI):
    """Recoverable error should NOT terminate — the subscribe step still runs."""
    audit_id = "aud_recoverable"
    await app.state.store.upsert(_minimal_record(audit_id))
    await app.state.store.append_event(
        audit_id,
        EvtAuditError(
            audit_id=audit_id,
            seq=1,
            ts="t1",
            error_type="timeout",
            message="soft",
            recoverable=True,
        ),
    )

    async def publish_terminal_when_subscribed():
        await _wait_for_subscriber(app, audit_id)
        await app.state.bus.publish(
            audit_id,
            EvtReportFinal(
                audit_id=audit_id,
                seq=2,
                ts="t2",
                report=_minimal_report(audit_id),
            ),
        )

    publisher = asyncio.create_task(publish_terminal_when_subscribed())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            timeout=5.0,
        ) as c:
            resp = await c.get(f"/api/v1/audit/{audit_id}/stream")
    finally:
        await publisher

    events = _parse_events(resp.text)
    assert "audit.error" in events
    assert "report.final" in events


# ---- live ----


async def test_stream_receives_live_published_events(app: FastAPI):
    audit_id = "aud_live"
    await app.state.store.upsert(_minimal_record(audit_id))

    async def publish_sequence():
        await _wait_for_subscriber(app, audit_id)
        await app.state.bus.publish(
            audit_id,
            EvtAuditStatus(
                audit_id=audit_id, seq=1, ts="t1", phase="paper_analyst"
            ),
        )
        await asyncio.sleep(0.01)
        await app.state.bus.publish(
            audit_id,
            EvtReportFinal(
                audit_id=audit_id,
                seq=2,
                ts="t2",
                report=_minimal_report(audit_id),
            ),
        )

    publisher = asyncio.create_task(publish_sequence())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            timeout=5.0,
        ) as c:
            resp = await c.get(f"/api/v1/audit/{audit_id}/stream")
    finally:
        await publisher

    assert _parse_events(resp.text) == ["audit.status", "report.final"]


async def test_stream_id_and_data_lines_present(app: FastAPI):
    audit_id = "aud_format"
    await app.state.store.upsert(_minimal_record(audit_id))
    await app.state.store.append_event(
        audit_id,
        EvtReportFinal(
            audit_id=audit_id, seq=42, ts="t", report=_minimal_report(audit_id)
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=5.0
    ) as c:
        resp = await c.get(f"/api/v1/audit/{audit_id}/stream")

    assert "id: 42" in resp.text
    assert "event: report.final" in resp.text
    assert "data: {" in resp.text
