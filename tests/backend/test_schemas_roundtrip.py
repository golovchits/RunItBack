"""Roundtrip every top-level schema through JSON and back.

Each test builds a minimal valid instance, serializes it via
`model_dump_json()`, parses it back via `model_validate_json()`, and
asserts equality. Catches typos in Literal values, discriminator keys,
forward-reference drift, and extra='forbid' regressions.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.schemas.claims import (
    AblationClaim,
    ArchitectureClaim,
    Citation,
    DatasetClaim,
    DatasetSplitSpec,
    EvaluationProtocolClaim,
    MetricClaim,
    PaperClaims,
    PaperRedFlag,
    TrainingConfigClaim,
)
from backend.schemas.common import CodeSpan, Evidence
from backend.schemas.events import (
    EvtAgentFileOpened,
    EvtAgentFinished,
    EvtAgentMessage,
    EvtAgentStarted,
    EvtAgentThinking,
    EvtAgentToolResult,
    EvtAgentToolUse,
    EvtAuditError,
    EvtAuditStatus,
    EvtClaimsExtracted,
    EvtFallbackTriggered,
    EvtFindingEmitted,
    EvtReportChunk,
    EvtReportFinal,
    EvtValidationCompleted,
    SSEEvent,
)
from backend.schemas.findings import (
    AuditFinding,
    AuditFindings,
    DataEDA,
    DetectorRole,
    FindingCategory,
    Severity,
    TargetedCheckRequest,
)
from backend.schemas.inputs import (
    AuditRecord,
    AuditRequest,
    CodeSource,
    CodeSourceGit,
    CodeSourceLocal,
    DataSource,
    DataSourceBundled,
    DataSourceLocal,
    DataSourceSkip,
    DataSourceUrl,
    PaperSource,
    PaperSourceArxiv,
    PaperSourceNone,
    PaperSourcePdfUrl,
    PaperSourceRawText,
    PaperSourceUpload,
)
from backend.schemas.report import (
    ClaimVerification,
    ClaimVerificationStatus,
    ConfigDiscrepancy,
    DiagnosticReport,
    Disagreement,
    Recommendation,
    Verdict,
)
from backend.schemas.validation import (
    ProactiveCheck,
    ValidationBatch,
    ValidationResult,
)


def _roundtrip(instance):
    cls = type(instance)
    raw = instance.model_dump_json()
    parsed = cls.model_validate_json(raw)
    assert parsed == instance, f"{cls.__name__} roundtrip drift"
    return parsed


def _cite() -> Citation:
    return Citation(page=1, section="Intro", quote="hello")


# ---- common ----


def test_code_span_roundtrip():
    _roundtrip(
        CodeSpan(
            file_path="src/a.py",
            line_start=1,
            line_end=10,
            snippet="pass",
        )
    )


def test_evidence_roundtrip():
    _roundtrip(Evidence(kind="grep", description="d", raw="r"))


# ---- claims ----


def test_citation_roundtrip():
    _roundtrip(_cite())


def test_metric_claim_roundtrip():
    _roundtrip(
        MetricClaim(
            id="claim_metrics_001",
            metric_name="accuracy",
            value=96.97,
            dataset="TRIDENT",
            citation=_cite(),
        )
    )


def test_dataset_claim_roundtrip():
    _roundtrip(
        DatasetClaim(
            id="claim_datasets_001",
            name="TRIDENT",
            modality=["image"],
            splits=[DatasetSplitSpec(name="train", num_samples=100)],
            citation=_cite(),
        )
    )


def test_architecture_claim_roundtrip():
    _roundtrip(
        ArchitectureClaim(
            id="claim_archs_001",
            component="backbone",
            architecture="VGG-19",
            citation=_cite(),
        )
    )


def test_training_config_claim_roundtrip():
    _roundtrip(
        TrainingConfigClaim(
            id="claim_tc_001",
            optimizer="Adam",
            learning_rate=1e-3,
            batch_size=32,
            citation=_cite(),
        )
    )


def test_evaluation_protocol_claim_roundtrip():
    _roundtrip(
        EvaluationProtocolClaim(
            id="claim_ep_001",
            metrics=["accuracy"],
            split="test",
            citation=_cite(),
        )
    )


def test_ablation_claim_roundtrip():
    _roundtrip(
        AblationClaim(
            id="claim_abl_001",
            description="with vs without fusion",
            citation=_cite(),
        )
    )


def test_paper_red_flag_roundtrip():
    _roundtrip(
        PaperRedFlag(
            category="ambiguous_protocol",
            description="unclear",
            citation=_cite(),
        )
    )


def test_paper_claims_roundtrip():
    _roundtrip(
        PaperClaims(
            paper_title="T",
            authors=["A"],
            abstract_summary="short",
            metrics=[
                MetricClaim(
                    id="m1",
                    metric_name="acc",
                    value=99.0,
                    dataset="D",
                    citation=_cite(),
                )
            ],
            datasets=[
                DatasetClaim(
                    id="d1",
                    name="D",
                    modality=["tabular"],
                    citation=_cite(),
                )
            ],
            architectures=[
                ArchitectureClaim(
                    id="a1",
                    component="head",
                    architecture="MLP",
                    citation=_cite(),
                )
            ],
            training_config=[TrainingConfigClaim(id="t1", citation=_cite())],
            evaluation_protocol=[
                EvaluationProtocolClaim(
                    id="e1",
                    metrics=["acc"],
                    split="test",
                    citation=_cite(),
                )
            ],
            extraction_confidence=0.8,
        )
    )


# ---- findings ----


def _finding(det: DetectorRole = DetectorRole.AUDITOR) -> AuditFinding:
    return AuditFinding(
        id="f_001",
        category=FindingCategory.DATA_LEAKAGE_PREPROCESSING,
        severity=Severity.CRITICAL,
        title="leak",
        description="d",
        confidence=0.9,
        detector=det,
    )


def test_data_eda_roundtrip():
    _roundtrip(DataEDA(splits_observed={"train": 100, "test": 20}))


def test_data_eda_coerces_list_splits_observed():
    """Agents sometimes emit splits_observed as a list of names —
    coerce to dict[name, 0] so the EDA block still validates."""
    eda = DataEDA.model_validate({
        "splits_observed": ["Train", "Validation", "Test"],
    })
    assert set(eda.splits_observed.keys()) == {
        "Train", "Validation", "Test",
    }


def test_data_eda_defaults_missing_splits_observed():
    """splits_observed is optional-with-default now; missing key is OK."""
    eda = DataEDA.model_validate({})
    assert eda.splits_observed == {}


def test_audit_findings_accepts_missing_repo_summary_via_normalizer():
    """Integration check: normalize_audit_findings + schema defaults
    let a minimal findings dict validate."""
    from backend.agents.output_parsers import normalize_audit_findings
    obj = normalize_audit_findings({"findings": []})
    AuditFindings.model_validate(obj)


def test_audit_finding_roundtrip():
    _roundtrip(_finding())


def test_targeted_check_request_roundtrip():
    _roundtrip(
        TargetedCheckRequest(
            finding_id="f_001",
            hypothesis="h",
            proposed_check="python -c 'pass'",
            priority="high",
        )
    )


def test_audit_findings_roundtrip():
    _roundtrip(
        AuditFindings(
            findings=[_finding()],
            repo_summary="r",
            eda=DataEDA(splits_observed={"train": 1}),
            targeted_check_requests=[
                TargetedCheckRequest(
                    finding_id="f_001",
                    hypothesis="h",
                    proposed_check="c",
                    priority="medium",
                )
            ],
        )
    )


def test_finding_category_includes_flag_swapped():
    # guard against accidental regression of the enum addition documented
    # in the commit that introduced §5.2 PREPROC_FLAG_SWAPPED
    assert FindingCategory.PREPROC_FLAG_SWAPPED.value == "preprocessing.flag_swapped"


# ---- validation ----


def test_validation_result_roundtrip():
    _roundtrip(
        ValidationResult(
            id="v_001",
            finding_id="f_001",
            verdict="confirmed",
            method="m",
            confidence=0.95,
        )
    )


def test_proactive_check_roundtrip():
    _roundtrip(
        ProactiveCheck(
            slug="pip_resolve",
            result=ValidationResult(
                id="v_002",
                finding_id="proactive.pip_resolve",
                verdict="confirmed",
                method="uv dry-run",
                confidence=0.9,
            ),
        )
    )


def test_validation_batch_roundtrip():
    _roundtrip(
        ValidationBatch(
            results=[],
            proactive=[],
            runtime_total_seconds=1.23,
            new_findings=[_finding(DetectorRole.VALIDATOR)],
        )
    )


# ---- report ----


def test_claim_verification_roundtrip():
    _roundtrip(
        ClaimVerification(
            claim_id="c1",
            claim_summary="s",
            status=ClaimVerificationStatus.VERIFIED,
        )
    )


def test_config_discrepancy_roundtrip():
    _roundtrip(
        ConfigDiscrepancy(
            parameter="lr",
            paper_value="1e-3",
            code_value="1e-4",
            match=False,
            severity="high",
        )
    )


def test_recommendation_roundtrip():
    _roundtrip(
        Recommendation(
            rank=1,
            title="fix X",
            rationale="because Y",
        )
    )


def test_disagreement_roundtrip():
    _roundtrip(
        Disagreement(
            finding_id="f_001",
            auditor_verdict="confirmed",
            validator_verdict="denied",
            reviewer_resolution="keep",
            exposed_in_report=True,
        )
    )


def test_diagnostic_report_roundtrip():
    _roundtrip(
        DiagnosticReport(
            audit_id="a1",
            generated_at="2026-04-22T14:00:00Z",
            verdict=Verdict.QUESTIONABLE,
            confidence=0.7,
            headline="h",
            executive_summary="e",
            claim_verifications=[],
            findings=[],
            config_comparison=[],
            recommendations=[],
            runtime_mode_used="managed_agents",
            runtime_ms_total=1000,
        )
    )


# ---- inputs (discriminated unions) ----


def test_paper_source_variants_roundtrip():
    ta = TypeAdapter(PaperSource)
    for inst in (
        PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
        PaperSourcePdfUrl(url="https://example.com/p.pdf"),
        PaperSourceUpload(upload_id="pdf_1"),
        PaperSourceRawText(text="x" * 600, title_hint="T"),
        PaperSourceNone(),
        PaperSourceNone(title_hint="My repo audit"),
    ):
        assert ta.validate_json(ta.dump_json(inst)) == inst


def test_code_source_variants_roundtrip():
    ta = TypeAdapter(CodeSource)
    for inst in (
        CodeSourceGit(url="https://github.com/a/b", ref="main"),
        CodeSourceLocal(path="/abs/path"),
    ):
        assert ta.validate_json(ta.dump_json(inst)) == inst


def test_data_source_variants_roundtrip():
    ta = TypeAdapter(DataSource)
    for inst in (
        DataSourceLocal(path="/abs/d"),
        DataSourceUrl(url="https://example.com/d.tar.gz"),
        DataSourceBundled(subpath="data/"),
        DataSourceSkip(),
    ):
        assert ta.validate_json(ta.dump_json(inst)) == inst


def test_audit_request_roundtrip():
    _roundtrip(
        AuditRequest(
            paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
        )
    )


def test_audit_request_with_user_notes_roundtrip():
    _roundtrip(
        AuditRequest(
            paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            user_notes="I suspect the train/test split overlaps.",
        )
    )


def test_audit_request_with_data_structure_text_roundtrip():
    tree = (
        "dataset/\n"
        "├── train/\n"
        "│   ├── class_a/ (2000 files)\n"
        "│   └── class_b/ (1800 files)\n"
        "└── val/\n"
        "    ├── class_a/ (200 files)\n"
        "    └── class_b/ (180 files)\n"
    )
    _roundtrip(
        AuditRequest(
            paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            data_structure_text=tree,
        )
    )


def test_audit_request_defaults_timeout_to_45_min():
    req = AuditRequest(
        paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    assert req.timeout_minutes == 45


def test_audit_request_accepts_120_min_max():
    req = AuditRequest(
        paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
        timeout_minutes=120,
    )
    assert req.timeout_minutes == 120


def test_audit_request_rejects_timeout_over_120():
    import pytest as _pytest
    from pydantic import ValidationError
    with _pytest.raises(ValidationError):
        AuditRequest(
            paper=PaperSourceArxiv(
                arxiv_url="https://arxiv.org/abs/2504.01848"
            ),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            timeout_minutes=150,
        )


def test_audit_request_rejects_oversized_data_structure_text():
    import pytest as _pytest
    from pydantic import ValidationError
    with _pytest.raises(ValidationError):
        AuditRequest(
            paper=PaperSourceArxiv(
                arxiv_url="https://arxiv.org/abs/2504.01848"
            ),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
            data_structure_text="x" * 200_001,
        )


def test_audit_record_roundtrip():
    _roundtrip(
        AuditRecord(
            id="a1",
            request=AuditRequest(
                paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
                code=CodeSourceGit(url="https://github.com/a/b"),
                data=DataSourceSkip(),
            ),
            created_at="2026-04-22T14:00:00Z",
            phase="created",
            runtime_mode="managed_agents",
        )
    )


# ---- events ----


def _base_fields() -> dict:
    return {"audit_id": "a1", "seq": 1, "ts": "2026-04-22T14:00:00Z"}


def _all_events() -> list:
    return [
        EvtAuditStatus(**_base_fields(), phase="normalizing"),
        EvtAgentStarted(
            **_base_fields(),
            agent="paper_analyst",
            session_id="s1",
            runtime_mode="managed_agents",
        ),
        EvtAgentThinking(**_base_fields(), agent="paper_analyst", delta="..."),
        EvtAgentMessage(
            **_base_fields(), agent="paper_analyst", text="t", is_final=False
        ),
        EvtAgentToolUse(
            **_base_fields(),
            agent="paper_analyst",
            tool="grep",
            input_summary="grep hello",
        ),
        EvtAgentToolResult(
            **_base_fields(),
            agent="paper_analyst",
            tool="grep",
            success=True,
            output_excerpt="out",
        ),
        EvtAgentFileOpened(
            **_base_fields(),
            agent="code_auditor",
            file_path="src/a.py",
            line_start=1,
            line_end=10,
        ),
        EvtFindingEmitted(
            **_base_fields(), agent="code_auditor", finding=_finding()
        ),
        EvtValidationCompleted(
            **_base_fields(),
            result=ValidationResult(
                id="v1",
                finding_id="f1",
                verdict="confirmed",
                method="m",
                confidence=0.9,
            ),
        ),
        EvtClaimsExtracted(
            **_base_fields(),
            claims=PaperClaims(
                paper_title="T",
                authors=["A"],
                abstract_summary="s",
                metrics=[],
                datasets=[],
                architectures=[],
                training_config=[],
                evaluation_protocol=[],
                extraction_confidence=0.5,
            ),
        ),
        EvtAgentFinished(**_base_fields(), agent="reviewer", duration_ms=1000),
        EvtReportChunk(**_base_fields(), delta={"a": "b"}),
        EvtReportFinal(
            **_base_fields(),
            report=DiagnosticReport(
                audit_id="a1",
                generated_at="t",
                verdict=Verdict.INCONCLUSIVE,
                confidence=0.5,
                headline="h",
                executive_summary="e",
                claim_verifications=[],
                findings=[],
                config_comparison=[],
                recommendations=[],
                runtime_mode_used="managed_agents",
                runtime_ms_total=1,
            ),
        ),
        EvtAuditError(
            **_base_fields(),
            error_type="timeout",
            message="m",
            recoverable=True,
        ),
        EvtFallbackTriggered(
            **_base_fields(), reason="r", target_mode="messages_api"
        ),
    ]


def test_all_events_direct_roundtrip():
    for ev in _all_events():
        _roundtrip(ev)


def test_all_events_through_sseevent_union():
    ta = TypeAdapter(SSEEvent)
    for ev in _all_events():
        assert ta.validate_json(ta.dump_json(ev)) == ev, (
            f"{type(ev).__name__} failed via SSEEvent union"
        )


# ---- extra='forbid' guards ----


def test_citation_ignores_unknown_fields():
    # Claim schemas are lenient (extra="ignore") so real-world LLM
    # output with extra semantic annotations doesn't fail validation.
    c = Citation.model_validate({"quote": "q", "unknown_field": "x"})
    assert c.quote == "q"


def test_metric_claim_accepts_unusual_unit_and_split():
    # Agents produce units like "nats_per_token" and splits beyond the
    # train/val/test triad; schema must not reject them.
    m = MetricClaim.model_validate({
        "id": "m1",
        "metric_name": "val_loss",
        "value": 2.85,
        "unit": "nats_per_token",
        "dataset": "OpenWebText",
        "split": "validation",
        "citation": {"quote": "q"},
    })
    assert m.unit == "nats_per_token"
    assert m.split == "validation"


def test_dataset_claim_coerces_string_modality_to_list():
    d = DatasetClaim.model_validate({
        "id": "d1",
        "name": "OWT",
        "modality": "text (character-level)",
        "citation": {"quote": "q"},
    })
    assert d.modality == ["text (character-level)"]


def test_dataset_claim_coerces_bare_string_splits_to_specs():
    """Agents often emit splits as a list of bare names; coerce to
    DatasetSplitSpec objects so validation still passes."""
    d = DatasetClaim.model_validate({
        "id": "d1",
        "name": "OWT",
        "splits": ["train", "val", "test"],
    })
    assert [s.name for s in d.splits] == ["train", "val", "test"]
    assert all(s.num_samples is None for s in d.splits)


def test_dataset_claim_coerces_dict_splits_to_specs():
    """Agents occasionally emit splits as a dict keyed by split name."""
    d = DatasetClaim.model_validate({
        "id": "d1",
        "name": "CIFAR10",
        "splits": {
            "train": {"num_samples": 50000, "num_classes": 10},
            "test": 10000,
            "val": "unused",
        },
    })
    by_name = {s.name: s for s in d.splits}
    assert by_name["train"].num_samples == 50000
    assert by_name["train"].num_classes == 10
    assert by_name["test"].num_samples == 10000
    assert by_name["val"].name == "val"  # non-dict/int → name-only spec


def test_dataset_claim_keeps_objects_as_is():
    d = DatasetClaim.model_validate({
        "id": "d1",
        "splits": [{"name": "train", "num_samples": 100}],
    })
    assert d.splits[0].name == "train"
    assert d.splits[0].num_samples == 100


def test_config_discrepancy_defaults_severity_to_info():
    """Reviewer sometimes emits ConfigDiscrepancy rows without severity
    (e.g. observations-only). Schema must accept and default."""
    c = ConfigDiscrepancy.model_validate({
        "parameter": "optimizer",
        "paper_value": "AdamW",
        "code_value": "Adam",
    })
    assert c.severity == "info"
    assert c.match is False


def test_config_discrepancy_explicit_values_preserved():
    c = ConfigDiscrepancy.model_validate({
        "parameter": "lr",
        "paper_value": "1e-4",
        "code_value": "1e-3",
        "match": False,
        "severity": "high",
    })
    assert c.severity == "high"


def test_audit_finding_ignores_unknown_fields():
    # Agent-output schemas are lenient so novel fields don't reject a
    # whole batch of otherwise-valid findings.
    f = AuditFinding.model_validate(
        {
            "id": "f1",
            "category": "data_leakage.preprocessing",
            "severity": "critical",
            "title": "t",
            "description": "d",
            "confidence": 0.9,
            "detector": "auditor",
            "novel_field": "ignored",
        }
    )
    assert f.id == "f1"


def test_audit_finding_coerces_unknown_category_to_other():
    f = AuditFinding.model_validate(
        {
            "id": "f2",
            "category": "some.made.up.category",
            "severity": "high",
            "title": "t",
            "description": "d",
            "confidence": 0.5,
            "detector": "auditor",
        }
    )
    assert f.category == FindingCategory.OTHER


def test_diagnostic_report_coerces_unknown_verdict_to_inconclusive():
    r = DiagnosticReport.model_validate(
        {
            "audit_id": "a",
            "generated_at": "t",
            "verdict": "not_a_real_verdict",
            "confidence": 0.5,
            "headline": "h",
            "executive_summary": "",
            "claim_verifications": [],
            "findings": [],
            "config_comparison": [],
            "recommendations": [],
            "runtime_mode_used": "managed_agents",
            "runtime_ms_total": 1,
        }
    )
    assert r.verdict == Verdict.INCONCLUSIVE


def test_diagnostic_report_accepts_uppercase_verdict_case_insensitive():
    """Agents occasionally emit SCREAMING_SNAKE — don't reject, coerce."""
    r = DiagnosticReport.model_validate(
        {
            "audit_id": "a",
            "generated_at": "t",
            "verdict": "INCONCLUSIVE",
            "confidence": 0.5,
            "headline": "h",
            "executive_summary": "",
            "claim_verifications": [],
            "findings": [],
            "config_comparison": [],
            "recommendations": [],
            "runtime_mode_used": "managed_agents",
            "runtime_ms_total": 1,
        }
    )
    assert r.verdict == Verdict.INCONCLUSIVE


def test_diagnostic_report_accepts_mixed_case_verdict():
    r = DiagnosticReport.model_validate(
        {
            "audit_id": "a",
            "generated_at": "t",
            "verdict": "Not_Reproducible",
            "confidence": 0.5,
            "headline": "h",
            "executive_summary": "",
            "claim_verifications": [],
            "findings": [],
            "config_comparison": [],
            "recommendations": [],
            "runtime_mode_used": "managed_agents",
            "runtime_ms_total": 1,
        }
    )
    assert r.verdict == Verdict.NOT_REPRODUCIBLE
