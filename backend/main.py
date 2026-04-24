from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agents.registry import AgentRegistry
from .agents.runner import AgentRunner
from .api.audits import router as audits_router
from .api.files import router as files_router
from .api.stream import router as stream_router
from .api.upload import router as upload_router
from .config import Settings, get_settings
from .errors import RunItBackError
from .logging_setup import configure_logging, get_logger
from .orchestrator.event_bus import EventBus
from .orchestrator.normalizer import Normalizer
from .orchestrator.pipeline import AuditPipeline
from .orchestrator.store import AuditStore


def setup_app_state(app: FastAPI, cfg: Settings) -> None:
    """Populate ``app.state`` with the shared singletons.

    Split out from the lifespan so tests can call it directly when using
    ``ASGITransport`` (which doesn't invoke lifespan hooks).
    """
    app.state.settings = cfg
    app.state.store = AuditStore(data_root=cfg.data_root_path())
    app.state.bus = EventBus()
    app.state.registry = AgentRegistry(cfg)
    app.state.http_client = httpx.AsyncClient(
        timeout=60.0, follow_redirects=True
    )
    app.state.normalizer = Normalizer(cfg, http_client=app.state.http_client)
    app.state.anthropic_client = None
    app.state.runner = None
    if cfg.ANTHROPIC_API_KEY:
        try:
            import anthropic

            app.state.anthropic_client = anthropic.AsyncAnthropic(
                api_key=cfg.ANTHROPIC_API_KEY
            )
            app.state.runner = AgentRunner(
                app.state.anthropic_client, app.state.registry, cfg
            )
        except Exception as e:  # pragma: no cover — defensive
            get_logger("runitback.startup").warning(
                "anthropic client init failed: %s", e
            )
    app.state.running_tasks = {}
    app.state.pipeline_factory = AuditPipeline


async def teardown_app_state(app: FastAPI) -> None:
    for _id, t in list(app.state.running_tasks.items()):
        t.cancel()
    try:
        await app.state.http_client.aclose()
    except Exception:
        pass
    if app.state.anthropic_client is not None:
        try:
            await app.state.anthropic_client.close()
        except Exception:
            pass


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(cfg.LOG_LEVEL)
        cfg.data_root_path()
        setup_app_state(app, cfg)
        log = get_logger("runitback.startup")
        log.info("app.boot", data_root=str(cfg.data_root_path()))
        try:
            yield
        finally:
            log.info("app.shutdown")
            await teardown_app_state(app)

    app = FastAPI(title="RunItBack", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RunItBackError)
    async def _runitback_error_handler(
        _request: Request, exc: RunItBackError
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    app.include_router(audits_router)
    app.include_router(upload_router)
    app.include_router(files_router)
    app.include_router(stream_router)

    @app.get("/api/v1/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/readyz")
    async def readyz() -> dict[str, object]:
        checks = {
            "anthropic_api_key": bool(cfg.ANTHROPIC_API_KEY),
            "data_root": cfg.data_root_path().is_dir(),
        }
        return {"ready": all(checks.values()), "checks": checks}

    return app


app = create_app()
