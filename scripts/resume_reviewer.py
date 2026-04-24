"""Resume an audit by running ONLY the Reviewer phase.

Loads the ``claims``, ``findings``, ``validation``, and ``repo_manifest``
artifacts from a previous audit's on-disk store, invokes the Reviewer
(via the real Managed Agents session), parses the report with repair,
and persists the report. Saves a full re-audit when only the Reviewer
failed.

Usage: uv run python scripts/resume_reviewer.py <audit_id>
"""

from __future__ import annotations

import asyncio
import sys
import time

import anthropic

from backend.agents.output_parsers import parse_json_output
from backend.agents.registry import AgentRegistry
from backend.agents.runner import AgentRunner
from backend.config import get_settings
from backend.orchestrator.repo_manifest import RepoManifest
from backend.orchestrator.store import AuditStore
from backend.orchestrator.user_messages import build_reviewer_content
from backend.schemas.claims import PaperClaims
from backend.schemas.findings import AuditFindings
from backend.schemas.report import DiagnosticReport
from backend.schemas.validation import ValidationBatch


async def _repair(client, raw_json: str, error_msg: str) -> str:
    """Minimal JSON repair via direct Messages API (no tools, no sessions)."""
    response = await asyncio.wait_for(
        client.messages.create(
            model="claude-opus-4-7",
            max_tokens=16000,
            system=(
                "You correct JSON objects so they validate against a "
                "pydantic schema. Preserve valid content; for invalid "
                "fields, remove them or substitute a reasonable value. "
                "Emit ONLY the corrected JSON inside a single fenced "
                "```json block. Do not explain, do not use tools."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "PREVIOUS_JSON:\n```json\n"
                        f"{raw_json[:12000]}\n```\n\n"
                        "VALIDATION_ERRORS:\n"
                        f"{error_msg[:3000]}\n\n"
                        "Emit the corrected JSON."
                    ),
                }
            ],
        ),
        timeout=120.0,
    )
    return "".join(getattr(b, "text", "") for b in response.content)


async def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/resume_reviewer.py <audit_id>")
        return 1
    audit_id = sys.argv[1]

    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set. Put it in .env or export it.")
        return 2

    store = AuditStore(data_root=settings.data_root_path())
    registry = AgentRegistry(settings)

    # Load all four artifacts
    claims = await store.load_artifact(audit_id, "claims", PaperClaims)
    findings = await store.load_artifact(audit_id, "findings", AuditFindings)
    validation = await store.load_artifact(
        audit_id, "validation", ValidationBatch
    )
    manifest = await store.load_artifact(
        audit_id, "repo_manifest", RepoManifest
    )

    missing = [
        name
        for name, art in [
            ("claims", claims),
            ("findings", findings),
            ("validation", validation),
            ("repo_manifest", manifest),
        ]
        if art is None
    ]
    if missing:
        print(f"Missing artifacts: {missing}")
        print(f"  expected under runtime/audits/{audit_id}/artifacts/")
        return 3

    print(f"Loaded artifacts for audit {audit_id}:")
    print(
        f"  claims:     {len(claims.metrics)} metrics, "
        f"{len(claims.datasets)} datasets, "
        f"{len(claims.architectures)} architectures"
    )
    print(f"  findings:   {len(findings.findings)}")
    print(
        f"  validation: {len(validation.results)} targeted, "
        f"{len(validation.proactive)} proactive"
    )
    print()

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    runner = AgentRunner(client, registry, settings)

    content = build_reviewer_content(
        claims_json=claims.model_dump_json(),
        findings_json=findings.model_dump_json(),
        validation_json=validation.model_dump_json(),
        manifest_json=manifest.model_dump_json(),
    )

    seq = 0

    def next_seq() -> int:
        nonlocal seq
        seq += 1
        return seq

    async def on_event(event) -> None:
        etype = getattr(event, "type", "?")
        extra = ""
        if etype == "agent.tool_use":
            extra = f" [{getattr(event, 'tool', '')}]"
        elif etype == "agent.message":
            extra = f" ({len(getattr(event, 'text', ''))} chars)"
        print(f"  -> {etype}{extra}", flush=True)

    print("Invoking Reviewer...", flush=True)
    t0 = time.monotonic()
    try:
        raw_text = await asyncio.wait_for(
            runner.run_agent(
                audit_id=audit_id,
                role="reviewer",
                user_content=content,
                on_event=on_event,
                next_seq=next_seq,
                max_turns=30,
            ),
            timeout=600.0,
        )
    except Exception as e:
        print(f"\nReviewer invocation failed: {type(e).__name__}: {e}")
        await client.close()
        return 4

    print(
        f"\nReviewer finished in {time.monotonic() - t0:.1f}s; "
        f"parsing report..."
    )

    # Persist the raw text so we can re-parse offline if the schema
    # still doesn't fit — avoids paying for another Reviewer session.
    raw_dir = settings.data_root_path() / "audits" / audit_id / "artifacts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "reviewer_raw.txt"
    raw_path.write_text(raw_text, encoding="utf-8")
    print(f"Raw reviewer output saved to: {raw_path}")

    try:
        report = await parse_json_output(
            raw_text,
            DiagnosticReport,
            repair_with=lambda raw, err: _repair(client, raw, err),
        )
    except Exception as e:
        print(f"Report parse failed: {type(e).__name__}: {e}")
        print(
            f"Raw output preserved at {raw_path}; "
            "re-parse with scripts/reparse_report.py after adjusting schema."
        )
        await client.close()
        return 5

    report.runtime_mode_used = "managed_agents"
    report.runtime_ms_total = int((time.monotonic() - t0) * 1000)

    path = await store.save_artifact(audit_id, "report", report)

    # Mark the audit record as done
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
    print()
    print(
        f"Fetch via API:\n"
        f"  curl -s http://localhost:8000/api/v1/audit/{audit_id}/report "
        "| python -m json.tool"
    )

    await client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
