from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from backend.errors import NonRecoverableAPIError, TurnLimitExceeded
from backend.schemas.events import (
    AgentName,
    EvtAgentFinished,
    EvtAgentMessage,
    EvtAgentStarted,
    EvtAgentThinking,
    EvtAgentToolResult,
    EvtAgentToolUse,
    SSEEvent,
)
from backend.util.time import utcnow_iso

_log = logging.getLogger(__name__)

EventEmitter = Callable[[SSEEvent], Awaitable[None]]
SeqFactory = Callable[[], int]


async def run_managed_session(
    client: Any,
    *,
    audit_id: str,
    role: AgentName,
    agent_id: str,
    environment_id: str,
    user_content: list[dict],
    on_event: EventEmitter,
    next_seq: SeqFactory,
    max_turns: int = 80,
    session_title: str = "",
) -> str:
    """Run one Managed Agents session to completion.

    Returns the final assistant message text (expected to contain the
    agent's JSON output, to be parsed by ``output_parsers``).

    ``client`` is an ``anthropic.AsyncAnthropic`` or test double that
    exposes the same ``client.beta.sessions.{create,delete,events.{stream,send}}``
    surface.
    """
    title = session_title or f"runitback-{role}-{audit_id}"
    session = await client.beta.sessions.create(
        agent=agent_id,
        environment_id=environment_id,
        title=title,
    )

    await on_event(
        EvtAgentStarted(
            audit_id=audit_id,
            seq=next_seq(),
            ts=utcnow_iso(),
            agent=role,
            session_id=session.id,
            runtime_mode="managed_agents",
        )
    )

    turns = 0
    last_text = ""
    start_ns = time.monotonic_ns()
    # agent.tool_result carries only a tool_use_id — we remember the
    # tool name from the prior agent.tool_use event to display it.
    tool_name_by_use_id: dict[str, str] = {}
    # Token usage accumulators, populated from span.model_request_end
    # events and reported on agent.finished so the pipeline can compute
    # a cost estimate across all four agent sessions.
    usage_input = 0
    usage_output = 0
    usage_cache_creation = 0
    usage_cache_read = 0

    try:
        # events.stream() is an async method that returns an AsyncStream
        # once awaited; AsyncStream is itself an async context manager.
        stream = await client.beta.sessions.events.stream(session.id)
        async with stream:
            await client.beta.sessions.events.send(
                session.id,
                events=[
                    {"type": "user.message", "content": user_content},
                ],
            )

            async for event in stream:
                etype = getattr(event, "type", None)

                if etype == "agent.thinking":
                    # Progress signal, no payload; surface as an empty
                    # thinking event so the UI sees the agent is alive.
                    await on_event(
                        EvtAgentThinking(
                            audit_id=audit_id,
                            seq=next_seq(),
                            ts=utcnow_iso(),
                            agent=role,
                            delta="",
                        )
                    )

                elif etype == "span.model_request_start":
                    # Fires whenever the agent kicks off a model turn —
                    # for tool-light agents (Reviewer in particular)
                    # this is the only sign of life between started
                    # and finished. Surface as a thinking heartbeat.
                    await on_event(
                        EvtAgentThinking(
                            audit_id=audit_id,
                            seq=next_seq(),
                            ts=utcnow_iso(),
                            agent=role,
                            delta="thinking…",
                        )
                    )

                elif etype == "span.model_request_end":
                    # Token-usage telemetry. Accumulate so we can
                    # compute per-agent totals and a cost estimate for
                    # the final report.
                    usage = getattr(event, "model_usage", None)
                    if usage is not None:
                        usage_input += getattr(usage, "input_tokens", 0) or 0
                        usage_output += getattr(usage, "output_tokens", 0) or 0
                        usage_cache_creation += (
                            getattr(usage, "cache_creation_input_tokens", 0) or 0
                        )
                        usage_cache_read += (
                            getattr(usage, "cache_read_input_tokens", 0) or 0
                        )

                elif etype == "agent.message":
                    text = _join_text_blocks(getattr(event, "content", []))
                    last_text = text
                    await on_event(
                        EvtAgentMessage(
                            audit_id=audit_id,
                            seq=next_seq(),
                            ts=utcnow_iso(),
                            agent=role,
                            text=text,
                            is_final=False,
                        )
                    )

                elif etype == "agent.tool_use":
                    turns += 1
                    name = getattr(event, "name", "unknown")
                    use_id = getattr(event, "id", "")
                    if use_id:
                        tool_name_by_use_id[use_id] = name
                    summary = _summarize_tool_input(
                        name, getattr(event, "input", None)
                    )
                    await on_event(
                        EvtAgentToolUse(
                            audit_id=audit_id,
                            seq=next_seq(),
                            ts=utcnow_iso(),
                            agent=role,
                            tool=name,
                            input_summary=summary,
                        )
                    )
                    if turns > max_turns:
                        try:
                            await client.beta.sessions.events.send(
                                session.id,
                                events=[{"type": "user.interrupt"}],
                            )
                        except Exception as e:
                            _log.debug("interrupt send failed: %s", e)
                        raise TurnLimitExceeded(role=role, turns=turns)

                elif etype == "agent.tool_result":
                    use_id = getattr(event, "tool_use_id", "")
                    tool_name = tool_name_by_use_id.get(use_id, "unknown")
                    is_error = bool(getattr(event, "is_error", False))
                    output = _join_text_blocks(
                        getattr(event, "content", None) or []
                    )
                    await on_event(
                        EvtAgentToolResult(
                            audit_id=audit_id,
                            seq=next_seq(),
                            ts=utcnow_iso(),
                            agent=role,
                            tool=tool_name,
                            success=not is_error,
                            output_excerpt=output[:2000],
                        )
                    )

                elif etype == "session.status_idle":
                    await on_event(
                        EvtAgentMessage(
                            audit_id=audit_id,
                            seq=next_seq(),
                            ts=utcnow_iso(),
                            agent=role,
                            text=last_text,
                            is_final=True,
                        )
                    )
                    duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
                    # Bill cache-read tokens at the discounted input
                    # rate but include them in input_tokens so a
                    # downstream cost calculation that uses the Opus
                    # input rate doesn't over-estimate egregiously.
                    # Cache-creation tokens are reported separately and
                    # handled by the pipeline's cost math.
                    await on_event(
                        EvtAgentFinished(
                            audit_id=audit_id,
                            seq=next_seq(),
                            ts=utcnow_iso(),
                            agent=role,
                            duration_ms=int(duration_ms),
                            input_tokens=(
                                usage_input + usage_cache_read
                                + usage_cache_creation
                            ) or None,
                            output_tokens=usage_output or None,
                        )
                    )
                    return last_text

                elif etype == "session.status_terminated":
                    reason = getattr(event, "reason", "unknown")
                    raise NonRecoverableAPIError(
                        f"session {session.id} terminated: {reason}",
                        details={"session_id": session.id, "reason": reason},
                    )

                else:
                    _log.debug("managed_session: ignoring event type %r", etype)

        raise NonRecoverableAPIError(
            f"stream closed without session.status_idle "
            f"(session {session.id})",
            details={"session_id": session.id},
        )
    finally:
        try:
            await client.beta.sessions.delete(session.id)
        except Exception as e:
            _log.debug("managed_session: delete failed (ignored): %s", e)


def _join_text_blocks(blocks: Any) -> str:
    if not blocks:
        return ""
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, dict):
            if b.get("type") == "text":
                parts.append(b.get("text", "") or "")
        else:
            if getattr(b, "type", None) == "text":
                parts.append(getattr(b, "text", "") or "")
    return "".join(parts)


def _summarize_tool_input(tool: str, input_val: Any) -> str:
    if input_val is None or input_val == "":
        return tool
    s = str(input_val)
    if len(s) > 380:
        s = s[:377] + "..."
    return f"{tool}: {s}"


def _stringify(val: Any) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)):
        return "\n".join(_stringify(v) for v in val)
    if val is None:
        return ""
    return str(val)
