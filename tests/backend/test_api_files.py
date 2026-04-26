from __future__ import annotations

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


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-ant-test",
        DATA_ROOT=tmp_path,
    )


async def _make_audit_with_repo(
    app: FastAPI, repo_path: Path
) -> str:
    audit_id = "aud-file-test"
    record = AuditRecord(
        id=audit_id,
        request=AuditRequest(
            paper=PaperSourceArxiv(
                arxiv_url="https://arxiv.org/pdf/2504.01848"
            ),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
        ),
        created_at="t",
        phase="code_auditor",
        runtime_mode="managed_agents",
        repo_path=repo_path,
    )
    await app.state.store.upsert(record)
    return audit_id


@pytest.fixture
async def app_and_repo(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, Path]]:
    settings = _settings(tmp_path)
    app = create_app(settings)
    setup_app_state(app, settings)

    repo = tmp_path / "checkout"
    repo.mkdir()
    (repo / "README.md").write_text("# hello\nworld\n")
    (repo / "src").mkdir()
    (repo / "src" / "train.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 11)) + "\n"
    )

    try:
        yield app, repo
    finally:
        await teardown_app_state(app)


@pytest.fixture
async def client_and_audit(
    app_and_repo,
) -> AsyncIterator[tuple[AsyncClient, str]]:
    app, repo = app_and_repo
    audit_id = await _make_audit_with_repo(app, repo)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, audit_id


async def test_fetch_file_happy_path(client_and_audit):
    client, audit_id = client_and_audit
    resp = await client.get(
        f"/api/v1/audit/{audit_id}/file", params={"path": "README.md"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == "README.md"
    assert body["total_lines"] == 2
    assert "hello" in body["content"]
    assert body["sha256"]


async def test_fetch_file_line_slice(client_and_audit):
    client, audit_id = client_and_audit
    resp = await client.get(
        f"/api/v1/audit/{audit_id}/file",
        params={"path": "src/train.py", "start": 3, "end": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["start"] == 3
    assert body["end"] == 5
    assert body["total_lines"] == 10
    assert body["content"] == "line 3\nline 4\nline 5\n"


async def test_fetch_missing_file_404(client_and_audit):
    client, audit_id = client_and_audit
    resp = await client.get(
        f"/api/v1/audit/{audit_id}/file", params={"path": "no/such/file.py"}
    )
    assert resp.status_code == 404


async def test_fetch_file_rejects_absolute_path(client_and_audit):
    client, audit_id = client_and_audit
    resp = await client.get(
        f"/api/v1/audit/{audit_id}/file",
        params={"path": "/etc/passwd"},
    )
    assert resp.status_code == 400


async def test_fetch_file_rejects_dot_dot_traversal(client_and_audit):
    client, audit_id = client_and_audit
    resp = await client.get(
        f"/api/v1/audit/{audit_id}/file",
        params={"path": "../../../etc/passwd"},
    )
    assert resp.status_code == 400


async def test_fetch_file_audit_not_found(tmp_path: Path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    setup_app_state(app, settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get(
                "/api/v1/audit/nonexistent/file", params={"path": "x.txt"}
            )
        assert resp.status_code == 404
    finally:
        await teardown_app_state(app)
