from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.config import Settings
from backend.main import create_app, setup_app_state, teardown_app_state
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
        AGENT_ID_PAPER_ANALYST="ag_pa",
        AGENT_ID_CODE_AUDITOR="ag_ca",
        AGENT_ID_VALIDATOR="ag_v",
        AGENT_ID_REVIEWER="ag_r",
        MANAGED_ENVIRONMENT_ID="env_1",
    )


class _QuickPipeline:
    """Fake pipeline that completes the audit immediately."""

    def __init__(self, audit, store, bus, runner, normalizer, settings):
        self.audit = audit
        self.store = store

    async def run(self) -> None:
        report = DiagnosticReport(
            audit_id=self.audit.id,
            generated_at="2026-04-22T14:30:00Z",
            verdict=Verdict.LIKELY_REPRODUCIBLE,
            confidence=0.9,
            headline="OK",
            executive_summary="",
            claim_verifications=[],
            findings=[],
            config_comparison=[],
            recommendations=[],
            runtime_mode_used="managed_agents",
            runtime_ms_total=1,
        )
        await self.store.save_artifact(self.audit.id, "report", report)
        self.audit.phase = "done"
        await self.store.upsert(self.audit)


class _BlockingPipeline:
    """Fake pipeline that blocks until released."""

    def __init__(self, audit, store, bus, runner, normalizer, settings):
        self.audit = audit
        self.store = store
        self.released = asyncio.Event()

    async def run(self) -> None:
        self.audit.phase = "paper_analyst"
        await self.store.upsert(self.audit)
        await self.released.wait()
        self.audit.phase = "done"
        await self.store.upsert(self.audit)


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    settings = _settings(tmp_path)
    _app = create_app(settings)
    setup_app_state(_app, settings)
    _app.state.pipeline_factory = _QuickPipeline
    try:
        yield _app
    finally:
        await teardown_app_state(_app)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _valid_request_body() -> dict:
    return {
        "paper": {
            "kind": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2504.01848",
        },
        "code": {"kind": "git", "url": "https://github.com/a/b"},
        "data": {"kind": "skip"},
    }


async def _await_audit_task(app: FastAPI, audit_id: str) -> None:
    task = app.state.running_tasks.get(audit_id)
    if task:
        try:
            await task
        except Exception:
            pass


# ---- POST /audit ----


async def test_create_audit_returns_202(client: AsyncClient):
    resp = await client.post("/api/v1/audit", json=_valid_request_body())
    assert resp.status_code == 202
    body = resp.json()
    assert "audit_id" in body
    assert body["phase"] == "created"
    assert body["runtime_mode"] == "managed_agents"
    assert body["status_url"].startswith("/api/v1/audit/")
    assert body["stream_url"].startswith("/api/v1/audit/")
    assert body["report_url"].startswith("/api/v1/audit/")


async def test_create_audit_invalid_body_422(client: AsyncClient):
    resp = await client.post("/api/v1/audit", json={"bogus": "data"})
    assert resp.status_code == 422


async def test_create_audit_persists_record(app: FastAPI, client: AsyncClient):
    resp = await client.post("/api/v1/audit", json=_valid_request_body())
    audit_id = resp.json()["audit_id"]
    record = await app.state.store.get(audit_id)
    assert record is not None
    assert record.id == audit_id


async def test_create_audit_no_runner_configured(tmp_path: Path):
    settings = _settings(tmp_path)
    settings.ANTHROPIC_API_KEY = ""  # type: ignore[misc]
    app = create_app(settings)
    setup_app_state(app, settings)
    app.state.pipeline_factory = _QuickPipeline
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/api/v1/audit", json=_valid_request_body())
        assert resp.status_code == 503
    finally:
        await teardown_app_state(app)


# ---- GET /status ----


async def test_get_status_nonexistent_404(client: AsyncClient):
    resp = await client.get("/api/v1/audit/does-not-exist/status")
    assert resp.status_code == 404


async def test_roundtrip_status_reflects_completion(
    app: FastAPI, client: AsyncClient
):
    resp = await client.post("/api/v1/audit", json=_valid_request_body())
    audit_id = resp.json()["audit_id"]
    await _await_audit_task(app, audit_id)

    status_resp = await client.get(f"/api/v1/audit/{audit_id}/status")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["audit_id"] == audit_id
    assert body["phase"] == "done"
    assert body["report_ready"] is True


# ---- GET /report ----


async def test_get_report_nonexistent_404(client: AsyncClient):
    resp = await client.get("/api/v1/audit/does-not-exist/report")
    assert resp.status_code == 404


async def test_get_report_409_when_not_done(app: FastAPI, tmp_path: Path):
    record = AuditRecord(
        id="running_audit",
        request=AuditRequest(
            paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
        ),
        created_at="t",
        phase="code_auditor",
        runtime_mode="managed_agents",
    )
    await app.state.store.upsert(record)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/api/v1/audit/running_audit/report")
    assert resp.status_code == 409


async def test_get_report_200_after_completion(
    app: FastAPI, client: AsyncClient
):
    resp = await client.post("/api/v1/audit", json=_valid_request_body())
    audit_id = resp.json()["audit_id"]
    await _await_audit_task(app, audit_id)

    report_resp = await client.get(f"/api/v1/audit/{audit_id}/report")
    assert report_resp.status_code == 200
    body = report_resp.json()
    assert body["audit_id"] == audit_id
    assert body["verdict"] == "likely_reproducible"


# ---- DELETE /audit/{id} ----


async def test_delete_nonexistent_404(client: AsyncClient):
    resp = await client.delete("/api/v1/audit/does-not-exist")
    assert resp.status_code == 404


async def test_delete_cancels_running(tmp_path: Path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    setup_app_state(app, settings)
    app.state.pipeline_factory = _BlockingPipeline
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            create_resp = await c.post(
                "/api/v1/audit", json=_valid_request_body()
            )
            audit_id = create_resp.json()["audit_id"]

            # Give the task a moment to start and set phase
            await asyncio.sleep(0.05)

            del_resp = await c.delete(f"/api/v1/audit/{audit_id}")
            assert del_resp.status_code == 204

            status_resp = await c.get(f"/api/v1/audit/{audit_id}/status")
            body = status_resp.json()
            assert body["phase"] == "failed"
            assert "cancelled" in (body["error"] or "").lower()
    finally:
        await teardown_app_state(app)


# ---- resume ----


async def test_resume_nonexistent_404(client: AsyncClient):
    resp = await client.post("/api/v1/audit/does-not-exist/resume")
    assert resp.status_code == 404


async def test_resume_running_audit_409(tmp_path: Path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    setup_app_state(app, settings)
    app.state.pipeline_factory = _BlockingPipeline
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            create = await c.post("/api/v1/audit", json=_valid_request_body())
            audit_id = create.json()["audit_id"]
            # Give the background task a moment to register.
            await asyncio.sleep(0.05)
            resp = await c.post(f"/api/v1/audit/{audit_id}/resume")
            assert resp.status_code == 409
            # Cleanup: cancel so teardown doesn't hang.
            await c.delete(f"/api/v1/audit/{audit_id}")
    finally:
        await teardown_app_state(app)


async def test_resume_runs_quick_pipeline(app: FastAPI, client: AsyncClient):
    """POST /resume should kick off the pipeline for an existing record."""
    # Create + complete an initial audit.
    create = await client.post("/api/v1/audit", json=_valid_request_body())
    audit_id = create.json()["audit_id"]
    await _await_audit_task(app, audit_id)

    record = await app.state.store.get(audit_id)
    assert record is not None
    assert record.phase == "done"

    # Resume — should 202 and re-run (no-op-ish since artifacts exist).
    resume = await client.post(f"/api/v1/audit/{audit_id}/resume")
    assert resume.status_code == 202
    body = resume.json()
    assert body["audit_id"] == audit_id
    assert body["resumed"] is True
    await _await_audit_task(app, audit_id)

    updated = await app.state.store.get(audit_id)
    assert updated.phase == "done"


async def test_error_payload_shape(app: FastAPI, client: AsyncClient):
    resp = await client.get("/api/v1/audit/missing/status")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["type"] == "not_found"
    assert "missing" in body["error"]["message"]
