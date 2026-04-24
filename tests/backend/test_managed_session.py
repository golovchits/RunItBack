from __future__ import annotations

from typing import Any

import pytest

from backend.agents.managed_session import run_managed_session
from backend.errors import NonRecoverableAPIError, TurnLimitExceeded
from backend.schemas.events import (
    EvtAgentFinished,
    EvtAgentMessage,
    EvtAgentStarted,
    EvtAgentThinking,
    EvtAgentToolResult,
    EvtAgentToolUse,
)


class _E:
    """Simple namespace to hold event attributes."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeStream:
    def __init__(self, events: list[_E]) -> None:
        self._events = list(events)

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def __aiter__(self) -> "_FakeStream":
        return self

    async def __anext__(self) -> _E:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)


class _FakeEvents:
    def __init__(self, scripted: list[_E]) -> None:
        self._scripted = scripted
        self.sent: list[tuple[str, list]] = []

    async def stream(self, session_id: str) -> _FakeStream:
        # Mirrors the real SDK: async method that, when awaited, returns
        # an AsyncStream (our _FakeStream supports both async-with and
        # async-for).
        return _FakeStream(self._scripted)

    async def send(self, session_id: str, *, events) -> None:
        self.sent.append((session_id, list(events)))


class _FakeSession:
    def __init__(self, id: str) -> None:
        self.id = id


class _FakeSessions:
    def __init__(self, scripted_events: list[_E]) -> None:
        self.events = _FakeEvents(scripted_events)
        self.created: list[dict] = []
        self.deleted: list[str] = []

    async def create(self, *, agent: str, environment_id: str, title: str):
        self.created.append(
            {"agent": agent, "environment_id": environment_id, "title": title}
        )
        return _FakeSession(id=f"sess_{len(self.created)}")

    async def delete(self, session_id: str) -> None:
        self.deleted.append(session_id)


class _FakeBeta:
    def __init__(self, scripted: list[_E]) -> None:
        self.sessions = _FakeSessions(scripted)


class _FakeClient:
    def __init__(self, scripted: list[_E] | None = None) -> None:
        self.beta = _FakeBeta(scripted or [])


def _counter():
    n = 0

    def _() -> int:
        nonlocal n
        n += 1
        return n

    return _


async def _collect(events: list):
    async def on(ev):
        events.append(ev)

    return on


async def test_happy_path_returns_final_text():
    scripted = [
        _E(type="agent.thinking"),
        _E(type="agent.message", content=[_E(type="text", text="Reading")]),
        _E(type="agent.tool_use", id="tu_1", name="grep",
           input={"pattern": "x"}),
        _E(type="agent.tool_result", tool_use_id="tu_1", is_error=False,
           content=[_E(type="text", text="match")]),
        _E(
            type="agent.message",
            content=[_E(type="text", text='```json\n{"ok": true}\n```')],
        ),
        _E(type="session.status_idle"),
    ]
    client = _FakeClient(scripted)
    emitted: list = []

    result = await run_managed_session(
        client,
        audit_id="aud1",
        role="paper_analyst",
        agent_id="ag_pa",
        environment_id="env_1",
        user_content=[{"type": "text", "text": "Extract claims"}],
        on_event=await _collect(emitted),
        next_seq=_counter(),
    )

    assert result == '```json\n{"ok": true}\n```'
    types = [type(e).__name__ for e in emitted]
    assert types == [
        "EvtAgentStarted",
        "EvtAgentThinking",
        "EvtAgentMessage",
        "EvtAgentToolUse",
        "EvtAgentToolResult",
        "EvtAgentMessage",
        "EvtAgentMessage",  # final synthesized
        "EvtAgentFinished",
    ]
    # Verify session cleanup
    assert client.beta.sessions.deleted == ["sess_1"]
    # Verify the create args
    created = client.beta.sessions.created[0]
    assert created["agent"] == "ag_pa"
    assert created["environment_id"] == "env_1"
    assert "aud1" in created["title"]


async def test_happy_path_events_carry_audit_fields():
    scripted = [
        _E(type="agent.message", content=[_E(type="text", text="hi")]),
        _E(type="session.status_idle"),
    ]
    client = _FakeClient(scripted)
    emitted: list = []

    await run_managed_session(
        client,
        audit_id="aud42",
        role="code_auditor",
        agent_id="ag_ca",
        environment_id="env_1",
        user_content=[{"type": "text", "text": "audit"}],
        on_event=await _collect(emitted),
        next_seq=_counter(),
    )

    for e in emitted:
        assert e.audit_id == "aud42"
        assert e.agent == "code_auditor"
    # sequence is monotonic
    assert [e.seq for e in emitted] == list(range(1, len(emitted) + 1))


async def test_status_terminated_raises():
    scripted = [
        _E(type="agent.message", content=[_E(type="text", text="oh")]),
        _E(type="session.status_terminated", reason="container_died"),
    ]
    client = _FakeClient(scripted)
    emitted: list = []

    with pytest.raises(NonRecoverableAPIError, match="container_died"):
        await run_managed_session(
            client,
            audit_id="aud1",
            role="validator",
            agent_id="ag_v",
            environment_id="env_1",
            user_content=[{"type": "text", "text": "run"}],
            on_event=await _collect(emitted),
            next_seq=_counter(),
        )
    assert client.beta.sessions.deleted == ["sess_1"]


async def test_max_turns_exceeded():
    scripted = [
        _E(type="agent.tool_use", id="tu_a", name="bash",
           input={"command": "ls"}),
        _E(type="agent.tool_use", id="tu_b", name="bash",
           input={"command": "pwd"}),
    ]
    client = _FakeClient(scripted)
    emitted: list = []

    with pytest.raises(TurnLimitExceeded):
        await run_managed_session(
            client,
            audit_id="aud1",
            role="reviewer",
            agent_id="ag_r",
            environment_id="env_1",
            user_content=[{"type": "text", "text": "review"}],
            on_event=await _collect(emitted),
            next_seq=_counter(),
            max_turns=1,
        )

    # interrupt sent (one user.message from initial send + one user.interrupt)
    sent_types = [e["type"] for _sid, events in client.beta.sessions.events.sent for e in events]
    assert "user.interrupt" in sent_types
    assert client.beta.sessions.deleted == ["sess_1"]


async def test_span_model_request_end_accumulates_token_usage():
    """span.model_request_end carries model_usage; totals should roll
    up onto the terminal agent.finished event so the pipeline can
    compute a cost estimate."""
    scripted = [
        _E(
            type="span.model_request_end",
            model_usage=_E(
                input_tokens=1000,
                output_tokens=200,
                cache_creation_input_tokens=500,
                cache_read_input_tokens=0,
            ),
        ),
        _E(
            type="span.model_request_end",
            model_usage=_E(
                input_tokens=800,
                output_tokens=150,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=400,
            ),
        ),
        _E(type="agent.message", content=[_E(type="text", text="done")]),
        _E(type="session.status_idle"),
    ]
    client = _FakeClient(scripted)
    emitted: list = []
    await run_managed_session(
        client, audit_id="aud1", role="reviewer",
        agent_id="ag_r", environment_id="env_1",
        user_content=[{"type": "text", "text": "x"}],
        on_event=await _collect(emitted), next_seq=_counter(),
    )
    finished = [e for e in emitted if isinstance(e, EvtAgentFinished)]
    assert finished
    # input = 1000 + 800 (fresh) + 500 (creation) + 400 (read) = 2700
    assert finished[0].input_tokens == 2700
    # output = 200 + 150 = 350
    assert finished[0].output_tokens == 350


async def test_span_model_request_start_emits_thinking_heartbeat():
    """Tool-light agents (Reviewer) produce long silent stretches —
    the span.model_request_start event is our heartbeat source."""
    scripted = [
        _E(type="span.model_request_start"),
        _E(type="agent.message", content=[_E(type="text", text="final")]),
        _E(type="session.status_idle"),
    ]
    client = _FakeClient(scripted)
    emitted: list = []

    await run_managed_session(
        client,
        audit_id="aud1",
        role="reviewer",
        agent_id="ag_r",
        environment_id="env_1",
        user_content=[{"type": "text", "text": "x"}],
        on_event=await _collect(emitted),
        next_seq=_counter(),
    )
    thinking = [e for e in emitted if isinstance(e, EvtAgentThinking)]
    assert thinking, "span.model_request_start should produce a thinking event"
    assert thinking[0].delta == "thinking…"
    assert thinking[0].agent == "reviewer"


async def test_unknown_event_type_is_ignored():
    scripted = [
        _E(type="agent.message", content=[_E(type="text", text="a")]),
        _E(type="agent.mystery", data="ignore_me"),
        _E(type="session.status_idle"),
    ]
    client = _FakeClient(scripted)
    emitted: list = []

    result = await run_managed_session(
        client,
        audit_id="aud1",
        role="paper_analyst",
        agent_id="ag_pa",
        environment_id="env_1",
        user_content=[{"type": "text", "text": "x"}],
        on_event=await _collect(emitted),
        next_seq=_counter(),
    )
    assert result == "a"
    # ensure no mystery event was emitted
    assert all(not isinstance(e, type("Fake", (), {})) for e in emitted)
    # tallied counts: started, message, final message, finished
    assert len(emitted) == 4


async def test_stream_closes_without_idle_raises():
    scripted = [
        _E(type="agent.message", content=[_E(type="text", text="incomplete")]),
        # no status_idle, no terminated — stream just ends
    ]
    client = _FakeClient(scripted)
    emitted: list = []

    with pytest.raises(NonRecoverableAPIError, match="without session.status_idle"):
        await run_managed_session(
            client,
            audit_id="aud1",
            role="paper_analyst",
            agent_id="ag_pa",
            environment_id="env_1",
            user_content=[{"type": "text", "text": "x"}],
            on_event=await _collect(emitted),
            next_seq=_counter(),
        )
    assert client.beta.sessions.deleted == ["sess_1"]


async def test_user_message_sent_with_provided_content():
    scripted = [_E(type="session.status_idle")]
    client = _FakeClient(scripted)
    content = [
        {"type": "text", "text": "hello"},
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "AAAA"}},
    ]

    await run_managed_session(
        client,
        audit_id="aud1",
        role="paper_analyst",
        agent_id="ag_pa",
        environment_id="env_1",
        user_content=content,
        on_event=await _collect([]),
        next_seq=_counter(),
    )
    sent = client.beta.sessions.events.sent
    assert len(sent) == 1
    _, events = sent[0]
    assert events[0]["type"] == "user.message"
    assert events[0]["content"] == content


async def test_tool_result_output_truncated_to_2000():
    big = "X" * 5000
    scripted = [
        _E(type="agent.tool_use", id="tu_big", name="bash",
           input={"command": "cat huge"}),
        _E(type="agent.tool_result", tool_use_id="tu_big", is_error=False,
           content=[_E(type="text", text=big)]),
        _E(type="session.status_idle"),
    ]
    client = _FakeClient(scripted)
    emitted: list = []

    await run_managed_session(
        client,
        audit_id="aud1",
        role="validator",
        agent_id="ag_v",
        environment_id="env_1",
        user_content=[{"type": "text", "text": "x"}],
        on_event=await _collect(emitted),
        next_seq=_counter(),
    )
    tool_result = [e for e in emitted if isinstance(e, EvtAgentToolResult)][0]
    assert len(tool_result.output_excerpt) == 2000


async def test_delete_failure_does_not_mask_success():
    """If session cleanup fails, the primary return value still flows."""

    class _BrokenDelete(_FakeSessions):
        async def delete(self, session_id: str) -> None:
            raise RuntimeError("cleanup boom")

    class _BrokenBeta(_FakeBeta):
        def __init__(self, scripted):
            self.sessions = _BrokenDelete(scripted)

    class _BrokenClient(_FakeClient):
        def __init__(self, scripted):
            self.beta = _BrokenBeta(scripted)

    scripted = [
        _E(type="agent.message", content=[_E(type="text", text="final")]),
        _E(type="session.status_idle"),
    ]
    client = _BrokenClient(scripted)

    result = await run_managed_session(
        client,
        audit_id="aud1",
        role="paper_analyst",
        agent_id="ag_pa",
        environment_id="env_1",
        user_content=[{"type": "text", "text": "x"}],
        on_event=await _collect([]),
        next_seq=_counter(),
    )
    assert result == "final"
