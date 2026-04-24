from __future__ import annotations

from backend.orchestrator.reviewer_checks import build_fallback_report
from backend.schemas.claims import (
    ArchitectureClaim,
    Citation,
    DatasetClaim,
    MetricClaim,
    PaperClaims,
)
from backend.schemas.findings import (
    AuditFinding,
    AuditFindings,
    DetectorRole,
    FindingCategory,
    Severity,
)
from backend.schemas.report import ClaimVerificationStatus, Verdict
from backend.schemas.validation import ValidationBatch, ValidationResult


def _cite() -> Citation:
    return Citation(quote="q")


def _finding(
    fid: str = "f1",
    severity: Severity = Severity.MEDIUM,
) -> AuditFinding:
    return AuditFinding(
        id=fid,
        category=FindingCategory.DATA_LEAKAGE_PREPROCESSING,
        severity=severity,
        title=f"finding {fid}",
        description="d",
        confidence=0.8,
        detector=DetectorRole.AUDITOR,
    )


def _claims_with_metrics(n: int = 3) -> PaperClaims:
    return PaperClaims(
        paper_title="T",
        authors=["A"],
        abstract_summary="s",
        metrics=[
            MetricClaim(id=f"m{i}", dataset="D", citation=_cite())
            for i in range(n)
        ],
        datasets=[DatasetClaim(id="d1", name="D", citation=_cite())],
        architectures=[
            ArchitectureClaim(id="a1", architecture="X", citation=_cite())
        ],
        training_config=[],
        evaluation_protocol=[],
        extraction_confidence=0.7,
    )


def _confirmed(fid: str) -> ValidationResult:
    return ValidationResult(
        id=f"v_{fid}",
        finding_id=fid,
        verdict="confirmed",
        method="m",
        confidence=0.9,
    )


def test_fallback_empty_inputs_explains_why_report_is_empty():
    """When the cascade has degraded everything (empty findings +
    empty validation), the summary must tell the user WHY — they
    paid for the audit and deserve an actionable explanation."""
    report = build_fallback_report(
        audit_id="aud1",
        claims=_claims_with_metrics(n=0),
        findings=AuditFindings(findings=[], repo_summary="empty"),
        validation=ValidationBatch(
            results=[],
            proactive=[],
            runtime_total_seconds=0.0,
            notes="Validator failed (timeout); all findings marked unvalidated.",
        ),
        reason="validation_error",
    )
    summary = report.executive_summary
    assert "Why this report is empty" in summary
    assert "turn or" in summary.lower() or "time budget" in summary.lower()
    assert "schema" in summary.lower()


def test_fallback_surfaces_code_auditor_partial_delivery():
    """When the Auditor degraded but emitted some findings, the
    fallback should surface the partial-delivery tag explicitly."""
    report = build_fallback_report(
        audit_id="aud1",
        claims=_claims_with_metrics(n=1),
        findings=AuditFindings(
            findings=[_finding()],
            repo_summary="partial",
            coverage_notes=["code_auditor_partial_delivery_api_error"],
        ),
        validation=ValidationBatch(
            results=[],
            proactive=[],
            runtime_total_seconds=0.0,
        ),
        reason="reviewer_unavailable",
    )
    assert "Upstream degradation" in report.executive_summary
    assert "Code Auditor degraded (api_error)" in report.executive_summary


def test_fallback_surfaces_validator_partial_delivery():
    report = build_fallback_report(
        audit_id="aud1",
        claims=_claims_with_metrics(n=1),
        findings=AuditFindings(
            findings=[_finding()],
            repo_summary="ok",
        ),
        validation=ValidationBatch(
            results=[_confirmed("f1")],
            proactive=[],
            runtime_total_seconds=12.0,
            notes="validator_partial_delivery_timeout",
            unvalidated_finding_ids=["f2", "f3"],
        ),
        reason="reviewer_unavailable",
    )
    assert "Validator degraded (timeout)" in report.executive_summary


def test_fallback_critical_confirmed_not_reproducible():
    findings = AuditFindings(
        findings=[_finding("f1", Severity.CRITICAL)],
        repo_summary="r",
    )
    validation = ValidationBatch(
        results=[_confirmed("f1")],
        proactive=[],
        runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation
    )
    assert report.verdict == Verdict.NOT_REPRODUCIBLE
    assert report.confidence <= 0.4


def test_fallback_two_high_confirmed_not_reproducible():
    findings = AuditFindings(
        findings=[
            _finding("f1", Severity.HIGH),
            _finding("f2", Severity.HIGH),
        ],
        repo_summary="r",
    )
    validation = ValidationBatch(
        results=[_confirmed("f1"), _confirmed("f2")],
        proactive=[],
        runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation
    )
    assert report.verdict == Verdict.NOT_REPRODUCIBLE


def test_fallback_many_unvalidated_inconclusive():
    findings = AuditFindings(
        findings=[_finding(f"f{i}", Severity.MEDIUM) for i in range(6)],
        repo_summary="r",
    )
    validation = ValidationBatch(
        results=[],
        proactive=[],
        runtime_total_seconds=0.0,
        unvalidated_finding_ids=[f"f{i}" for i in range(6)],
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation
    )
    assert report.verdict == Verdict.INCONCLUSIVE


def test_fallback_no_findings_reproducible():
    findings = AuditFindings(findings=[], repo_summary="r")
    validation = ValidationBatch(
        results=[], proactive=[], runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation
    )
    assert report.verdict == Verdict.REPRODUCIBLE


def test_fallback_passes_through_all_findings():
    findings = AuditFindings(
        findings=[_finding(f"f{i}", Severity.LOW) for i in range(3)],
        repo_summary="r",
    )
    validation = ValidationBatch(
        results=[], proactive=[], runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation
    )
    assert len(report.findings) == 3


def test_fallback_confidence_capped():
    findings = AuditFindings(findings=[], repo_summary="r")
    validation = ValidationBatch(
        results=[], proactive=[], runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation
    )
    assert report.confidence <= 0.4


def test_fallback_claim_verifications_unchecked():
    findings = AuditFindings(findings=[], repo_summary="r")
    validation = ValidationBatch(
        results=[], proactive=[], runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(n=3), findings, validation
    )
    for cv in report.claim_verifications:
        assert cv.status == ClaimVerificationStatus.UNCHECKED
    # one per metric + 1 dataset + 1 architecture
    assert len(report.claim_verifications) == 3 + 1 + 1


def test_fallback_recommendations_rank_by_severity():
    findings = AuditFindings(
        findings=[
            _finding("low1", Severity.LOW),
            _finding("crit1", Severity.CRITICAL),
            _finding("med1", Severity.MEDIUM),
            _finding("high1", Severity.HIGH),
        ],
        repo_summary="r",
    )
    validation = ValidationBatch(
        results=[], proactive=[], runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation
    )
    # critical first, then high, medium, low
    assert report.recommendations[0].linked_finding_ids == ["crit1"]
    assert report.recommendations[1].linked_finding_ids == ["high1"]
    assert report.recommendations[2].linked_finding_ids == ["med1"]
    assert report.recommendations[3].linked_finding_ids == ["low1"]


def test_fallback_headline_mentions_fallback_and_reason():
    findings = AuditFindings(findings=[], repo_summary="r")
    validation = ValidationBatch(
        results=[], proactive=[], runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation,
        reason="timeout",
    )
    assert "Deterministic fallback" in report.headline
    assert "timeout" in report.headline


def test_fallback_severity_counts_populated():
    findings = AuditFindings(
        findings=[
            _finding("f1", Severity.CRITICAL),
            _finding("f2", Severity.HIGH),
            _finding("f3", Severity.HIGH),
            _finding("f4", Severity.LOW),
        ],
        repo_summary="r",
    )
    validation = ValidationBatch(
        results=[], proactive=[], runtime_total_seconds=0.0,
    )
    report = build_fallback_report(
        "aud", _claims_with_metrics(), findings, validation
    )
    assert report.severity_counts["critical"] == 1
    assert report.severity_counts["high"] == 2
    assert report.severity_counts["low"] == 1
