from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from backend.errors import NotFoundError

router = APIRouter(prefix="/api/v1")
_log = logging.getLogger("runitback.api.stream")

_KEEPALIVE_INTERVAL = 2.0
_ALWAYS_TERMINAL_TYPES = {"report.final"}


def _is_terminal(payload: dict) -> bool:
    t = payload.get("type")
    if t in _ALWAYS_TERMINAL_TYPES:
        return True
    if t == "audit.error" and payload.get("recoverable") is False:
        return True
    return False


def _event_to_dict(ev) -> dict:
    if isinstance(ev, dict):
        return ev
    if hasattr(ev, "model_dump"):
        return ev.model_dump(mode="json")
    raise TypeError(f"cannot serialize event: {type(ev).__name__}")


def _format_sse(payload: dict) -> bytes:
    ev_type = payload.get("type", "message")
    seq = payload.get("seq", 0)
    data = json.dumps(payload)
    return f"id: {seq}\nevent: {ev_type}\ndata: {data}\n\n".encode()


@router.get("/audit/{audit_id}/stream")
async def stream(
    audit_id: str,
    http_request: Request,
    last_event_id: Optional[str] = Header(
        default=None, alias="Last-Event-ID"
    ),
):
    state = http_request.app.state
    record = await state.store.get(audit_id)
    if record is None:
        raise NotFoundError(f"audit {audit_id!r} not found")

    since_seq = 0
    if last_event_id:
        try:
            since_seq = int(last_event_id)
        except ValueError:
            pass

    async def gen() -> AsyncIterator[bytes]:
        # Prime the connection so clients (and httpx.ASGITransport in
        # tests) unblock on stream open even if there are no events yet.
        yield b":runitback open\n\n"

        # 1. Replay persisted events (for reconnect / late subscribers).
        saw_terminal = False
        async for payload in state.store.read_events(
            audit_id, since_seq=since_seq
        ):
            yield _format_sse(payload)
            if _is_terminal(payload):
                saw_terminal = True
                break
        if saw_terminal:
            return

        # 2. Subscribe for live events.
        queue = await state.bus.subscribe(audit_id)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_INTERVAL
                    )
                    payload = _event_to_dict(ev)
                    yield _format_sse(payload)
                    if _is_terminal(payload):
                        return
                except asyncio.TimeoutError:
                    # Keepalive; also check for client disconnect here, not
                    # on every event iteration (ASGITransport can report
                    # is_disconnected() spuriously mid-stream).
                    yield b":ping\n\n"
                    if await http_request.is_disconnected():
                        return
        finally:
            await state.bus.unsubscribe(audit_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
