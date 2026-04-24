"""Deterministic, no-LLM fallback for the Reviewer phase.

When the LLM Reviewer times out or otherwise fails, the pipeline calls
``build_fallback_report`` to synthesize a minimal ``DiagnosticReport``
directly from the claims + findings + validation artifacts. Uses
straightforward rules — no model invocation, no API cost, no network.
Confidence is capped so the researcher knows not to over-rely on it.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from backend.schemas.claims import PaperClaims
from backend.schemas.findings import AuditFinding, AuditFindings, Severity
from backend.schemas.report import (
    ClaimVerification,
    ClaimVerificationStatus,
    DiagnosticReport,
    Recommendation,
    Verdict,
)
from backend.schemas.validation import ValidationBatch
from backend.util.time import utcnow_iso


_FALLBACK_CONFIDENCE_CAP = 0.4


def build_fallback_report(
    audit_id: str,
    claims: PaperClaims,
    findings: AuditFindings,
    validation: ValidationBatch,
    *,
    reason: str = "reviewer_unavailable",
) -> DiagnosticReport:
    """Synthesize a report with simple rules — no LLM.

    Rules:
      * Verdict: any confirmed critical → NOT_REPRODUCIBLE;
        2+ confirmed high → NOT_REPRODUCIBLE;
        1 confirmed high + several medium → QUESTIONABLE;
        only confirmed medium or below → LIKELY_REPRODUCIBLE;
        no verified claims + no findings above info → REPRODUCIBLE;
        many unvalidated → INCONCLUSIVE.
      * Findings: all Auditor findings pass through (no cross-check).
      * Claim verifications: UNCHECKED for every claim (no agent
        synthesis possible).
    """
    confirmed_by_severity = _count_confirmed_by_severity(findings, validation)
    verdict = _pick_verdict(confirmed_by_severity, findings, validation)
    severity_counts = _severity_counts(findings)
    claim_verifications = _unchecked_verifications(claims)
    recommendations = _top_recommendations(findings)

    return DiagnosticReport(
        audit_id=audit_id,
        generated_at=utcnow_iso(),
        verdict=verdict,
        confidence=_FALLBACK_CONFIDENCE_CAP,
        headline=(
            "Deterministic fallback — LLM Reviewer unavailable "
            f"(reason: {reason}). {len(findings.findings)} findings "
            "passed through from the Auditor without cross-check."
        )[:1000],
        executive_summary=_build_summary(
            findings, validation, confirmed_by_severity, reason
        ),
        claim_verifications=claim_verifications,
        findings=findings.findings,
        config_comparison=[],
        recommendations=recommendations,
        severity_counts=severity_counts,
        runtime_mode_used="managed_agents",
        runtime_ms_total=0,
    )


def _count_confirmed_by_severity(
    findings: AuditFindings, validation: ValidationBatch
) -> Counter:
    confirmed_ids = {
        r.finding_id for r in validation.results if r.verdict == "confirmed"
    }
    counter: Counter = Counter()
    for f in findings.findings:
        if f.id in confirmed_ids:
            counter[f.severity.value] += 1
    return counter


def _pick_verdict(
    confirmed: Counter,
    findings: AuditFindings,
    validation: ValidationBatch,
) -> Verdict:
    if confirmed[Severity.CRITICAL.value] >= 1:
        return Verdict.NOT_REPRODUCIBLE
    if confirmed[Severity.HIGH.value] >= 2:
        return Verdict.NOT_REPRODUCIBLE

    # Unvalidated > 5 with nothing confirmed → INCONCLUSIVE.
    unvalidated_count = len(validation.unvalidated_finding_ids)
    if not confirmed and unvalidated_count > 5:
        return Verdict.INCONCLUSIVE

    if confirmed[Severity.HIGH.value] == 1 and any(
        f.severity == Severity.MEDIUM for f in findings.findings
    ):
        return Verdict.QUESTIONABLE

    top_sev = _top_severity(findings)
    if top_sev in (Severity.MEDIUM, Severity.LOW):
        return Verdict.LIKELY_REPRODUCIBLE
    if top_sev is Severity.INFO or not findings.findings:
        return Verdict.REPRODUCIBLE

    # Unconfirmed critical / high findings present but nothing verified:
    # lean cautious.
    return Verdict.INCONCLUSIVE


def _top_severity(findings: AuditFindings) -> Optional[Severity]:
    order = [
        Severity.CRITICAL,
        Severity.HIGH,
        Severity.MEDIUM,
        Severity.LOW,
        Severity.INFO,
    ]
    present = {f.severity for f in findings.findings}
    for s in order:
        if s in present:
            return s
    return None


def _severity_counts(findings: AuditFindings) -> dict[str, int]:
    counts: Counter = Counter()
    for f in findings.findings:
        counts[f.severity.value] += 1
    return dict(counts)


def _unchecked_verifications(claims: PaperClaims) -> list[ClaimVerification]:
    out: list[ClaimVerification] = []
    for m in claims.metrics:
        out.append(
            ClaimVerification(
                claim_id=m.id,
                claim_summary=f"{m.metric_name or 'metric'} on {m.dataset or '?'}",
                status=ClaimVerificationStatus.UNCHECKED,
                notes="Unchecked — deterministic fallback did not cross-check.",
            )
        )
    for d in claims.datasets:
        out.append(
            ClaimVerification(
                claim_id=d.id,
                claim_summary=f"dataset: {d.name or d.id}",
                status=ClaimVerificationStatus.UNCHECKED,
            )
        )
    for a in claims.architectures:
        out.append(
            ClaimVerification(
                claim_id=a.id,
                claim_summary=f"architecture: {a.architecture or a.component or a.id}",
                status=ClaimVerificationStatus.UNCHECKED,
            )
        )
    return out


def _top_recommendations(findings: AuditFindings) -> list[Recommendation]:
    """Rank findings by severity and return top 5 as recommendations."""
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }
    sorted_findings = sorted(
        findings.findings, key=lambda f: severity_order.get(f.severity, 5)
    )
    out: list[Recommendation] = []
    for idx, f in enumerate(sorted_findings[:5], start=1):
        out.append(
            Recommendation(
                rank=idx,
                title=f.title,
                rationale=(f.description or "")[:600],
                linked_finding_ids=[f.id],
            )
        )
    return out


def _build_summary(
    findings: AuditFindings,
    validation: ValidationBatch,
    confirmed: Counter,
    reason: str,
) -> str:
    lines = [
        f"**Deterministic fallback report** (reason: `{reason}`).",
        "",
        (
            "The LLM-based Reviewer was unavailable, so this report was "
            "assembled by a rule-based synthesizer. Findings are passed "
            "through from the Code & Data Auditor without a second-opinion "
            "cross-check; claim verifications are marked UNCHECKED."
        ),
    ]

    # Upstream cascade — surface what each earlier agent actually
    # produced so the user can see where the signal was lost.
    cascade = _degradation_cascade(findings, validation)
    if cascade:
        lines.append("")
        lines.append("**Upstream degradation detected:**")
        for line in cascade:
            lines.append(f"- {line}")

    lines.append("")
    lines.append(f"**Findings:** {len(findings.findings)} total.")
    severity_counts = _severity_counts(findings)
    if severity_counts:
        parts = [f"{k}: {v}" for k, v in severity_counts.items()]
        lines.append(f"**By severity:** {', '.join(parts)}.")
    if sum(confirmed.values()):
        parts = [f"{k}: {v}" for k, v in confirmed.items() if v]
        lines.append(
            f"**Validator-confirmed:** {', '.join(parts)}."
        )
    if validation.unvalidated_finding_ids:
        lines.append(
            f"**Unvalidated findings:** "
            f"{len(validation.unvalidated_finding_ids)}."
        )
    lines.append("")

    if len(findings.findings) == 0:
        # Empty report — explain what likely went wrong instead of
        # silently shrugging. This is the scenario where the user
        # spent money and got nothing; they deserve actionable context.
        lines.append(
            "**Why this report is empty:** no findings survived the "
            "Code Auditor phase (schema drift or partial-delivery "
            "recovery produced an empty batch), and the Validator's "
            "proactive checks did not surface new findings either. "
            "Common causes: repo cloned but agent hit its turn or "
            "time budget before emitting a complete findings JSON; "
            "persistent JSON schema violations the repair pass could "
            "not fix; or all transient network drops stacked on one "
            "run. Re-run with a fresh audit ID — individual agents "
            "rarely repeat the same failure pattern."
        )
    else:
        lines.append(
            "Re-run with a working Reviewer agent to get claim-by-claim "
            "verification and a proper verdict confidence."
        )
    return "\n".join(lines)


def _degradation_cascade(
    findings: AuditFindings, validation: ValidationBatch
) -> list[str]:
    """Scan artifacts for partial-delivery markers and summarize."""
    out: list[str] = []
    for note in findings.coverage_notes:
        if "code_auditor_partial_delivery_" in note:
            reason = note.split("code_auditor_partial_delivery_", 1)[1]
            out.append(
                f"Code Auditor degraded ({reason}); "
                f"{len(findings.findings)} finding(s) recovered from "
                "mid-stream messages, not a complete batch."
            )
            break
    if "validator_partial_delivery_" in (validation.notes or ""):
        tag = validation.notes.split(
            "validator_partial_delivery_", 1
        )[1].split(";")[0]
        out.append(
            f"Validator degraded ({tag}); "
            f"{len(validation.results)} partial result(s), "
            f"{len(validation.unvalidated_finding_ids)} unvalidated."
        )
    elif len(validation.results) == 0 and validation.notes:
        # Validator empty-batch path (full failure, no salvage).
        out.append(f"Validator produced no results: {validation.notes}.")
    return out


def _top_finding_severity_count(
    findings: AuditFindings, severity: Severity
) -> int:
    return sum(1 for f in findings.findings if f.severity == severity)


__all__ = ["build_fallback_report"]


# Keep a couple of helpers in the explicit API for testing ergonomics.
def only_finding_severity(
    findings: list[AuditFinding], severity: Severity
) -> list[AuditFinding]:
    return [f for f in findings if f.severity == severity]
