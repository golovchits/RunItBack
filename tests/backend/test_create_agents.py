from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.create_agents import (
    AGENT_NAMES,
    ENV_KEYS,
    MODEL_ID,
    TOOL_CONFIGS,
    TOOLSET_TYPE,
    create_all,
    create_one,
)

ROLES = ["paper_analyst", "code_auditor", "validator", "reviewer"]


def _fake_client_returning(ids: dict[str, str]) -> MagicMock:
    """Build a fake Anthropic that returns a configured id per agent name."""
    fake = MagicMock()
    name_to_id = {
        AGENT_NAMES[role]: aid for role, aid in ids.items()
    }

    def _create(**kwargs):
        agent_id = name_to_id[kwargs["name"]]
        return MagicMock(id=agent_id)

    fake.beta.agents.create.side_effect = _create
    return fake


def test_create_one_uses_expected_fields():
    fake = MagicMock()
    fake.beta.agents.create.return_value = MagicMock(id="ag_xyz")

    result = create_one(fake, "paper_analyst")

    assert result == "ag_xyz"
    fake.beta.agents.create.assert_called_once()
    kwargs = fake.beta.agents.create.call_args.kwargs
    assert kwargs["name"] == "runitback-paper-analyst"
    assert kwargs["model"] == {"id": MODEL_ID}
    assert kwargs["system"]  # non-empty prompt loaded
    assert "<identity>" in kwargs["system"]
    assert "<role>" in kwargs["system"]
    tools = kwargs["tools"]
    assert len(tools) == 1
    assert tools[0]["type"] == TOOLSET_TYPE


def test_create_all_produces_id_per_role():
    fake = _fake_client_returning(
        {
            "paper_analyst": "ag_pa",
            "code_auditor": "ag_ca",
            "validator": "ag_v",
            "reviewer": "ag_r",
        }
    )
    ids = create_all(client=fake)
    assert ids == {
        "paper_analyst": "ag_pa",
        "code_auditor": "ag_ca",
        "validator": "ag_v",
        "reviewer": "ag_r",
    }
    assert fake.beta.agents.create.call_count == 4


@pytest.mark.parametrize("role", ROLES)
def test_tool_config_default_enabled(role):
    cfg = TOOL_CONFIGS[role]
    assert cfg["default_config"]["enabled"] is True


@pytest.mark.parametrize("role", ROLES)
def test_web_search_disabled_for_all_roles(role):
    cfg = TOOL_CONFIGS[role]
    disables = {
        entry["name"]
        for entry in cfg["configs"]
        if not entry.get("enabled", True)
    }
    assert "web_search" in disables


def test_validator_and_reviewer_disable_web_fetch():
    for role in ("validator", "reviewer"):
        disables = {
            entry["name"]
            for entry in TOOL_CONFIGS[role]["configs"]
            if not entry.get("enabled", True)
        }
        assert "web_fetch" in disables


def test_reviewer_disables_write_and_edit():
    disables = {
        entry["name"]
        for entry in TOOL_CONFIGS["reviewer"]["configs"]
        if not entry.get("enabled", True)
    }
    assert "write" in disables
    assert "edit" in disables


def test_env_keys_cover_all_roles():
    assert set(ENV_KEYS.keys()) == set(ROLES)
    for key in ENV_KEYS.values():
        assert key.startswith("AGENT_ID_")


def test_agent_names_are_unique():
    assert len(set(AGENT_NAMES.values())) == len(AGENT_NAMES)


def test_model_id_is_opus_4_7():
    assert MODEL_ID == "claude-opus-4-7"


@pytest.mark.parametrize("role", ROLES)
def test_create_one_passes_role_specific_tool_config(role):
    fake = MagicMock()
    fake.beta.agents.create.return_value = MagicMock(id="ag_x")

    create_one(fake, role)

    kwargs = fake.beta.agents.create.call_args.kwargs
    tools = kwargs["tools"]
    assert tools[0]["default_config"] == TOOL_CONFIGS[role]["default_config"]
    assert tools[0]["configs"] == TOOL_CONFIGS[role]["configs"]
