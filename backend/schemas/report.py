from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import Field, field_validator

from .common import Lenient
from .findings import AuditFinding, DataEDA


class Verdict(str, Enum):
    REPRODUCIBLE = "reproducible"
    LIKELY_REPRODUCIBLE = "likely_reproducible"
    QUESTIONABLE = "questionable"
    NOT_REPRODUCIBLE = "not_reproducible"
    INCONCLUSIVE = "inconclusive"


class ClaimVerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partial"
    NOT_VERIFIED = "not_verified"
    UNCHECKED = "unchecked"


class ClaimVerification(Lenient):
    claim_id: str
    claim_summary: Optional[str] = None
    status: ClaimVerificationStatus = ClaimVerificationStatus.UNCHECKED
    code_location: Optional[str] = None
    notes: Optional[str] = None
    linked_finding_ids: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v):
        # Reviewer agents emit natural statuses like "reproduced",
        # "reproduced_with_caveat", "not_reproduced", "unreproducible"
        # that aren't in the 4-value enum. Map them so a single drifty
        # status doesn't reject the whole report and force the
        # deterministic fallback. Same pattern as the validator
        # verdict coercer.
        #
        # Falling through to UNCHECKED when the status is unrecognized
        # is DELIBERATE but dangerous: a reviewer who says "not
        # reproducible" and gets mapped to "unchecked" silently loses
        # the verdict. Keep the synonym sets broad.
        if isinstance(v, ClaimVerificationStatus):
            return v
        if isinstance(v, str):
            lowered = v.strip().lower()
            for member in ClaimVerificationStatus:
                if member.value == lowered:
                    return lowered
            if lowered in {
                "reproduced", "reproduced_exactly", "matches",
                "verified", "confirmed", "match", "passed",
                "reproducible",
            }:
                return ClaimVerificationStatus.VERIFIED.value
            if lowered in {
                "reproduced_with_caveat", "partial_match",
                "partially_reproduced", "partial", "approximate",
                # "partially_reproducible" is the reviewer's natural
                # form for the partial-success case; without it the
                # status silently defaults to UNCHECKED and the
                # claim looks un-evaluated in the UI.
                "partially_reproducible", "partly_reproducible",
                "caveat",
            }:
                return ClaimVerificationStatus.PARTIALLY_VERIFIED.value
            if lowered in {
                "not_reproduced", "mismatch", "contradicted",
                "refuted", "failed", "no_match",
                # "unreproducible" and "not_reproducible" are the
                # reviewer's natural forms mirroring the Verdict enum;
                # without these, every "unreproducible" claim
                # verification looked "unchecked" in the saved report.
                "unreproducible", "not_reproducible",
                "non_reproducible", "irreproducible",
            }:
                return ClaimVerificationStatus.NOT_VERIFIED.value
            return ClaimVerificationStatus.UNCHECKED.value
        return v


class ConfigDiscrepancy(Lenient):
    parameter: str
    paper_value: Optional[str] = None
    code_value: Optional[str] = None
    code_location: Optional[str] = None
    # Agents sometimes omit ``match`` / ``severity`` when they emit
    # only observations. Defaults match the conservative reading:
    # ``match=False`` (a discrepancy is implied by this row even
    # existing), ``severity="info"`` (so a missing severity never
    # drives the verdict up).
    match: bool = False
    severity: Literal["critical", "high", "medium", "low", "info"] = "info"

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v):
        valid = {"critical", "high", "medium", "low", "info"}
        if v is None:
            return "info"
        if isinstance(v, str):
            lowered = v.strip().lower()
            if lowered in valid:
                return lowered
            if lowered in {"warn", "warning"}:
                return "medium"
            if lowered in {"urgent", "blocker"}:
                return "critical"
            return "info"
        return "info"

    @field_validator(
        "parameter", "paper_value", "code_value", "code_location",
        mode="before",
    )
    @classmethod
    def _stringify_values(cls, v):
        # Agents emit numeric paper/code values (``paper_value: 1.92``,
        # ``code_value: 32``) because these fields hold config values
        # of any type in reality. Schema keeps them as strings for
        # downstream text formatting, so stringify here rather than
        # rejecting the whole config_comparison row.
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, (list, dict)):
            import json as _json
            try:
                return _json.dumps(v)
            except (TypeError, ValueError):
                return str(v)
        return str(v)


class Recommendation(Lenient):
    rank: int
    title: str
    rationale: str
    linked_finding_ids: list[str] = Field(default_factory=list)


class Disagreement(Lenient):
    finding_id: str
    auditor_verdict: str
    validator_verdict: str
    reviewer_resolution: str
    # Default True: if the Reviewer wrote a disagreement entry at all,
    # it's meant to be surfaced in the report. Agents routinely omit
    # this flag because it's a UI-level concern, not a content one.
    exposed_in_report: bool = True

    @field_validator(
        "auditor_verdict", "validator_verdict", "reviewer_resolution",
        mode="before",
    )
    @classmethod
    def _coerce_verdict_text(cls, v):
        # Agents emit nested position dicts (``{"claim": ...,
        # "evidence": ..., "confidence": 0.9}``) instead of a flat
        # verdict string. Extract the ``claim`` if present, or JSON-
        # serialize the whole structure, so one rich disagreement
        # doesn't reject the batch.
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            claim = v.get("claim") or v.get("verdict") or v.get("summary")
            if claim:
                return str(claim)
            import json as _json
            try:
                return _json.dumps(v)
            except (TypeError, ValueError):
                return str(v)
        return str(v)


class DiagnosticReport(Lenient):
    audit_id: str
    generated_at: str
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    headline: str = Field(max_length=1000)
    executive_summary: str = Field(max_length=10_000)

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v):
        if isinstance(v, Verdict):
            return v
        if isinstance(v, str):
            # Case-insensitive match against enum values — agents
            # sometimes emit "INCONCLUSIVE" or "Not_Reproducible".
            lowered = v.strip().lower()
            for member in Verdict:
                if member.value == lowered:
                    return member.value
            return Verdict.INCONCLUSIVE.value
        return v

    @field_validator("headline", mode="before")
    @classmethod
    def _truncate_headline(cls, v):
        if isinstance(v, str) and len(v) > 1000:
            return v[:1000]
        return v

    @field_validator("executive_summary", mode="before")
    @classmethod
    def _truncate_summary(cls, v):
        if isinstance(v, str) and len(v) > 10_000:
            return v[:10_000]
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v):
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            if v < 0:
                return 0.0
            if v > 1:
                return 1.0
        return v
    claim_verifications: list[ClaimVerification] = Field(default_factory=list)
    findings: list[AuditFinding] = Field(default_factory=list)
    config_comparison: list[ConfigDiscrepancy] = Field(default_factory=list)
    eda_summary: Optional[DataEDA] = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    unresolved_disagreements: list[Disagreement] = Field(default_factory=list)
    severity_counts: dict[str, Any] = Field(default_factory=dict)
    # Pipeline stamps these after parse; default values let the model
    # validate even when the agent (reasonably) omits them.
    runtime_mode_used: Literal["managed_agents", "messages_api"] = "managed_agents"
    runtime_ms_total: int = 0
    cost_usd_estimate: Optional[float] = None
