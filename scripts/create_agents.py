"""One-shot script: create the 4 RunItBack agents on Claude Managed Agents.

Reads each agent's system prompt from ``backend/agents/prompts/*.md``.
Prints lines ready to paste into ``.env``.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from anthropic import Anthropic

from backend.agents.prompts import load_prompt
from backend.config import get_settings

MODEL_ID = "claude-opus-4-7"
TOOLSET_TYPE = "agent_toolset_20260401"

AGENT_NAMES: dict[str, str] = {
    "paper_analyst": "runitback-paper-analyst",
    "code_auditor": "runitback-code-auditor",
    "validator": "runitback-validator",
    "reviewer": "runitback-reviewer",
}

ENV_KEYS: dict[str, str] = {
    "paper_analyst": "AGENT_ID_PAPER_ANALYST",
    "code_auditor": "AGENT_ID_CODE_AUDITOR",
    "validator": "AGENT_ID_VALIDATOR",
    "reviewer": "AGENT_ID_REVIEWER",
}

TOOL_CONFIGS: dict[str, dict[str, Any]] = {
    # Per ARCHITECTURE.md §7.1. All use the pre-built Managed Agents
    # toolset with role-specific disables.
    "paper_analyst": {
        "default_config": {"enabled": True},
        "configs": [
            {"name": "web_search", "enabled": False},
            {"name": "edit", "enabled": False},
        ],
    },
    "code_auditor": {
        "default_config": {"enabled": True},
        "configs": [
            {"name": "web_search", "enabled": False},
        ],
    },
    "validator": {
        "default_config": {"enabled": True},
        "configs": [
            {"name": "web_fetch", "enabled": False},
            {"name": "web_search", "enabled": False},
        ],
    },
    "reviewer": {
        "default_config": {"enabled": True},
        "configs": [
            {"name": "write", "enabled": False},
            {"name": "edit", "enabled": False},
            {"name": "web_fetch", "enabled": False},
            {"name": "web_search", "enabled": False},
        ],
    },
}


def create_one(client: Anthropic, role: str) -> str:
    agent = client.beta.agents.create(
        name=AGENT_NAMES[role],
        model={"id": MODEL_ID},
        system=load_prompt(role),
        tools=[{"type": TOOLSET_TYPE, **TOOL_CONFIGS[role]}],
    )
    return agent.id


def _default_client() -> Anthropic:
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Put it in .env or export it."
        )
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def create_all(client: Optional[Anthropic] = None) -> dict[str, str]:
    client = client or _default_client()
    return {role: create_one(client, role) for role in AGENT_NAMES}


def main() -> int:
    ids = create_all()
    print("# Paste into .env:")
    for role, aid in ids.items():
        print(f"{ENV_KEYS[role]}={aid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
