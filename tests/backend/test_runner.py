from __future__ import annotations

import pytest

from backend.agents.registry import AgentRegistry
from backend.agents.runner import AgentRunner
from backend.config import Settings
from backend.errors import UnavailableError


def _settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-ant-test",
        AGENT_ID_PAPER_ANALYST="ag_pa_1",
        AGENT_ID_CODE_AUDITOR="ag_ca_2",
        AGENT_ID_VALIDATOR="ag_v_3",
        AGENT_ID_REVIEWER="ag_r_4",
        MANAGED_ENVIRONMENT_ID="env_abc",
    )
    defaults.update(overrides)
    return Settings(**defaults)


async def _noop_emit(_ev) -> None:
    return None


def _counter():
    n = 0

    def _() -> int:
        nonlocal n
        n += 1
        return n

    return _


def _runner(settings: Settings) -> AgentRunner:
    return AgentRunner(
        client=object(), registry=AgentRegistry(settings), settings=settings
    )


async def test_run_agent_delegates_to_managed_session(monkeypatch):
    captured: dict = {}

    async def fake_session(
        client, *,
        audit_id, role, agent_id, environment_id,
        user_content, on_event, next_seq, max_turns=80, session_title="",
    ):
        captured.update(
            client=client,
            audit_id=audit_id,
            role=role,
            agent_id=agent_id,
            environment_id=environment_id,
            user_content=user_content,
            max_turns=max_turns,
        )
        return "final-text-sentinel"

    monkeypatch.setattr(
        "backend.agents.runner.run_managed_session", fake_session
    )

    settings = _settings()
    runner = _runner(settings)
    result = await runner.run_agent(
        audit_id="aud1",
        role="paper_analyst",
        user_content=[{"type": "text", "text": "hi"}],
        on_event=_noop_emit,
        next_seq=_counter(),
    )
    assert result == "final-text-sentinel"
    assert captured["audit_id"] == "aud1"
    assert captured["role"] == "paper_analyst"
    assert captured["agent_id"] == "ag_pa_1"
    assert captured["environment_id"] == "env_abc"
    assert captured["user_content"] == [{"type": "text", "text": "hi"}]


async def test_last_mode_managed_on_success(monkeypatch):
    async def fake_session(*_args, **_kwargs):
        return "ok"

    monkeypatch.setattr(
        "backend.agents.runner.run_managed_session", fake_session
    )

    runner = _runner(_settings())
    await runner.run_agent(
        audit_id="aud1",
        role="paper_analyst",
        user_content=[{"type": "text", "text": "x"}],
        on_event=_noop_emit,
        next_seq=_counter(),
    )
    assert runner.last_mode == "managed_agents"


async def test_use_fallback_raises_unavailable():
    runner = _runner(_settings(USE_FALLBACK=True))
    with pytest.raises(UnavailableError, match="not yet implemented"):
        await runner.run_agent(
            audit_id="aud1",
            role="paper_analyst",
            user_content=[{"type": "text", "text": "x"}],
            on_event=_noop_emit,
            next_seq=_counter(),
        )
    assert runner.last_mode == "messages_api"


async def test_unconfigured_agent_id_raises():
    runner = _runner(_settings(AGENT_ID_PAPER_ANALYST=None))
    with pytest.raises(UnavailableError, match="not configured"):
        await runner.run_agent(
            audit_id="aud1",
            role="paper_analyst",
            user_content=[{"type": "text", "text": "x"}],
            on_event=_noop_emit,
            next_seq=_counter(),
        )


async def test_unconfigured_environment_id_raises():
    runner = _runner(_settings(MANAGED_ENVIRONMENT_ID=None))
    with pytest.raises(UnavailableError, match="Environment"):
        await runner.run_agent(
            audit_id="aud1",
            role="paper_analyst",
            user_content=[{"type": "text", "text": "x"}],
            on_event=_noop_emit,
            next_seq=_counter(),
        )


async def test_max_turns_passthrough(monkeypatch):
    captured: dict = {}

    async def fake_session(_client, **kwargs):
        captured.update(kwargs)
        return "done"

    monkeypatch.setattr(
        "backend.agents.runner.run_managed_session", fake_session
    )

    runner = _runner(_settings())
    await runner.run_agent(
        audit_id="aud1",
        role="code_auditor",
        user_content=[],
        on_event=_noop_emit,
        next_seq=_counter(),
        max_turns=120,
    )
    assert captured["max_turns"] == 120


async def test_session_failure_propagates(monkeypatch):
    from backend.errors import NonRecoverableAPIError

    async def fake_session(*_args, **_kwargs):
        raise NonRecoverableAPIError("session died")

    monkeypatch.setattr(
        "backend.agents.runner.run_managed_session", fake_session
    )

    runner = _runner(_settings())
    with pytest.raises(NonRecoverableAPIError, match="session died"):
        await runner.run_agent(
            audit_id="aud1",
            role="paper_analyst",
            user_content=[{"type": "text", "text": "x"}],
            on_event=_noop_emit,
            next_seq=_counter(),
        )
    # last_mode still reflects the attempted mode
    assert runner.last_mode == "managed_agents"
