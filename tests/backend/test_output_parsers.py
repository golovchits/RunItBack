from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from backend.agents.output_parsers import (
    normalize_audit_findings,
    normalize_paper_claims,
    normalize_reviewer_report,
    parse_json_output,
)
from backend.errors import ValidationFailedError


class _Sample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: int


async def test_parse_valid_fenced_json():
    text = 'Some preamble.\n```json\n{"name": "x", "value": 42}\n```\n'
    result = await parse_json_output(text, _Sample)
    assert result == _Sample(name="x", value=42)


async def test_parse_valid_bare_json():
    text = 'Here is the result:\n{"name": "x", "value": 42}'
    result = await parse_json_output(text, _Sample)
    assert result == _Sample(name="x", value=42)


async def test_parse_last_fenced_wins():
    text = (
        '```json\n{"name": "first", "value": 1}\n```\n'
        "Then the final answer:\n"
        '```json\n{"name": "second", "value": 2}\n```'
    )
    result = await parse_json_output(text, _Sample)
    assert result.name == "second"


async def test_parse_nested_json_object():
    # raw_decode handles nested braces correctly
    text = 'Note: {"unrelated": "bad"} and then: {"name": "real", "value": 7}'
    result = await parse_json_output(text, _Sample)
    assert result.name == "real"
    assert result.value == 7


async def test_parse_prose_and_json_in_single_fenced_block():
    # Real-world: the Code Auditor sometimes writes a single ``` fence
    # that contains notes AND the final JSON object. We must still
    # find and return just the JSON portion.
    text = (
        "```\n"
        "Dependencies:\n"
        "- torch\n"
        "- numpy\n"
        "\n"
        "Here is the output:\n"
        '{"name": "x", "value": 42}\n'
        "```"
    )
    result = await parse_json_output(text, _Sample)
    assert result == _Sample(name="x", value=42)


async def test_parse_bare_fenced_without_json_tag():
    text = '```\n{"name": "x", "value": 9}\n```'
    result = await parse_json_output(text, _Sample)
    assert result.value == 9


async def test_no_json_raises():
    with pytest.raises(ValidationFailedError, match="no JSON object"):
        await parse_json_output("no json here at all", _Sample)


async def test_schema_violation_no_repair_raises():
    text = '```json\n{"name": "x"}\n```'
    with pytest.raises(ValidationFailedError, match="validation failed"):
        await parse_json_output(text, _Sample)


async def test_schema_violation_repaired():
    text = '```json\n{"name": "x"}\n```'
    calls = []

    async def repair(raw: str, err: str) -> str:
        calls.append((raw, err))
        return '```json\n{"name": "x", "value": 42}\n```'

    result = await parse_json_output(text, _Sample, repair_with=repair)
    assert result == _Sample(name="x", value=42)
    assert len(calls) == 1
    assert "value" in calls[0][1].lower() or "missing" in calls[0][1].lower()


async def test_repair_returns_still_invalid():
    text = '```json\n{"name": "x"}\n```'

    async def bad_repair(raw: str, err: str) -> str:
        return '```json\n{"name": "y"}\n```'  # still missing value

    with pytest.raises(ValidationFailedError, match="still invalid"):
        await parse_json_output(text, _Sample, repair_with=bad_repair)


async def test_repair_callable_raises():
    text = '```json\n{"name": "x"}\n```'

    async def broken_repair(raw: str, err: str) -> str:
        raise RuntimeError("boom")

    with pytest.raises(ValidationFailedError, match="repair call failed"):
        await parse_json_output(text, _Sample, repair_with=broken_repair)


async def test_repair_returns_bare_json_without_fence():
    text = '```json\n{"name": "x"}\n```'

    async def repair(raw: str, err: str) -> str:
        return '{"name": "x", "value": 99}'

    result = await parse_json_output(text, _Sample, repair_with=repair)
    assert result.value == 99


async def test_extra_field_rejected_with_forbid():
    text = '```json\n{"name": "x", "value": 1, "extra": "nope"}\n```'
    with pytest.raises(ValidationFailedError):
        await parse_json_output(text, _Sample)


# ---- normalize_with kwarg ----


async def test_normalize_with_rewrites_fields_before_validation():
    """normalize_with runs BEFORE validation — fields it produces
    should flow straight into model_validate."""
    text = '```json\n{"name": "x", "aliased_value": 7}\n```'

    def renamer(obj: dict) -> dict:
        if "aliased_value" in obj and "value" not in obj:
            obj["value"] = obj.pop("aliased_value")
        return obj

    result = await parse_json_output(text, _Sample, normalize_with=renamer)
    assert result == _Sample(name="x", value=7)


async def test_normalize_with_runs_again_after_repair():
    """If the first normalize-then-validate still fails and repair
    runs, the repaired output is normalized again before validation."""
    text = '```json\n{"name": "x", "aliased_value": "not-a-number"}\n```'

    async def repair(raw: str, err: str) -> str:
        # Repair fixes the number, but keeps the (post-normalize) key name.
        return '```json\n{"name": "x", "value": 99}\n```'

    def renamer(obj: dict) -> dict:
        if "aliased_value" in obj and "value" not in obj:
            obj["value"] = obj.pop("aliased_value")
        return obj

    result = await parse_json_output(
        text, _Sample, repair_with=repair, normalize_with=renamer
    )
    assert result.value == 99


# ---- normalize_reviewer_report ----


def test_normalize_reviewer_renames_overall_confidence():
    obj = {"overall_confidence": 0.42, "verdict": "inconclusive"}
    out = normalize_reviewer_report(
        obj, audit_id="aud1", generated_at="2026-04-23T00:00:00Z"
    )
    assert out["confidence"] == 0.42
    assert "overall_confidence" not in out


def test_normalize_reviewer_renames_config_discrepancies():
    obj = {"config_discrepancies": []}
    out = normalize_reviewer_report(
        obj, audit_id="aud1", generated_at="t"
    )
    assert out["config_comparison"] == []
    assert "config_discrepancies" not in out


def test_normalize_reviewer_does_not_overwrite_canonical_field():
    """If the canonical field is present, the alias must not clobber
    it. (The alias itself survives but gets stripped by the schema's
    extra="ignore" during validation.)"""
    obj = {
        "overall_confidence": 0.42,
        "confidence": 0.8,  # already present — must win
    }
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["confidence"] == 0.8


def test_normalize_reviewer_stamps_missing_audit_id_and_generated_at():
    obj = {"verdict": "inconclusive"}
    out = normalize_reviewer_report(
        obj, audit_id="aud42", generated_at="2026-04-23T12:00:00Z"
    )
    assert out["audit_id"] == "aud42"
    assert out["generated_at"] == "2026-04-23T12:00:00Z"


def test_normalize_reviewer_keeps_existing_audit_id():
    obj = {"audit_id": "original"}
    out = normalize_reviewer_report(
        obj, audit_id="new", generated_at="t"
    )
    assert out["audit_id"] == "original"


def test_normalize_reviewer_lowercases_verdict():
    obj = {"verdict": "INCONCLUSIVE"}
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["verdict"] == "inconclusive"


def test_normalize_reviewer_derives_headline_from_executive_summary():
    obj = {"executive_summary": "Verdict: unclear.\n\nMore details follow..."}
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["headline"] == "Verdict: unclear."


def test_normalize_reviewer_does_not_overwrite_existing_headline():
    obj = {"headline": "kept", "executive_summary": "would be derived"}
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["headline"] == "kept"


def test_normalize_reviewer_noop_on_non_dict():
    assert (
        normalize_reviewer_report("not a dict", audit_id="x", generated_at="t")
        == "not a dict"
    )


def test_normalize_reviewer_joins_claim_verifications_from_findings():
    """Reviewer agents routinely leave claim_verifications at the default
    "unchecked" with empty linked_finding_ids even when findings clearly
    reference the claim. The deterministic post-pass wires up the join
    from paper_claim_refs + validator verdicts."""
    obj = {
        "claim_verifications": [
            # Will flip to not_verified: finding f1 references it, verdict confirmed
            {"claim_id": "claim_001", "status": "unchecked"},
            # Will flip to verified: all linked findings denied
            {"claim_id": "claim_002", "status": "unchecked"},
            # Will flip to partial: mix of denied + inconclusive
            {"claim_id": "claim_003", "status": "unchecked"},
            # Linked but no verdict → stays unchecked (no evidence yet)
            {"claim_id": "claim_004", "status": "unchecked"},
            # Explicit reviewer status must be preserved
            {"claim_id": "claim_005", "status": "verified"},
        ]
    }
    auditor_findings = [
        {"id": "f1", "paper_claim_refs": ["claim_001"]},
        {"id": "f2", "paper_claim_refs": ["claim_002"]},
        {"id": "f3", "paper_claim_refs": ["claim_003"]},
        {"id": "f4", "paper_claim_refs": ["claim_003"]},
        {"id": "f5", "paper_claim_refs": ["claim_004"]},
        {"id": "f6", "paper_claim_refs": ["claim_005"]},
    ]
    validation_results = [
        {"finding_id": "f1", "verdict": "confirmed"},
        {"finding_id": "f2", "verdict": "denied"},
        {"finding_id": "f3", "verdict": "denied"},
        {"finding_id": "f4", "verdict": "inconclusive"},
        # f5 deliberately has no verdict
        {"finding_id": "f6", "verdict": "confirmed"},
    ]
    out = normalize_reviewer_report(
        obj,
        audit_id="x",
        generated_at="t",
        auditor_findings=auditor_findings,
        validation_results=validation_results,
    )
    by_id = {cv["claim_id"]: cv for cv in out["claim_verifications"]}
    assert by_id["claim_001"]["status"] == "not_verified"
    assert by_id["claim_001"]["linked_finding_ids"] == ["f1"]
    assert by_id["claim_002"]["status"] == "verified"
    assert by_id["claim_002"]["linked_finding_ids"] == ["f2"]
    assert by_id["claim_003"]["status"] == "partial"
    assert set(by_id["claim_003"]["linked_finding_ids"]) == {"f3", "f4"}
    assert by_id["claim_004"]["status"] == "unchecked"
    assert by_id["claim_004"]["linked_finding_ids"] == ["f5"]
    # Explicit reviewer verdict wins; link is still added for UI surfacing.
    assert by_id["claim_005"]["status"] == "verified"
    assert by_id["claim_005"]["linked_finding_ids"] == ["f6"]


def test_normalize_reviewer_join_respects_validator_new_findings():
    """Validator-emitted new_findings also carry paper_claim_refs and
    must contribute to the join index."""
    obj = {
        "claim_verifications": [
            {"claim_id": "claim_xyz", "status": "unchecked"},
        ]
    }
    validator_new = [
        {"id": "vf1", "paper_claim_refs": ["claim_xyz"]},
    ]
    validation_results = [{"finding_id": "vf1", "verdict": "confirmed"}]
    out = normalize_reviewer_report(
        obj,
        audit_id="x",
        generated_at="t",
        validator_new_findings=validator_new,
        validation_results=validation_results,
    )
    cv = out["claim_verifications"][0]
    assert cv["status"] == "not_verified"
    assert cv["linked_finding_ids"] == ["vf1"]


def test_normalize_reviewer_join_is_skipped_when_data_missing():
    """Backwards-compatibility: when no findings/validation are supplied
    (e.g., older callers, tests of pure drift coercion), the join
    post-pass must be a no-op."""
    obj = {
        "claim_verifications": [
            {"claim_id": "c1", "status": "unchecked", "linked_finding_ids": []},
        ]
    }
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    cv = out["claim_verifications"][0]
    assert cv["status"] == "unchecked"
    assert cv["linked_finding_ids"] == []


# ---- normalize_audit_findings ----


def test_normalize_audit_findings_backfills_repo_summary():
    obj = {"findings": []}
    out = normalize_audit_findings(obj)
    assert out["repo_summary"].startswith(
        "Repository summary not emitted"
    )


def test_normalize_audit_findings_keeps_explicit_repo_summary():
    obj = {"findings": [], "repo_summary": "tour complete"}
    out = normalize_audit_findings(obj)
    assert out["repo_summary"] == "tour complete"


def test_normalize_audit_findings_defaults_missing_lists():
    obj = {}
    out = normalize_audit_findings(obj)
    assert out["findings"] == []
    assert out["targeted_check_requests"] == []


def test_normalize_audit_findings_end_to_end_accepts_real_world_drift():
    """The exact failure shape from the bug report: repo_summary
    missing + eda.splits_observed as a list. Must validate after
    normalize + the DataEDA field_validator."""
    from backend.schemas.findings import AuditFindings

    obj = {
        "findings": [
            {
                "id": "f_leakage_001",
                "category": "determinism.missing_seeds",
                "severity": "high",
                "title": "No seed set",
                "description": "train.py does not set any seeds.",
                "confidence": 0.9,
                "detector": "auditor",
            }
        ],
        "eda": {
            "splits_observed": ["Train", "Validation", "Test"],
            "class_distribution": {
                "train": {"Foreground": 14, "Background": 12},
            },
        },
        # repo_summary deliberately omitted
    }
    normalized = normalize_audit_findings(obj)
    af = AuditFindings.model_validate(normalized)
    assert af.repo_summary.startswith("Repository summary")
    assert af.eda is not None
    assert set(af.eda.splits_observed.keys()) == {
        "Train", "Validation", "Test",
    }
    assert all(v == 0 for v in af.eda.splits_observed.values())
    assert len(af.findings) == 1


# ---- normalize_paper_claims ----


def test_normalize_paper_claims_backfills_extraction_confidence():
    obj = {"paper_title": "t", "authors": []}
    out = normalize_paper_claims(obj)
    assert out["extraction_confidence"] == 0.5


def test_normalize_paper_claims_keeps_explicit_confidence():
    obj = {"paper_title": "t", "authors": [], "extraction_confidence": 0.9}
    out = normalize_paper_claims(obj)
    assert out["extraction_confidence"] == 0.9


def test_normalize_paper_claims_treats_null_as_missing():
    obj = {"paper_title": "t", "authors": [], "extraction_confidence": None}
    out = normalize_paper_claims(obj)
    assert out["extraction_confidence"] == 0.5


def test_normalize_paper_claims_coerces_single_author_string():
    obj = {"paper_title": "t", "authors": "solo author"}
    out = normalize_paper_claims(obj)
    assert out["authors"] == ["solo author"]


def test_normalize_paper_claims_fills_missing_authors():
    obj = {"paper_title": "t"}
    out = normalize_paper_claims(obj)
    assert out["authors"] == []


def test_normalize_paper_claims_end_to_end_accepts_agent_drift():
    """The exact failure mode from the bug report: extraction_confidence
    omitted AND splits given as bare strings. Should validate after
    the normalizer + the schema's _coerce_splits validator."""
    from backend.schemas.claims import PaperClaims

    obj = {
        "paper_title": "nanoGPT paper",
        "authors": ["Karpathy"],
        "abstract_summary": "short",
        "datasets": [
            {
                "id": "claim_datasets_001",
                "name": "OpenWebText",
                "splits": ["train", "val"],  # WRONG shape — coerced
            }
        ],
        # extraction_confidence deliberately omitted
    }
    normalized = normalize_paper_claims(obj)
    claims = PaperClaims.model_validate(normalized)
    assert claims.extraction_confidence == 0.5
    assert len(claims.datasets[0].splits) == 2
    assert claims.datasets[0].splits[0].name == "train"
    assert claims.datasets[0].splits[1].name == "val"


def test_normalize_reviewer_coerces_unknown_config_severity_to_info():
    obj = {
        "config_comparison": [
            {"parameter": "lr", "match": False, "severity": "WARN"},
            {"parameter": "bs", "match": False, "severity": "HIGH"},
            {"parameter": "opt", "match": False},  # missing severity
        ],
    }
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["config_comparison"][0]["severity"] == "info"  # WARN → info
    assert out["config_comparison"][1]["severity"] == "high"  # HIGH → high
    # The "missing" case is left to the schema default (already "info").
    assert out["config_comparison"][2].get("severity", "info") == "info"


def test_normalize_reviewer_preserves_valid_config_severity():
    obj = {
        "config_comparison": [
            {"parameter": "lr", "match": False, "severity": "critical"},
        ],
    }
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["config_comparison"][0]["severity"] == "critical"


def test_normalize_reviewer_backfills_missing_lists():
    obj = {"verdict": "inconclusive", "confidence": 0.5}
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["findings"] == []
    assert out["claim_verifications"] == []
    assert out["config_comparison"] == []
    assert out["recommendations"] == []
    assert out["unresolved_disagreements"] == []
    assert out["severity_counts"] == {}


def test_normalize_reviewer_clamps_confidence_over_one():
    obj = {"confidence": 1.5}
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["confidence"] == 1.0


def test_normalize_reviewer_clamps_negative_confidence():
    obj = {"confidence": -0.3}
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["confidence"] == 0.0


def test_normalize_reviewer_defaults_null_confidence_to_zero():
    obj = {"confidence": None}
    out = normalize_reviewer_report(obj, audit_id="x", generated_at="t")
    assert out["confidence"] == 0.0


def test_normalize_reviewer_end_to_end_fixes_real_world_output():
    """A structure matching the failure mode we observed on audit
    a243a021-... should normalize into a validatable DiagnosticReport."""
    from backend.schemas.report import DiagnosticReport

    obj = {
        "report_version": "1.0",
        "verdict": "INCONCLUSIVE",
        "overall_confidence": 0.35,
        "executive_summary": (
            "Validator failed; all findings unvalidated.\n\n"
            "Full details follow..."
        ),
        "findings": [],
        "claim_verifications": [],
        "config_discrepancies": [],
        "recommendations": [],
        "coverage_notes": ["ignored extra"],
    }
    normalized = normalize_reviewer_report(
        obj, audit_id="aud42", generated_at="2026-04-23T12:00:00Z"
    )
    # model_validate should succeed — all required fields present.
    report = DiagnosticReport.model_validate(normalized)
    assert report.audit_id == "aud42"
    assert report.confidence == 0.35
    assert report.verdict.value == "inconclusive"
    assert report.headline.startswith("Validator failed")


# ---- comprehensive synonym renames (regression coverage) ----


def test_normalize_reviewer_renames_config_field_to_parameter():
    """The exact drift from audit 212b6ea4: reviewer emits
    ``"field": ...`` in ``config_comparison`` entries. Without the
    rename, 14 rows fail validation and the whole report falls into
    the truncated-repair path that silently loses findings."""
    from backend.schemas.report import DiagnosticReport

    obj = {
        "verdict": "not_reproducible",
        "confidence": 0.9,
        "executive_summary": "Mismatch in LR schedule.",
        "headline": "Mismatch",
        "config_comparison": [
            {
                "field": "learning_rate_schedule",
                "paper_value": "cosine",
                "code_value": "fixed",
                "agrees": False,
                "finding_ids": ["f_01"],
            }
        ],
    }
    out = normalize_reviewer_report(
        obj, audit_id="x", generated_at="t"
    )
    assert out["config_comparison"][0]["parameter"] == (
        "learning_rate_schedule"
    )
    assert out["config_comparison"][0]["match"] is False
    assert "field" not in out["config_comparison"][0]
    assert "agrees" not in out["config_comparison"][0]
    # End-to-end: DiagnosticReport validates.
    report = DiagnosticReport.model_validate(out)
    assert report.config_comparison[0].parameter == (
        "learning_rate_schedule"
    )
    assert report.config_comparison[0].match is False


def test_normalize_reviewer_preserves_all_findings_with_suggested_fix():
    """Real reviewer output uses ``suggested_fix`` (the natural name).
    Schema has ``suggested_fix_prose``; without the rename the field
    is silently dropped. 22 findings, all with suggested_fix, should
    survive end-to-end."""
    from backend.schemas.report import DiagnosticReport

    obj = {
        "verdict": "not_reproducible",
        "confidence": 0.9,
        "executive_summary": "x",
        "headline": "x",
        "findings": [
            {
                "id": f"f_{i:02d}",
                "category": "architecture_mismatch",  # unknown → OTHER
                "severity": "high",
                "title": f"Finding {i}",
                "description": "desc",
                "confidence": 0.9,
                "detector": "auditor",
                "suggested_fix": f"fix prose for {i}",
            }
            for i in range(22)
        ],
    }
    out = normalize_reviewer_report(
        obj, audit_id="x", generated_at="t"
    )
    report = DiagnosticReport.model_validate(out)
    assert len(report.findings) == 22
    # suggested_fix was renamed to suggested_fix_prose on every entry.
    for i, f in enumerate(report.findings):
        assert f.suggested_fix_prose == f"fix prose for {i}"


def test_normalize_reviewer_renames_supporting_finding_ids():
    """Reviewer emits ``supporting_finding_ids`` on claim_verifications.
    Schema uses ``linked_finding_ids`` — missing the rename would lose
    the linkage between claims and findings in the final report."""
    obj = {
        "claim_verifications": [
            {
                "claim_id": "c_001",
                "status": "verified",
                "supporting_finding_ids": ["f_01", "f_02"],
            }
        ],
    }
    out = normalize_reviewer_report(
        obj, audit_id="x", generated_at="t"
    )
    cv = out["claim_verifications"][0]
    assert cv["linked_finding_ids"] == ["f_01", "f_02"]
    assert "supporting_finding_ids" not in cv


def test_normalize_reviewer_renames_priority_to_rank_before_fallback():
    """``priority`` → ``rank`` must happen BEFORE the index-fallback
    that sets ``rank = i + 1``. Otherwise the agent's intended order
    is discarded."""
    obj = {
        "recommendations": [
            {"priority": 5, "title": "fifth"},
            {"priority": 1, "title": "first"},
            {"priority": 3, "title": "third"},
        ],
    }
    out = normalize_reviewer_report(
        obj, audit_id="x", generated_at="t"
    )
    ranks = [r["rank"] for r in out["recommendations"]]
    assert ranks == [5, 1, 3]


def test_normalize_reviewer_reviewer_raw_212b6ea4_regression():
    """The exact failure case from the handoff: 58k-char reviewer
    output with ``field`` and ``agrees`` drift, ``supporting_finding_ids``
    drift, ``suggested_fix`` drift, and 22 findings + 61 claim
    verifications + 10 recommendations. Must validate end-to-end
    with no repair call and no entry loss.

    This is the regression test for the "raw reviewer does not
    translate correctly to the report" bug class that the user
    flagged as "frustration at the very top."
    """
    import json as _json
    from pathlib import Path

    from backend.schemas.report import DiagnosticReport

    raw_path = (
        Path(__file__).resolve().parents[2]
        / "runtime" / "audits"
        / "212b6ea4-fa83-412c-99e6-adca2e1d2a40"
        / "artifacts" / "reviewer_raw.txt"
    )
    if not raw_path.exists():
        pytest.skip(f"fixture not available: {raw_path}")
    text = raw_path.read_text(encoding="utf-8")

    # Extract the JSON like parse_json_output does.
    from backend.agents.output_parsers import _extract_json
    blob = _extract_json(text)
    assert blob is not None
    obj = _json.loads(blob)

    out = normalize_reviewer_report(
        obj,
        audit_id="212b6ea4-fa83-412c-99e6-adca2e1d2a40",
        generated_at="2026-04-23T12:00:00Z",
    )
    report = DiagnosticReport.model_validate(out)
    assert report.verdict.value == "not_reproducible"
    assert len(report.findings) == 22, (
        "regression: findings lost in translation"
    )
    assert len(report.claim_verifications) == 61, (
        "regression: claim_verifications truncated"
    )
    assert len(report.config_comparison) == 14, (
        "regression: config_comparison dropped on field-rename drift"
    )
    assert len(report.recommendations) == 10, (
        "regression: recommendations lost in translation"
    )
    assert report.severity_counts == {
        "critical": 5, "high": 7, "medium": 6, "low": 4, "info": 0,
    }, "regression: severity_counts emptied in translation"


def test_normalize_validator_raw_212b6ea4_regression():
    """Regression: validator_raw emitted ``kind`` instead of ``slug``
    on proactive checks, plus a result with ``finding_id: null``.
    Without the fixes the whole ValidationBatch fails and the
    Reviewer sees only 10 of 22 finding validations — which the
    Reviewer then reports as "f_11–f_22 unvalidated" in the final
    report. Fixing the validator translation restores full coverage."""
    import json as _json
    from pathlib import Path

    from backend.agents.output_parsers import (
        _extract_json,
        normalize_validation_batch,
    )
    from backend.schemas.validation import ValidationBatch

    raw_path = (
        Path(__file__).resolve().parents[2]
        / "runtime" / "audits"
        / "212b6ea4-fa83-412c-99e6-adca2e1d2a40"
        / "artifacts" / "validator_raw.txt"
    )
    if not raw_path.exists():
        pytest.skip(f"fixture not available: {raw_path}")
    text = raw_path.read_text(encoding="utf-8")
    blob = _extract_json(text)
    assert blob is not None
    obj = _json.loads(blob)
    normalized = normalize_validation_batch(obj)
    vb = ValidationBatch.model_validate(normalized)
    assert len(vb.results) == 23, (
        "regression: validator coverage truncated; Reviewer will "
        "see only a subset of findings as validated."
    )
    # All 22 finding ids must be covered.
    finding_ids = {r.finding_id for r in vb.results if r.finding_id}
    for i in range(1, 23):
        match = [fid for fid in finding_ids if fid.startswith(f"f_{i:02d}_")]
        assert len(match) == 1, (
            f"regression: f_{i:02d}_* not covered by validator results"
        )
    assert len(vb.proactive) == 6, (
        "regression: proactive checks dropped by missing kind→slug rename"
    )
    assert len(vb.new_findings) == 2, (
        "regression: new_findings lost; validator can't surface "
        "f_23/f_24 to the Reviewer"
    )
    # No proactive slug should be an empty-default placeholder.
    for p in vb.proactive:
        assert p.slug and not p.slug.startswith("unknown_"), (
            f"regression: proactive slug fallback fired ({p.slug!r}); "
            "kind→slug rename missed the entry"
        )


# ---- per-entry salvage ----


async def test_parse_json_output_salvages_one_bad_list_entry():
    """If normalization leaves one invalid list entry and others are
    valid, the salvage path drops only the bad one and keeps the rest
    — instead of forcing the full repair roundtrip."""
    from pydantic import BaseModel, ConfigDict, Field

    class _Item(BaseModel):
        model_config = ConfigDict(extra="ignore")
        name: str
        value: int

    class _Batch(BaseModel):
        model_config = ConfigDict(extra="ignore")
        items: list[_Item] = Field(default_factory=list)

    text = (
        '{"items": ['
        '{"name": "a", "value": 1},'
        '{"name": "b", "value": "not-an-int"},'  # bad entry
        '{"name": "c", "value": 3}'
        "]}"
    )
    result = await parse_json_output(text, _Batch)
    # Salvage drops the invalid entry; 2 valid entries survive.
    assert len(result.items) == 2
    names = {i.name for i in result.items}
    assert names == {"a", "c"}


async def test_parse_json_output_salvages_innermost_list_entry():
    """A nested list error should drop the innermost entry, not the
    whole parent — preserves more content."""
    from pydantic import BaseModel, ConfigDict, Field

    class _Inner(BaseModel):
        model_config = ConfigDict(extra="ignore")
        kind: str

    class _Outer(BaseModel):
        model_config = ConfigDict(extra="ignore")
        id: str
        inners: list[_Inner] = Field(default_factory=list)

    class _Root(BaseModel):
        model_config = ConfigDict(extra="ignore")
        outers: list[_Outer] = Field(default_factory=list)

    text = (
        '{"outers": ['
        '{"id": "o1", "inners": ['
        '{"kind": "ok"},'
        '{"kind": 42}'  # bad: int not str
        "]}"
        "]}"
    )
    # The int→str coercion in Lenient would fix this on a Lenient
    # model; for plain BaseModel the error stands. Salvage drops
    # inners[1] but keeps outers[0].
    result = await parse_json_output(text, _Root)
    assert len(result.outers) == 1
    assert result.outers[0].id == "o1"
    assert len(result.outers[0].inners) == 1
    assert result.outers[0].inners[0].kind == "ok"


async def test_parse_json_output_salvage_then_repair_if_still_fails():
    """If salvage alone can't make the object valid (e.g. required
    top-level field missing), the repair callback still runs."""
    from pydantic import BaseModel, ConfigDict, Field

    class _Item(BaseModel):
        model_config = ConfigDict(extra="ignore")
        value: int

    class _Batch(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str
        items: list[_Item] = Field(default_factory=list)

    text = (
        '{"items": ['
        '{"value": 1},'
        '{"value": "bad"}'
        "]}"
    )

    async def repair(raw: str, err: str) -> str:
        return '{"name": "recovered", "items": []}'

    result = await parse_json_output(text, _Batch, repair_with=repair)
    # Repair invoked because salvage alone couldn't satisfy ``name``.
    assert result.name == "recovered"


# ---- validator synonyms ----


def test_normalize_validator_kind_to_slug():
    """The drift that broke audit 212b6ea4: validator emitted ``kind``
    where the schema expects ``slug``. Must rename and preserve flat-
    shape ValidationResult fields lifted from the top level."""
    from backend.schemas.validation import ValidationBatch
    from backend.agents.output_parsers import normalize_validation_batch

    obj = {
        "results": [],
        "proactive": [
            {
                "id": "p_pip_resolve",
                "kind": "pip_resolve",
                "command": "pip install -r reqs.txt",
                "stdout_excerpt": "Resolved 30 packages",
                "exit_code": 0,
                "runtime_seconds": 5.0,
                "confidence": 0.9,
            }
        ],
        "new_findings": [],
        "runtime_total_seconds": 10.0,
    }
    out = normalize_validation_batch(obj)
    vb = ValidationBatch.model_validate(out)
    assert vb.proactive[0].slug == "pip_resolve"
    # Top-level ValidationResult fields were lifted into result.
    assert vb.proactive[0].result.command == "pip install -r reqs.txt"
    assert vb.proactive[0].result.exit_code == 0
    assert vb.proactive[0].result.confidence == 0.9


def test_normalize_validator_null_finding_id_coerced():
    """Validator sometimes emits an aggregate result with no target
    finding (``finding_id: null``). setdefault doesn't replace None,
    so the required-string field used to reject the whole batch."""
    from backend.schemas.validation import ValidationBatch
    from backend.agents.output_parsers import normalize_validation_batch

    obj = {
        "results": [
            {
                "id": "v_23_aggregate",
                "finding_id": None,  # null — used to kill the batch
                "verdict": "confirmed",
                "method": "structure-only aggregate check",
                "confidence": 0.95,
            }
        ],
        "proactive": [],
        "new_findings": [],
        "runtime_total_seconds": 1.0,
    }
    out = normalize_validation_batch(obj)
    vb = ValidationBatch.model_validate(out)
    assert vb.results[0].finding_id == ""
    assert vb.results[0].verdict == "confirmed"
