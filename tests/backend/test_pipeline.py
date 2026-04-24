from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from backend.config import Settings
from backend.errors import NonRecoverableAPIError, TurnLimitExceeded
from backend.orchestrator.event_bus import EventBus
from backend.orchestrator.normalizer import NormalizedPaths
from backend.orchestrator.pipeline import AuditPipeline
from backend.orchestrator.store import AuditStore
from backend.schemas.claims import PaperClaims
from backend.schemas.findings import AuditFindings
from backend.schemas.inputs import (
    AuditRecord,
    AuditRequest,
    CodeSourceGit,
    DataSourceLocal,
    DataSourceSkip,
    PaperSourceArxiv,
    PaperSourceNone,
)
from backend.schemas.report import DiagnosticReport, Verdict
from backend.schemas.validation import ValidationBatch


class _FakeRunner:
    def __init__(self, outputs: dict[str, Any] | None = None) -> None:
        self.outputs = outputs or {}
        self.calls: list[dict] = []
        self.last_mode = "managed_agents"

    async def run_agent(
        self,
        *,
        audit_id: str,
        role: str,
        user_content: list[dict],
        on_event,
        next_seq,
        max_turns: int = 80,
    ) -> str:
        self.calls.append(
            {"audit_id": audit_id, "role": role, "user_content": user_content}
        )
        out = self.outputs.get(role)
        if out is None:
            raise RuntimeError(f"no scripted output for role={role}")
        if isinstance(out, BaseException):
            raise out
        return out


class _FakeNormalizer:
    def __init__(self, paths: NormalizedPaths) -> None:
        self._paths = paths

    async def normalize(self, audit_id: str, request) -> NormalizedPaths:
        return self._paths


def _claims_json(title: str = "Test Paper") -> str:
    claims = PaperClaims(
        paper_title=title,
        authors=["A", "B"],
        abstract_summary="short",
        metrics=[],
        datasets=[],
        architectures=[],
        training_config=[],
        evaluation_protocol=[],
        extraction_confidence=0.9,
    )
    return f"```json\n{claims.model_dump_json()}\n```"


def _findings_json() -> str:
    findings = AuditFindings(findings=[], repo_summary="tour complete")
    return f"```json\n{findings.model_dump_json()}\n```"


def _validation_json() -> str:
    vb = ValidationBatch(results=[], proactive=[], runtime_total_seconds=1.5)
    return f"```json\n{vb.model_dump_json()}\n```"


def _report_json(audit_id: str = "aud1") -> str:
    report = DiagnosticReport(
        audit_id=audit_id,
        generated_at="2026-04-22T14:30:00Z",
        verdict=Verdict.LIKELY_REPRODUCIBLE,
        confidence=0.85,
        headline="Clean audit",
        executive_summary="no issues found",
        claim_verifications=[],
        findings=[],
        config_comparison=[],
        recommendations=[],
        runtime_mode_used="managed_agents",
        runtime_ms_total=0,
    )
    return f"```json\n{report.model_dump_json()}\n```"


def _happy_outputs() -> dict[str, str]:
    return {
        "paper_analyst": _claims_json(),
        "code_auditor": _findings_json(),
        "validator": _validation_json(),
        "reviewer": _report_json(),
    }


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def store(data_root: Path) -> AuditStore:
    return AuditStore(data_root=data_root)


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def settings(data_root: Path) -> Settings:
    return Settings(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-ant-test",
        DATA_ROOT=data_root,
        AGENT_ID_PAPER_ANALYST="ag_pa",
        AGENT_ID_CODE_AUDITOR="ag_ca",
        AGENT_ID_VALIDATOR="ag_v",
        AGENT_ID_REVIEWER="ag_r",
        MANAGED_ENVIRONMENT_ID="env_1",
    )


@pytest.fixture
def audit() -> AuditRecord:
    return AuditRecord(
        id="aud1",
        request=AuditRequest(
            paper=PaperSourceArxiv(
                arxiv_url="https://arxiv.org/abs/2504.01848"
            ),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            timeout_minutes=5,
        ),
        created_at="2026-04-22T14:00:00Z",
        phase="created",
        runtime_mode="managed_agents",
    )


@pytest.fixture
def paths(data_root: Path) -> NormalizedPaths:
    repo = data_root / "fake_repo"
    repo.mkdir()
    (repo / "README.md").write_text("# test\n")
    (repo / "train.py").write_text("# training\n")
    paper = data_root / "fake_paper.pdf"
    paper.write_bytes(b"%PDF-fake")
    return NormalizedPaths(
        paper_path=paper, repo_path=repo, data_path=None, source_summary="x"
    )


def _pipeline(
    audit,
    store,
    bus,
    settings,
    paths,
    *,
    outputs: dict | None = None,
) -> AuditPipeline:
    runner = _FakeRunner(outputs or _happy_outputs())
    normalizer = _FakeNormalizer(paths)
    return AuditPipeline(audit, store, bus, runner, normalizer, settings)


# ---- happy path ----


async def test_happy_path_completes_and_marks_done(
    audit, store, bus, settings, paths
):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()

    updated = await store.get(audit.id)
    assert updated is not None
    assert updated.phase == "done"


async def test_happy_path_calls_all_four_agents_in_order(
    audit, store, bus, settings, paths
):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    roles = [c["role"] for c in p.runner.calls]
    assert roles == ["paper_analyst", "code_auditor", "validator", "reviewer"]


async def test_happy_path_saves_all_artifacts(
    audit, store, bus, settings, paths
):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    assert await store.load_artifact(audit.id, "claims", PaperClaims) is not None
    assert await store.load_artifact(audit.id, "findings", AuditFindings) is not None
    assert await store.load_artifact(audit.id, "validation", ValidationBatch) is not None
    assert await store.load_artifact(audit.id, "report", DiagnosticReport) is not None


async def test_events_monotonic_seq(audit, store, bus, settings, paths):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    events = [ev async for ev in store.read_events(audit.id)]
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)
    assert seqs == list(range(1, len(seqs) + 1))


async def test_all_events_carry_audit_id(audit, store, bus, settings, paths):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    events = [ev async for ev in store.read_events(audit.id)]
    assert events
    assert all(e["audit_id"] == audit.id for e in events)


async def test_report_runtime_fields_stamped(
    audit, store, bus, settings, paths
):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    report = await store.load_artifact(audit.id, "report", DiagnosticReport)
    assert report.runtime_mode_used == "managed_agents"
    assert report.runtime_ms_total >= 0


async def test_reviewer_receives_all_three_artifacts(
    audit, store, bus, settings, paths
):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    reviewer_call = [c for c in p.runner.calls if c["role"] == "reviewer"][0]
    content = reviewer_call["user_content"]
    joined = "\n".join(b["text"] for b in content)
    assert "PAPER_CLAIMS_JSON" in joined
    assert "AUDIT_FINDINGS_JSON" in joined
    assert "VALIDATION_BATCH_JSON" in joined


async def test_code_auditor_receives_manifest(
    audit, store, bus, settings, paths
):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    ca_call = [c for c in p.runner.calls if c["role"] == "code_auditor"][0]
    content = ca_call["user_content"]
    joined = "\n".join(b["text"] for b in content)
    assert "REPO_MANIFEST_JSON" in joined
    # manifest should mention the fake repo's files
    assert "train.py" in joined


async def test_paper_analyst_receives_pdf_document_block(
    audit, store, bus, settings, paths
):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    pa_call = [c for c in p.runner.calls if c["role"] == "paper_analyst"][0]
    content = pa_call["user_content"]
    block_types = [b["type"] for b in content]
    assert "document" in block_types


# ---- failures ----


async def test_paper_analyst_failure_aborts_and_emits_error(
    audit, store, bus, settings, paths
):
    """A non-classified error (e.g. plain ValueError) still kills the
    audit — only the expected failure classes degrade gracefully."""
    p = _pipeline(
        audit,
        store,
        bus,
        settings,
        paths,
        outputs={"paper_analyst": ValueError("boom")},
    )
    with pytest.raises(ValueError):
        await p.run()

    updated = await store.get(audit.id)
    assert updated.phase == "failed"
    assert "boom" in updated.error

    events = [ev async for ev in store.read_events(audit.id)]
    error_events = [e for e in events if e.get("type") == "audit.error"]
    assert error_events
    assert error_events[0]["recoverable"] is False


async def test_paper_analyst_timeout_degrades_to_minimal_claims(
    audit, store, bus, settings, paths
):
    """Paper Analyst timeout must NOT kill the audit — it degrades to
    a minimal PaperClaims and the rest of the pipeline runs. Matches
    ARCHITECTURE.md §6.5."""
    outputs = _happy_outputs()
    outputs["paper_analyst"] = asyncio.TimeoutError()
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()  # must not raise

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    claims = await store.load_artifact(audit.id, "claims", PaperClaims)
    assert claims is not None
    # Fallback confidence: 0.2 for paper path.
    assert claims.extraction_confidence == 0.2
    assert any("paper_analyst_timeout" in q for q in claims.unresolved_questions)

    events = [ev async for ev in store.read_events(audit.id)]
    paper_errors = [
        e for e in events
        if e.get("type") == "audit.error" and e.get("agent") == "paper_analyst"
    ]
    assert paper_errors
    assert paper_errors[0]["recoverable"] is True


async def test_paper_analyst_network_drop_degrades(
    audit, store, bus, settings, paths
):
    """httpx RemoteProtocolError (the real-world 'peer closed connection
    without sending complete message body' error) wrapped as
    anthropic.APIConnectionError must degrade, not kill the audit."""
    import anthropic
    import httpx as _httpx
    outputs = _happy_outputs()
    # Mimic the SDK's behavior: wrap an httpx.RemoteProtocolError in
    # anthropic.APIConnectionError, which is what surfaces when the
    # stream reader sees an incomplete chunked body.
    req = _httpx.Request("POST", "https://api.anthropic.com/sessions/events/stream")
    transport_err = _httpx.RemoteProtocolError(
        "peer closed connection without sending complete message body "
        "(incomplete chunked read)",
        request=req,
    )
    outputs["paper_analyst"] = anthropic.APIConnectionError(request=req)
    # Set __cause__ for realism — SDK chains these.
    outputs["paper_analyst"].__cause__ = transport_err
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()  # must not raise

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    claims = await store.load_artifact(audit.id, "claims", PaperClaims)
    assert claims is not None
    assert claims.extraction_confidence == 0.2

    events = [ev async for ev in store.read_events(audit.id)]
    paper_errors = [
        e for e in events
        if e.get("type") == "audit.error" and e.get("agent") == "paper_analyst"
    ]
    assert paper_errors
    assert paper_errors[0]["recoverable"] is True
    assert paper_errors[0]["error_type"] == "api_error"


async def test_validator_network_drop_degrades(
    audit, store, bus, settings, paths
):
    import anthropic
    import httpx as _httpx
    req = _httpx.Request("POST", "https://api.anthropic.com/sessions/events/stream")
    outputs = _happy_outputs()
    outputs["validator"] = anthropic.APIConnectionError(request=req)
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()
    updated = await store.get(audit.id)
    assert updated.phase == "done"


async def test_reviewer_network_drop_degrades(
    audit, store, bus, settings, paths
):
    import anthropic
    import httpx as _httpx
    req = _httpx.Request("POST", "https://api.anthropic.com/sessions/events/stream")
    outputs = _happy_outputs()
    outputs["reviewer"] = anthropic.APIConnectionError(request=req)
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()
    updated = await store.get(audit.id)
    assert updated.phase == "done"
    report = await store.load_artifact(audit.id, "report", DiagnosticReport)
    assert report is not None
    assert "Deterministic fallback" in report.headline


async def test_paper_analyst_drifted_output_is_normalized(
    audit, store, bus, settings, paths
):
    """The exact failure shape from the bug report: extraction_confidence
    omitted AND splits as ['train', 'val']. Must validate after
    normalize + schema coercion, not fall into degrade path."""
    drifted = (
        "```json\n"
        "{"
        '"paper_title": "nanoGPT", "authors": ["Karpathy"],'
        '"abstract_summary": "small GPT impl.",'
        '"datasets": [{"id": "claim_datasets_001",'
        '"name": "OpenWebText", "splits": ["train", "val"]}],'
        '"metrics": [], "architectures": [], "training_config": [],'
        '"evaluation_protocol": [], "ablations": [], "red_flags": [],'
        '"unresolved_questions": []'
        "}\n```"
    )
    outputs = _happy_outputs()
    outputs["paper_analyst"] = drifted
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    claims = await store.load_artifact(audit.id, "claims", PaperClaims)
    assert claims is not None
    # extraction_confidence backfilled
    assert claims.extraction_confidence == 0.5
    # splits coerced
    assert len(claims.datasets[0].splits) == 2
    assert claims.datasets[0].splits[0].name == "train"

    # No audit.error should have been emitted for paper_analyst —
    # the normalizer handled it without the degrade path.
    events = [ev async for ev in store.read_events(audit.id)]
    paper_errors = [
        e for e in events
        if e.get("type") == "audit.error" and e.get("agent") == "paper_analyst"
    ]
    assert not paper_errors


async def test_paper_analyst_turn_limit_degrades(
    audit, store, bus, settings, paths
):
    outputs = _happy_outputs()
    outputs["paper_analyst"] = TurnLimitExceeded(role="paper_analyst", turns=20)
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()
    updated = await store.get(audit.id)
    assert updated.phase == "done"


async def test_paper_analyst_readme_timeout_degrades_to_empty(
    store, bus, settings, data_root: Path
):
    """README path timeout should degrade to confidence=0.0 (not 0.2)
    — the README was already weak evidence."""
    audit = AuditRecord(
        id="aud-readme-fail",
        request=AuditRequest(
            paper=PaperSourceNone(title_hint="nanoGPT"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            timeout_minutes=5,
        ),
        created_at="2026-04-22T14:00:00Z",
        phase="created",
        runtime_mode="managed_agents",
    )
    repo = data_root / "repo_readme_fail"
    repo.mkdir()
    (repo / "README.md").write_text(
        "# Project\n\n" + ("This repo implements XYZ. " * 40)
    )
    paths = NormalizedPaths(
        paper_path=None, repo_path=repo, data_path=None,
        source_summary="paper=none",
    )
    outputs = _happy_outputs()
    outputs["paper_analyst"] = asyncio.TimeoutError()
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    claims = await store.load_artifact(audit.id, "claims", PaperClaims)
    assert claims is not None
    assert claims.extraction_confidence == 0.0
    assert any(
        "paper_analyst_readme_timeout" in q
        for q in claims.unresolved_questions
    )


async def test_validator_failure_uses_empty_batch(
    audit, store, bus, settings, paths
):
    outputs = _happy_outputs()
    outputs["validator"] = NonRecoverableAPIError("session died")
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)

    await p.run()

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    vb = await store.load_artifact(audit.id, "validation", ValidationBatch)
    assert vb is not None
    assert vb.results == []
    assert "Validator failed" in vb.notes

    # non-fatal error event recorded
    events = [ev async for ev in store.read_events(audit.id)]
    validator_errors = [
        e for e in events
        if e.get("type") == "audit.error" and e.get("agent") == "validator"
    ]
    assert validator_errors
    assert validator_errors[0]["recoverable"] is True


async def test_validator_network_drop_recovers_partial_batch(
    audit, store, bus, settings, paths
):
    """Validator mid-stream connection drop — salvage whatever
    ValidationBatch the agent had emitted before the failure."""
    import anthropic
    import httpx as _httpx
    from backend.schemas.events import EvtAgentMessage

    partial_batch = (
        "```json\n"
        "{"
        '"results": [{"id":"v1","finding_id":"f1","verdict":"confirmed",'
        '"method":"bash","command":"python train.py","confidence":0.9}],'
        '"proactive": [],'
        '"unvalidated_finding_ids": [],'
        '"runtime_total_seconds": 42.0,'
        '"new_findings": [],'
        '"notes": "partial run before drop"'
        "}\n```"
    )

    class _EmittingThenFailingRunner(_FakeRunner):
        async def run_agent(
            self, *, audit_id, role, user_content, on_event, next_seq,
            max_turns=80,
        ):
            self.calls.append(
                {"audit_id": audit_id, "role": role,
                 "user_content": user_content}
            )
            if role == "validator":
                await on_event(EvtAgentMessage(
                    audit_id=audit_id, seq=next_seq(),
                    ts="2026-04-23T00:00:00Z",
                    agent="validator", text=partial_batch,
                    is_final=False,
                ))
                req = _httpx.Request("POST", "https://api.anthropic.com/x")
                raise anthropic.APIConnectionError(request=req)
            out = self.outputs.get(role)
            if isinstance(out, BaseException):
                raise out
            return out

    from backend.orchestrator.pipeline import AuditPipeline

    runner = _EmittingThenFailingRunner(_happy_outputs())
    normalizer = _FakeNormalizer(paths)
    p = AuditPipeline(audit, store, bus, runner, normalizer, settings)
    await p.run()

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    vb = await store.load_artifact(audit.id, "validation", ValidationBatch)
    assert vb is not None
    assert len(vb.results) == 1
    assert vb.results[0].verdict == "confirmed"
    assert "validator_partial_delivery_" in vb.notes


async def test_pipeline_stamps_cost_estimate_when_tokens_reported(
    audit, store, bus, settings, paths
):
    """If agents emit input/output token counts on agent.finished,
    the pipeline should compute a cost estimate and stamp it on the
    report."""
    from backend.schemas.events import EvtAgentFinished

    # Runner that injects an agent.finished with token counts before
    # returning the scripted output.
    class _TokenReportingRunner(_FakeRunner):
        async def run_agent(
            self, *, audit_id, role, user_content, on_event, next_seq,
            max_turns=80,
        ):
            self.calls.append(
                {"audit_id": audit_id, "role": role,
                 "user_content": user_content}
            )
            out = self.outputs.get(role)
            if isinstance(out, BaseException):
                raise out
            await on_event(EvtAgentFinished(
                audit_id=audit_id, seq=next_seq(),
                ts="2026-04-23T00:00:00Z",
                agent=role, duration_ms=1000,
                input_tokens=100_000,   # 100k input
                output_tokens=10_000,   # 10k output
            ))
            return out

    from backend.orchestrator.pipeline import AuditPipeline
    runner = _TokenReportingRunner(_happy_outputs())
    normalizer = _FakeNormalizer(paths)
    p = AuditPipeline(audit, store, bus, runner, normalizer, settings)
    await p.run()

    report = await store.load_artifact(audit.id, "report", DiagnosticReport)
    # 4 agents × (100k × $15 + 10k × $75) / 1M = 4 × (1.5 + 0.75) = 9.00
    assert report.cost_usd_estimate is not None
    assert abs(report.cost_usd_estimate - 9.00) < 0.01


async def test_pipeline_skips_cost_when_no_tokens_reported(
    audit, store, bus, settings, paths
):
    """Without token telemetry (happy-path FakeRunner), cost stays
    None so the frontend hides the row rather than showing $0.00."""
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()
    report = await store.load_artifact(audit.id, "report", DiagnosticReport)
    assert report.cost_usd_estimate is None


async def test_code_auditor_timeout_degrades_with_empty_findings(
    audit, store, bus, settings, paths
):
    """Code Auditor timeout now degrades to empty findings + recovery
    note, rather than killing the whole audit. No captured messages
    means nothing to salvage, but the pipeline still reaches done."""
    outputs = _happy_outputs()
    outputs["code_auditor"] = asyncio.TimeoutError()
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)

    await p.run()  # must not raise

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    findings = await store.load_artifact(audit.id, "findings", AuditFindings)
    assert findings is not None
    assert findings.findings == []
    assert any(
        "code_auditor_partial_delivery_failed" in n
        for n in findings.coverage_notes
    )

    events = [ev async for ev in store.read_events(audit.id)]
    auditor_errors = [
        e for e in events
        if e.get("type") == "audit.error" and e.get("agent") == "code_auditor"
    ]
    assert auditor_errors
    assert auditor_errors[0]["recoverable"] is True
    assert auditor_errors[0]["error_type"] == "timeout"


async def test_code_auditor_network_drop_recovers_partial_findings(
    audit, store, bus, settings, paths
):
    """The real bug scenario: Code Auditor had emitted a partial-but-
    parseable findings blob via an agent.message event BEFORE the
    network drop. Pipeline should salvage those findings rather than
    discard all the work."""
    import anthropic
    import httpx as _httpx
    from backend.schemas.events import EvtAgentMessage

    partial_findings_blob = (
        "```json\n"
        "{"
        '"findings": ['
        '  {"id": "f1", "category": "determinism.missing_seeds",'
        '   "severity": "high", "title": "No seed set",'
        '   "description": "train.py does not set any seeds.",'
        '   "confidence": 0.9, "detector": "auditor"}'
        '],'
        '"repo_summary": "partial tour before drop",'
        '"targeted_check_requests": []'
        "}\n```"
    )

    # FakeRunner that, before raising, emits one agent.message carrying
    # the partial-findings blob via the on_event callback.
    class _EmittingThenFailingRunner(_FakeRunner):
        async def run_agent(
            self, *, audit_id, role, user_content, on_event, next_seq,
            max_turns=80,
        ):
            self.calls.append(
                {"audit_id": audit_id, "role": role, "user_content": user_content}
            )
            out = self.outputs.get(role)
            if role == "code_auditor":
                # Simulate the SDK emitting a mid-stream agent.message.
                await on_event(EvtAgentMessage(
                    audit_id=audit_id, seq=next_seq(),
                    ts="2026-04-23T00:00:00Z",
                    agent="code_auditor",
                    text=partial_findings_blob,
                    is_final=False,
                ))
                # Then the connection drops.
                req = _httpx.Request("POST", "https://api.anthropic.com/x")
                raise anthropic.APIConnectionError(request=req)
            if isinstance(out, BaseException):
                raise out
            return out

    from backend.orchestrator.normalizer import NormalizedPaths
    from backend.orchestrator.pipeline import AuditPipeline

    runner = _EmittingThenFailingRunner(_happy_outputs())
    normalizer = _FakeNormalizer(paths)
    p = AuditPipeline(audit, store, bus, runner, normalizer, settings)
    await p.run()

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    findings = await store.load_artifact(audit.id, "findings", AuditFindings)
    assert findings is not None
    # The salvaged finding must be present.
    assert len(findings.findings) == 1
    assert findings.findings[0].id == "f1"
    # And tagged as partial so the Reviewer knows.
    assert any(
        "code_auditor_partial_delivery_" in n
        for n in findings.coverage_notes
    )

    # Recoverable error event was emitted.
    events = [ev async for ev in store.read_events(audit.id)]
    auditor_errors = [
        e for e in events
        if e.get("type") == "audit.error" and e.get("agent") == "code_auditor"
    ]
    assert auditor_errors
    assert auditor_errors[0]["recoverable"] is True

    # The salvaged finding was emitted to the bus so the UI populates.
    finding_events = [
        e for e in events
        if e.get("type") == "agent.finding_emitted"
    ]
    assert len(finding_events) == 1


async def test_resume_skips_phases_with_existing_artifacts(
    audit, store, bus, settings, paths
):
    """Pre-seed claims + findings. Running the pipeline should skip
    Paper Analyst and Code Auditor; only Validator + Reviewer run."""
    # Pre-seed the first two phase artifacts from the happy_outputs
    # payloads (we reuse the fixture JSON).
    import json as _json
    from backend.schemas.claims import PaperClaims as _PC
    from backend.schemas.findings import AuditFindings as _AF

    claims_wire = _json.loads(_claims_json().replace("```json\n", "").rstrip("`\n"))
    findings_wire = _json.loads(_findings_json().replace("```json\n", "").rstrip("`\n"))
    await store.save_artifact(audit.id, "claims", _PC.model_validate(claims_wire))
    await store.save_artifact(audit.id, "findings", _AF.model_validate(findings_wire))

    # Runner should NOT be called for paper_analyst / code_auditor.
    outputs = _happy_outputs()
    outputs.pop("paper_analyst")
    outputs.pop("code_auditor")

    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()

    roles = [c["role"] for c in p.runner.calls]
    assert roles == ["validator", "reviewer"]

    updated = await store.get(audit.id)
    assert updated.phase == "done"


async def test_resume_skips_all_phases_when_all_artifacts_exist(
    audit, store, bus, settings, paths
):
    """If every artifact exists, no agent is invoked at all."""
    import json as _json
    from backend.schemas.claims import PaperClaims as _PC
    from backend.schemas.findings import AuditFindings as _AF
    from backend.schemas.validation import ValidationBatch as _VB
    from backend.schemas.report import DiagnosticReport as _DR

    await store.save_artifact(
        audit.id, "claims",
        _PC.model_validate(_json.loads(_claims_json().replace("```json\n", "").rstrip("`\n"))),
    )
    await store.save_artifact(
        audit.id, "findings",
        _AF.model_validate(_json.loads(_findings_json().replace("```json\n", "").rstrip("`\n"))),
    )
    await store.save_artifact(
        audit.id, "validation",
        _VB.model_validate(_json.loads(_validation_json().replace("```json\n", "").rstrip("`\n"))),
    )
    await store.save_artifact(
        audit.id, "report",
        _DR.model_validate(_json.loads(_report_json(audit.id).replace("```json\n", "").rstrip("`\n"))),
    )

    # All runner outputs removed — any call is a bug.
    p = _pipeline(audit, store, bus, settings, paths, outputs={})
    await p.run()

    assert p.runner.calls == []
    updated = await store.get(audit.id)
    assert updated.phase == "done"


async def test_code_only_audit_skips_paper_analyst(
    store, bus, settings, data_root: Path
):
    """PaperSourceNone → pipeline does not call the Paper Analyst."""
    audit = AuditRecord(
        id="aud-code-only",
        request=AuditRequest(
            paper=PaperSourceNone(title_hint="nanoGPT"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            timeout_minutes=5,
        ),
        created_at="2026-04-22T14:00:00Z",
        phase="created",
        runtime_mode="managed_agents",
    )
    # Paths: no paper_path since code-only
    paths = NormalizedPaths(
        paper_path=None,
        repo_path=data_root / "fake_repo",
        data_path=None,
        source_summary="paper=none",
    )
    (data_root / "fake_repo").mkdir()
    (data_root / "fake_repo" / "README.md").write_text("# x\n")

    outputs = _happy_outputs()
    # Paper Analyst should NOT be invoked; remove its scripted output
    # so a misrouted call would surface as RuntimeError.
    outputs.pop("paper_analyst")
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()

    roles = [c["role"] for c in p.runner.calls]
    assert "paper_analyst" not in roles
    assert roles == ["code_auditor", "validator", "reviewer"]

    # Synthesized empty claims artifact
    claims = await store.load_artifact(audit.id, "claims", PaperClaims)
    assert claims is not None
    assert claims.extraction_confidence == 0.0
    assert claims.paper_title == "(no paper provided)"

    updated = await store.get(audit.id)
    assert updated.phase == "done"


async def test_raw_outputs_persisted_for_each_agent(
    audit, store, bus, settings, paths, data_root: Path
):
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()

    art_dir = data_root / "audits" / audit.id / "artifacts"
    for role in ("paper_analyst", "code_auditor", "validator", "reviewer"):
        raw_path = art_dir / f"{role}_raw.txt"
        assert raw_path.exists(), f"{role}_raw.txt should be written"
        content = raw_path.read_text()
        assert "```json" in content, (
            f"{role}_raw.txt should contain the fenced JSON output"
        )


async def test_reviewer_failure_triggers_deterministic_fallback(
    audit, store, bus, settings, paths
):
    """Reviewer failure → deterministic fallback, pipeline completes."""
    outputs = _happy_outputs()
    outputs["reviewer"] = NonRecoverableAPIError("reviewer blew up")
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)

    await p.run()  # no longer raises — fallback produces a report

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    report = await store.load_artifact(audit.id, "report", DiagnosticReport)
    assert report is not None
    assert "Deterministic fallback" in report.headline
    assert report.confidence <= 0.4

    # A recoverable error event should be emitted for the reviewer.
    events = [ev async for ev in store.read_events(audit.id)]
    reviewer_errors = [
        e for e in events
        if e.get("type") == "audit.error" and e.get("agent") == "reviewer"
    ]
    assert reviewer_errors
    assert reviewer_errors[0]["recoverable"] is True


# ---- TurnLimitExceeded coverage for validator + reviewer ----


async def test_validator_turn_limit_falls_back_to_empty_batch(
    audit, store, bus, settings, paths
):
    """TurnLimitExceeded from the managed session must NOT kill the
    audit — the validator should degrade to unvalidated, same as a
    timeout. The error_type should surface as 'timeout' (budget
    exhaustion category), not the scary 'internal_error'."""
    outputs = _happy_outputs()
    outputs["validator"] = TurnLimitExceeded(role="validator", turns=100)
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)

    await p.run()  # must not raise

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    vb = await store.load_artifact(audit.id, "validation", ValidationBatch)
    assert vb is not None
    assert vb.results == []
    assert "Validator failed" in vb.notes

    # Error classification should be 'timeout', not 'internal_error'.
    events = [ev async for ev in store.read_events(audit.id)]
    validator_errors = [
        e for e in events
        if e.get("type") == "audit.error" and e.get("agent") == "validator"
    ]
    assert validator_errors
    assert validator_errors[0]["error_type"] == "timeout"
    assert validator_errors[0]["recoverable"] is True


async def test_reviewer_turn_limit_triggers_deterministic_fallback(
    audit, store, bus, settings, paths
):
    """TurnLimitExceeded from the reviewer should flow into the
    deterministic-fallback branch, not crash the run."""
    outputs = _happy_outputs()
    outputs["reviewer"] = TurnLimitExceeded(role="reviewer", turns=30)
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)

    await p.run()  # must not raise

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    report = await store.load_artifact(audit.id, "report", DiagnosticReport)
    assert report is not None
    assert "Deterministic fallback" in report.headline


# ---- report.final emitted before final SQLite upsert ----


async def test_report_final_emitted_before_final_upsert(
    audit, store, bus, settings, paths
):
    """The FinalizingOverlay disappears on report.final — we want it
    in-flight BEFORE we wait on the final SQLite write, so the event
    bus and the phase=done upsert can run in that order."""
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()

    events = [ev async for ev in store.read_events(audit.id)]
    types = [e.get("type") for e in events]
    # report.final must come before the terminal audit.status(done).
    assert "report.final" in types
    assert "audit.status" in types
    rf_idx = types.index("report.final")
    done_idx = next(
        i for i, e in enumerate(events)
        if e.get("type") == "audit.status" and e.get("phase") == "done"
    )
    assert rf_idx < done_idx


# ---- Reviewer normalize hook handles drifted output ----


async def test_reviewer_drifted_output_is_normalized_and_accepted(
    audit, store, bus, settings, paths
):
    """Reviewer emits overall_confidence + uppercase verdict and omits
    audit_id/generated_at/headline — the pipeline normalizer should
    patch these before validation, producing a real report (not the
    deterministic fallback)."""
    drifted = (
        "```json\n"
        "{"
        '"verdict": "INCONCLUSIVE",'
        '"overall_confidence": 0.37,'
        '"executive_summary": "Validator failed; findings unvalidated.\\n\\nmore",'
        '"findings": [], "claim_verifications": [],'
        '"config_discrepancies": [], "recommendations": [],'
        '"severity_counts": {}'
        "}\n```"
    )
    outputs = _happy_outputs()
    outputs["reviewer"] = drifted
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()

    report = await store.load_artifact(audit.id, "report", DiagnosticReport)
    assert report is not None
    # Not the deterministic fallback:
    assert "Deterministic fallback" not in report.headline
    assert report.audit_id == audit.id
    assert report.confidence == 0.37
    assert report.verdict.value == "inconclusive"
    assert report.headline.startswith("Validator failed")


# ---- README-as-paper fallback for code-only audits ----


async def test_code_only_audit_uses_readme_when_long_enough(
    store, bus, settings, data_root: Path
):
    """When code-only and the repo has a README ≥ 500 chars, the
    Paper Analyst runs against the README (capped at 0.5 confidence)."""
    audit = AuditRecord(
        id="aud-readme",
        request=AuditRequest(
            paper=PaperSourceNone(title_hint="nanoGPT"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            timeout_minutes=5,
        ),
        created_at="2026-04-22T14:00:00Z",
        phase="created",
        runtime_mode="managed_agents",
    )
    repo = data_root / "repo_with_readme"
    repo.mkdir()
    (repo / "README.md").write_text(
        "# Project\n\n"
        + ("This repo implements XYZ. " * 40)
    )
    paths = NormalizedPaths(
        paper_path=None,
        repo_path=repo,
        data_path=None,
        source_summary="paper=none",
    )

    # Paper Analyst is expected to run with README content; claim
    # self-reports higher confidence than we allow — the pipeline
    # must clamp it.
    readme_claims = PaperClaims(
        paper_title="Project README",
        authors=[],
        abstract_summary="summary",
        extraction_confidence=0.85,  # agent self-reports high
    )
    outputs = {
        "paper_analyst": f"```json\n{readme_claims.model_dump_json()}\n```",
        "code_auditor": _findings_json(),
        "validator": _validation_json(),
        "reviewer": _report_json(audit.id),
    }
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()

    roles = [c["role"] for c in p.runner.calls]
    assert roles == [
        "paper_analyst", "code_auditor", "validator", "reviewer"
    ]
    # README content should have been passed to the Paper Analyst.
    pa_call = [c for c in p.runner.calls if c["role"] == "paper_analyst"][0]
    joined = "\n".join(b.get("text", "") for b in pa_call["user_content"])
    assert "REPO_README" in joined
    assert "This repo implements XYZ" in joined

    claims = await store.load_artifact(audit.id, "claims", PaperClaims)
    assert claims is not None
    # Confidence cap enforced even though agent said 0.85.
    assert claims.extraction_confidence == 0.5
    assert "readme_derived" in claims.unresolved_questions


async def test_local_data_path_degrades_to_skip_not_fatal(
    store, bus, settings, data_root: Path,
):
    """DataSourceLocal on the hosted runtime now degrades to
    skip-with-notice instead of killing the audit with input_error."""
    data_dir = data_root / "local_data"
    data_dir.mkdir()
    audit = AuditRecord(
        id="aud-local-data",
        request=AuditRequest(
            paper=PaperSourceArxiv(
                arxiv_url="https://arxiv.org/abs/2504.01848"
            ),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceLocal(path=data_dir),
            timeout_minutes=5,
        ),
        created_at="2026-04-22T14:00:00Z",
        phase="created",
        runtime_mode="managed_agents",
    )
    repo = data_root / "tmp_repo"
    repo.mkdir()
    (repo / "train.py").write_text("# stub\n")
    paper = data_root / "tmp_paper.pdf"
    paper.write_bytes(b"%PDF-stub")
    paths = NormalizedPaths(
        paper_path=paper, repo_path=repo, data_path=data_dir,
        source_summary="paper=arxiv | data=local",
    )
    p = _pipeline(audit, store, bus, settings, paths)
    await p.run()

    updated = await store.get(audit.id)
    assert updated.phase == "done"

    events = [ev async for ev in store.read_events(audit.id)]
    # The advisory status message should be on the wire.
    notices = [
        e for e in events
        if e.get("type") == "audit.status"
        and e.get("message")
        and "host filesystems" in e["message"]
    ]
    assert notices, "Expected a status message explaining the local-data skip"

    # code_auditor user_content should carry LOCAL_PATH_NOT_MOUNTED.
    ca_call = [c for c in p.runner.calls if c["role"] == "code_auditor"][0]
    body = "\n".join(b["text"] for b in ca_call["user_content"])
    assert "LOCAL_PATH_NOT_MOUNTED" in body


async def test_code_only_audit_skips_when_readme_too_short(
    store, bus, settings, data_root: Path
):
    """README shorter than 500 chars → skip Paper Analyst entirely."""
    audit = AuditRecord(
        id="aud-short",
        request=AuditRequest(
            paper=PaperSourceNone(),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            timeout_minutes=5,
        ),
        created_at="2026-04-22T14:00:00Z",
        phase="created",
        runtime_mode="managed_agents",
    )
    repo = data_root / "repo_short"
    repo.mkdir()
    (repo / "README.md").write_text("# tiny\n")
    paths = NormalizedPaths(
        paper_path=None,
        repo_path=repo,
        data_path=None,
        source_summary="paper=none",
    )
    outputs = _happy_outputs()
    outputs.pop("paper_analyst")  # must not be called
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()

    roles = [c["role"] for c in p.runner.calls]
    assert "paper_analyst" not in roles

    claims = await store.load_artifact(audit.id, "claims", PaperClaims)
    assert claims is not None
    assert claims.extraction_confidence == 0.0
    assert claims.paper_title == "(no paper provided)"


async def test_code_only_audit_skips_when_no_readme(
    store, bus, settings, data_root: Path
):
    """No README at all → skip Paper Analyst entirely."""
    audit = AuditRecord(
        id="aud-no-readme",
        request=AuditRequest(
            paper=PaperSourceNone(),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            timeout_minutes=5,
        ),
        created_at="2026-04-22T14:00:00Z",
        phase="created",
        runtime_mode="managed_agents",
    )
    repo = data_root / "repo_no_readme"
    repo.mkdir()
    (repo / "train.py").write_text("# code only\n")
    paths = NormalizedPaths(
        paper_path=None,
        repo_path=repo,
        data_path=None,
        source_summary="paper=none",
    )
    outputs = _happy_outputs()
    outputs.pop("paper_analyst")
    p = _pipeline(audit, store, bus, settings, paths, outputs=outputs)
    await p.run()

    roles = [c["role"] for c in p.runner.calls]
    assert "paper_analyst" not in roles

    claims = await store.load_artifact(audit.id, "claims", PaperClaims)
    assert claims is not None
    assert claims.extraction_confidence == 0.0
