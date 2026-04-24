from __future__ import annotations

from backend.config import Settings
from backend.errors import UnavailableError
from backend.schemas.events import AgentName

AgentRole = AgentName


class AgentRegistry:
    """Lookup from agent role to configured Managed Agent ID + environment."""

    def __init__(self, settings: Settings) -> None:
        self._ids: dict[str, str | None] = {
            "paper_analyst": settings.AGENT_ID_PAPER_ANALYST,
            "code_auditor": settings.AGENT_ID_CODE_AUDITOR,
            "validator": settings.AGENT_ID_VALIDATOR,
            "reviewer": settings.AGENT_ID_REVIEWER,
        }
        self._env_id = settings.MANAGED_ENVIRONMENT_ID

    def agent_id(self, role: AgentRole) -> str:
        if role not in self._ids:
            raise UnavailableError(
                f"unknown agent role: {role!r}",
                details={"role": role},
            )
        aid = self._ids[role]
        if not aid:
            raise UnavailableError(
                f"Managed Agent ID for {role!r} is not configured. "
                "Run `uv run python scripts/create_agents.py` first.",
                details={"role": role},
            )
        return aid

    def environment_id(self) -> str:
        if not self._env_id:
            raise UnavailableError(
                "Managed Environment ID is not configured. "
                "Run `uv run python scripts/create_environment.py` first.",
            )
        return self._env_id

    def all_configured(self) -> bool:
        return all(self._ids.values()) and bool(self._env_id)
