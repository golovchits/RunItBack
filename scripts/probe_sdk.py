"""Diagnostic probe: create a Managed Agents session directly, bypassing
our pipeline. Tells us whether a hang is SDK/API-side or in our code.

Usage: uv run python scripts/probe_sdk.py
"""

from __future__ import annotations

import asyncio
import sys
import time

from anthropic import AsyncAnthropic

from backend.config import get_settings


async def main() -> int:
    s = get_settings()
    missing = [
        k
        for k, v in {
            "ANTHROPIC_API_KEY": s.ANTHROPIC_API_KEY,
            "MANAGED_ENVIRONMENT_ID": s.MANAGED_ENVIRONMENT_ID,
            "AGENT_ID_PAPER_ANALYST": s.AGENT_ID_PAPER_ANALYST,
        }.items()
        if not v
    ]
    if missing:
        print(f"missing .env values: {missing}")
        return 1

    print(f"env_id:   {s.MANAGED_ENVIRONMENT_ID}")
    print(f"agent_id: {s.AGENT_ID_PAPER_ANALYST}")
    print()

    client = AsyncAnthropic(api_key=s.ANTHROPIC_API_KEY)
    print("[1] creating session (30s timeout)...", flush=True)
    t0 = time.monotonic()
    try:
        session = await asyncio.wait_for(
            client.beta.sessions.create(
                agent=s.AGENT_ID_PAPER_ANALYST,
                environment_id=s.MANAGED_ENVIRONMENT_ID,
                title="runitback-probe",
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        print(f"  TIMEOUT after {time.monotonic() - t0:.1f}s")
        print("  -> session.create hung; API or network issue")
        return 2
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        return 3
    print(f"  session.id = {session.id}  (in {time.monotonic() - t0:.1f}s)")

    print("[2] opening stream + sending user message (60s timeout)...", flush=True)
    t0 = time.monotonic()
    events_seen: list[str] = []
    try:
        async def run_once() -> None:
            async with client.beta.sessions.events.stream(session.id) as stream:
                await client.beta.sessions.events.send(
                    session.id,
                    events=[
                        {
                            "type": "user.message",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Say hello and return.",
                                }
                            ],
                        }
                    ],
                )
                async for ev in stream:
                    etype = getattr(ev, "type", "?")
                    events_seen.append(etype)
                    print(f"  <- {etype}", flush=True)
                    if etype == "session.status_idle":
                        return
                    if etype == "session.status_terminated":
                        return

        await asyncio.wait_for(run_once(), timeout=60.0)
    except asyncio.TimeoutError:
        print(f"  TIMEOUT after {time.monotonic() - t0:.1f}s")
        print(f"  events seen: {events_seen}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        print(f"  events seen: {events_seen}")
    else:
        print(f"  OK in {time.monotonic() - t0:.1f}s; {len(events_seen)} events")

    try:
        await client.beta.sessions.delete(session.id)
        print("[3] session deleted")
    except Exception as e:
        print(f"[3] delete failed (ignored): {e}")

    await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
