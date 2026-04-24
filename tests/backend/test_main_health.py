from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.config import Settings
from backend.main import create_app


def _make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-ant-test",
        DATA_ROOT=tmp_path,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return create_app(_make_settings(tmp_path))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def test_healthz(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["checks"]["anthropic_api_key"] is True
    assert body["checks"]["data_root"] is True


async def test_readyz_missing_api_key(tmp_path: Path) -> None:
    app = create_app(_make_settings(tmp_path, ANTHROPIC_API_KEY=""))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        resp = await c.get("/api/v1/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False
    assert body["checks"]["anthropic_api_key"] is False


async def test_unknown_route_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/nonexistent")
    assert resp.status_code == 404
