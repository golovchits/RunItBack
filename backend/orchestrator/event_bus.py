from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    """In-process pub/sub for SSE events, per-audit channels.

    Each subscriber gets a bounded queue. On overflow, the oldest item
    is dropped so publishers never block.
    """

    def __init__(self, queue_maxsize: int = 1024) -> None:
        self._channels: dict[str, list[asyncio.Queue[Any]]] = {}
        self._lock = asyncio.Lock()
        self._queue_maxsize = queue_maxsize

    async def publish(self, audit_id: str, event: Any) -> None:
        async with self._lock:
            subs = list(self._channels.get(audit_id, ()))
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                q.put_nowait(event)

    async def subscribe(self, audit_id: str) -> asyncio.Queue[Any]:
        q: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._queue_maxsize)
        async with self._lock:
            self._channels.setdefault(audit_id, []).append(q)
        return q

    async def unsubscribe(self, audit_id: str, q: asyncio.Queue[Any]) -> None:
        async with self._lock:
            subs = self._channels.get(audit_id)
            if subs is None:
                return
            try:
                subs.remove(q)
            except ValueError:
                pass
            if not subs:
                del self._channels[audit_id]

    def subscriber_count(self, audit_id: str) -> int:
        return len(self._channels.get(audit_id, ()))
