from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.config import Settings
from backend.main import create_app, setup_app_state, teardown_app_state


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-ant-test",
        DATA_ROOT=tmp_path,
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


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_upload_pdf_happy_path(
    app: FastAPI, client: AsyncClient, tmp_path: Path
):
    pdf_bytes = b"%PDF-1.4\nfake body\n%%EOF\n"
    files = {"file": ("paper.pdf", pdf_bytes, "application/pdf")}
    resp = await client.post("/api/v1/audit/upload-pdf", files=files)
    assert resp.status_code == 201
    body = resp.json()
    assert body["upload_id"].startswith("pdf_")
    assert body["size_bytes"] == len(pdf_bytes)

    stored = (
        app.state.settings.data_root_path()
        / "uploads"
        / f"{body['upload_id']}.pdf"
    )
    assert stored.exists()
    assert stored.read_bytes() == pdf_bytes


async def test_upload_rejects_non_pdf_content_type(client: AsyncClient):
    files = {"file": ("x.txt", b"hello", "text/plain")}
    resp = await client.post("/api/v1/audit/upload-pdf", files=files)
    assert resp.status_code == 400


async def test_upload_rejects_missing_magic_bytes(client: AsyncClient):
    files = {"file": ("fake.pdf", b"not-a-pdf", "application/pdf")}
    resp = await client.post("/api/v1/audit/upload-pdf", files=files)
    assert resp.status_code == 400
    assert "magic" in resp.json()["error"]["message"].lower()


async def test_upload_rejects_oversized(client: AsyncClient):
    body = b"%PDF-" + b"A" * (51 * 1024 * 1024)
    files = {"file": ("big.pdf", body, "application/pdf")}
    resp = await client.post("/api/v1/audit/upload-pdf", files=files)
    assert resp.status_code == 413
