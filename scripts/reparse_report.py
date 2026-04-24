"""Re-parse a previously saved Reviewer raw output against the current
``DiagnosticReport`` schema — no API call, no cost.

Use after loosening ``report.py`` or ``common.py``: instead of paying
for another Reviewer invocation, read the ``reviewer_raw.txt`` left
behind by ``scripts/resume_reviewer.py`` and validate it against the
updated schema. Saves ``report.json`` on success and marks the audit
record ``done``.

Usage: uv run python scripts/reparse_report.py <audit_id>
"""

from __future__ import annotations

import asyncio
import sys

import anthropic

from datetime import datetime, timezone

from backend.agents.output_parsers import (
    normalize_reviewer_report,
    parse_json_output,
)
from backend.config import get_settings
from backend.orchestrator.store import AuditStore
from backend.schemas.findings import AuditFindings
from backend.schemas.report import DiagnosticReport


async def _repair(client, raw_json: str, error_msg: str) -> str:
    # Caps mirror ``pipeline.py::_make_repair`` for the reviewer role.
    # See that function's docstring for why 120k input / 32k output —
    # short version: smaller caps silently truncated the tail of
    # large reviewer outputs, losing findings/recommendations.
    truncated = raw_json[:120_000]
    was_truncated = len(raw_json) > 120_000
    note = (
        "\n\n[NOTE: PREVIOUS_JSON exceeded 120k chars and was truncated. "
        "Return the FULL corrected JSON, reusing the visible structure "
        "and preserving every list entry — do not omit any.]"
        if was_truncated else ""
    )
    response = await asyncio.wait_for(
        client.messages.create(
            model="claude-opus-4-7",
            max_tokens=32_000,
            system=(
                "You correct JSON objects so they validate against a "
                "pydantic schema. Preserve ALL valid content — every "
                "list entry, every field. Only modify what the errors "
                "explicitly call out. Do NOT drop list entries that "
                "weren't flagged as invalid. Emit ONLY the corrected "
                "JSON inside a single fenced ```json block. Do not "
                "explain, do not use tools."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "PREVIOUS_JSON:\n```json\n"
                        f"{truncated}\n```\n\n"
                        "VALIDATION_ERRORS:\n"
                        f"{error_msg[:8000]}\n"
                        f"{note}\n\n"
                        "Emit the corrected JSON."
                    ),
                }
            ],
        ),
        timeout=180.0,
    )
    return "".join(getattr(b, "text", "") for b in response.content)


async def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/reparse_report.py <audit_id>")
        return 1
    audit_id = sys.argv[1]

    settings = get_settings()
    store = AuditStore(data_root=settings.data_root_path())

    raw_path = (
        settings.data_root_path()
        / "audits"
        / audit_id
        / "artifacts"
        / "reviewer_raw.txt"
    )
    if not raw_path.exists():
        print(f"No reviewer_raw.txt found at {raw_path}")
        print("Run scripts/resume_reviewer.py first to produce it.")
        return 2

    raw_text = raw_path.read_text(encoding="utf-8")
    print(f"Loaded {len(raw_text)} chars from {raw_path}")

    # Repair falls back to a direct messages.create if the initial
    # parse fails. Needs an Anthropic client; only allocated on demand.
    client: anthropic.AsyncAnthropic | None = None

    async def repair(raw: str, err: str) -> str:
        nonlocal client
        if client is None:
            if not settings.ANTHROPIC_API_KEY:
                raise RuntimeError(
                    "repair needed but ANTHROPIC_API_KEY not set"
                )
            client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
        return await _repair(client, raw, err)

    # Pull the Auditor's EDA so the normalizer can backfill
    # ``eda_summary`` when the Reviewer didn't emit one.
    eda_fallback = None
    findings_art = await store.load_artifact(
        audit_id, "findings", AuditFindings
    )
    if findings_art is not None and findings_art.eda is not None:
        eda_fallback = findings_art.eda.model_dump()

    generated_at = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )

    def _normalize(obj: dict) -> dict:
        return normalize_reviewer_report(
            obj,
            audit_id=audit_id,
            generated_at=generated_at,
            eda_fallback=eda_fallback,
        )

    try:
        report = await parse_json_output(
            raw_text, DiagnosticReport,
            repair_with=repair,
            normalize_with=_normalize,
        )
    except Exception as e:
        print(f"Parse failed: {type(e).__name__}: {e}")
        if client is not None:
            await client.close()
        return 3

    path = await store.save_artifact(audit_id, "report", report)

    record = await store.get(audit_id)
    if record is not None:
        record.phase = "done"
        record.error = None
        await store.upsert(record)

    print()
    print(f"Report saved to: {path}")
    print(f"Verdict:    {report.verdict.value}")
    print(f"Confidence: {report.confidence:.2f}")
    print(f"Headline:   {report.headline}")
    print(f"Findings:   {len(report.findings)}")
    print(
        f"Claim verifications: {len(report.claim_verifications)}  |  "
        f"Recommendations: {len(report.recommendations)}"
    )

    if client is not None:
        await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
