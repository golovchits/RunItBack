from __future__ import annotations

import asyncio

from backend.orchestrator.event_bus import EventBus


async def test_publish_subscribe_roundtrip():
    bus = EventBus()
    q = await bus.subscribe("a1")
    await bus.publish("a1", {"type": "test", "seq": 1})
    got = await asyncio.wait_for(q.get(), timeout=1)
    assert got == {"type": "test", "seq": 1}


async def test_multi_subscriber_fanout():
    bus = EventBus()
    q1 = await bus.subscribe("a1")
    q2 = await bus.subscribe("a1")
    await bus.publish("a1", "hello")
    assert await asyncio.wait_for(q1.get(), timeout=1) == "hello"
    assert await asyncio.wait_for(q2.get(), timeout=1) == "hello"


async def test_audit_isolation():
    bus = EventBus()
    q_a = await bus.subscribe("a1")
    q_b = await bus.subscribe("b1")
    await bus.publish("a1", "for-a")
    assert q_a.qsize() == 1
    assert q_b.qsize() == 0


async def test_unsubscribe_removes_queue():
    bus = EventBus()
    q = await bus.subscribe("a1")
    assert bus.subscriber_count("a1") == 1
    await bus.unsubscribe("a1", q)
    assert bus.subscriber_count("a1") == 0


async def test_unsubscribe_idempotent():
    bus = EventBus()
    q = await bus.subscribe("a1")
    await bus.unsubscribe("a1", q)
    await bus.unsubscribe("a1", q)  # must not raise


async def test_overflow_drops_oldest():
    bus = EventBus(queue_maxsize=2)
    q = await bus.subscribe("a1")
    await bus.publish("a1", "first")
    await bus.publish("a1", "second")
    await bus.publish("a1", "third")
    items = [await q.get() for _ in range(2)]
    assert items == ["second", "third"]


async def test_publish_to_unknown_audit_is_noop():
    bus = EventBus()
    await bus.publish("ghost", "x")  # must not raise


async def test_channel_cleaned_up_after_last_unsubscribe():
    bus = EventBus()
    q = await bus.subscribe("a1")
    await bus.unsubscribe("a1", q)
    assert "a1" not in bus._channels
