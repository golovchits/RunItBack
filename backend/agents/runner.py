from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from backend.agents.managed_session import run_managed_session
from backend.agents.registry import AgentRegistry
from backend.config import Settings
from backend.errors import UnavailableError
from backend.schemas.events import AgentName, SSEEvent
from backend.schemas.inputs import RuntimeMode

EventEmitter = Callable[[SSEEvent], Awaitable[None]]
SeqFactory = Callable[[], int]


class AgentRunner:
    """Dispatches agent runs between Managed Agents and Messages API modes.

    Only the Managed Agents path is implemented. The Messages API
    fallback is reserved for Day 3 (see ARCHITECTURE.md §8); if
    ``settings.USE_FALLBACK`` is true, ``run_agent`` raises
    ``UnavailableError`` with a clear message.
    """

    def __init__(
        self,
        client: Any,  # anthropic.AsyncAnthropic or test double
        registry: AgentRegistry,
        settings: Settings,
    ) -> None:
        self._client = client
        self._registry = registry
        self._settings = settings
        self.last_mode: RuntimeMode = "managed_agents"

    async def run_agent(
        self,
        *,
        audit_id: str,
        role: AgentName,
        user_content: list[dict],
        on_event: EventEmitter,
        next_seq: SeqFactory,
        max_turns: int = 80,
    ) -> str:
        """Run one agent turn-loop; return the final assistant text."""
        if self._settings.USE_FALLBACK:
            self.last_mode = "messages_api"
            raise UnavailableError(
                "Messages API fallback is not yet implemented. "
                "Set USE_FALLBACK=false to use Managed Agents mode.",
                details={"requested_mode": "messages_api"},
            )

        agent_id = self._registry.agent_id(role)
        environment_id = self._registry.environment_id()
        self.last_mode = "managed_agents"

        return await run_managed_session(
            self._client,
            audit_id=audit_id,
            role=role,
            agent_id=agent_id,
            environment_id=environment_id,
            user_content=user_content,
            on_event=on_event,
            next_seq=next_seq,
            max_turns=max_turns,
        )
