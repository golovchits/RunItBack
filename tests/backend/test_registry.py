from __future__ import annotations

import pytest

from backend.agents.registry import AgentRegistry
from backend.config import Settings
from backend.errors import UnavailableError


def _settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-ant-test",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_agent_id_returns_configured():
    r = AgentRegistry(_settings(
        AGENT_ID_PAPER_ANALYST="ag_pa_1",
        AGENT_ID_CODE_AUDITOR="ag_ca_2",
        AGENT_ID_VALIDATOR="ag_v_3",
        AGENT_ID_REVIEWER="ag_r_4",
    ))
    assert r.agent_id("paper_analyst") == "ag_pa_1"
    assert r.agent_id("code_auditor") == "ag_ca_2"
    assert r.agent_id("validator") == "ag_v_3"
    assert r.agent_id("reviewer") == "ag_r_4"


def test_agent_id_missing_raises_unavailable():
    r = AgentRegistry(_settings())
    with pytest.raises(UnavailableError, match="not configured"):
        r.agent_id("paper_analyst")


def test_agent_id_unknown_role_raises():
    r = AgentRegistry(_settings())
    with pytest.raises(UnavailableError, match="unknown agent role"):
        r.agent_id("ghost")  # type: ignore[arg-type]


def test_environment_id_returns_configured():
    r = AgentRegistry(_settings(MANAGED_ENVIRONMENT_ID="env_abc"))
    assert r.environment_id() == "env_abc"


def test_environment_id_missing_raises_unavailable():
    r = AgentRegistry(_settings())
    with pytest.raises(UnavailableError, match="Environment"):
        r.environment_id()


def test_all_configured_true_when_everything_set():
    r = AgentRegistry(_settings(
        AGENT_ID_PAPER_ANALYST="a",
        AGENT_ID_CODE_AUDITOR="b",
        AGENT_ID_VALIDATOR="c",
        AGENT_ID_REVIEWER="d",
        MANAGED_ENVIRONMENT_ID="env",
    ))
    assert r.all_configured() is True


def test_all_configured_false_when_partial():
    r = AgentRegistry(_settings(
        AGENT_ID_PAPER_ANALYST="a",
        MANAGED_ENVIRONMENT_ID="env",
    ))
    assert r.all_configured() is False
