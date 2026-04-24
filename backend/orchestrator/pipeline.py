from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import anthropic
import httpx

from backend.agents.output_parsers import (
    normalize_audit_findings,
    normalize_paper_claims,
    normalize_reviewer_report,
    normalize_validation_batch,
    normalize_validation_batch_drop_new_findings,
    parse_json_output,
)
from backend.agents.runner import AgentRunner
from backend.config import Settings
from backend.errors import (
    InputError,
    NonRecoverableAPIError,
    TurnLimitExceeded,
    UnavailableError,
    ValidationFailedError,
)
from backend.orchestrator.event_bus import EventBus
from backend.orchestrator.normalizer import NormalizedPaths, Normalizer
from backend.orchestrator.repo_manifest import RepoManifest, build_manifest
from backend.orchestrator.reviewer_checks import build_fallback_report
from backend.orchestrator.store import AuditStore
from backend.orchestrator.user_messages import (
    build_code_auditor_content,
    build_paper_analyst_content,
    build_readme_analyst_content,
    build_reviewer_content,
    build_validator_content,
)
from backend.schemas.claims import PaperClaims
from backend.schemas.events import (
    EvtAuditError,
    EvtAuditStatus,
    EvtClaimsExtracted,
    EvtFindingEmitted,
    EvtReportFinal,
    EvtValidationCompleted,
)
from backend.schemas.findings import AuditFindings
from backend.schemas.inputs import (
    AuditRecord,
    DataSourceLocal,
    PaperSourceNone,
)
from backend.schemas.report import DiagnosticReport
from backend.schemas.validation import ValidationBatch
from backend.util.time import utcnow_iso

_log = logging.getLogger(__name__)

_TIMEOUT_FRACTIONS = {
    # Bumped 1/8 → 1/5. A 20-page ML paper with tables + appendix can
    # need 2-4 min of Opus inference time; 1/8 of 25 min (≈188 s) was
    # tight enough to time out on mid-length papers. 1/5 = 300 s.
    "paper_analyst": 1 / 5,
    "code_auditor": 2 / 5,
    # Validator gets the largest slice: pip_resolve + import_smoke +
    # eval_dry_run + per-finding checks on real repos regularly exceed
    # what Code Auditor (a pure read pass) needs. Partial-delivery
    # recovery covers anything that still overruns.
    "validator": 1 / 2,
    "reviewer": 1 / 6,
}

_MAX_TURNS = {
    "paper_analyst": 20,
    # Bumped 80 → 100. With normalize_audit_findings accepting more
    # drift, the Auditor can iterate longer without being shut down
    # for a schema mistake at the tail end.
    "code_auditor": 100,
    # Bumped 60 → 100. The proactive battery (pip_resolve,
    # import_smoke, eval_dry_run, seed_reproducibility,
    # config_argparse_parse, checkpoint_load_smoke) plus per-finding
    # checks regularly needs 70+ turns on real repos. Turn-limit
    # recovery still catches runaway loops; 100 is a circuit breaker,
    # not a target.
    "validator": 100,
    "reviewer": 30,
}

# README-as-paper fallback for code-only audits. The threshold and
# confidence cap are load-bearing for diagnostic integrity — a README
# is weaker evidence than a formal paper, and the verdict rubric must
# not over-trust README-derived claims.
_README_MIN_CHARS = 500
_README_CONFIDENCE_CAP = 0.5

# Claude Opus 4.x public rates (USD per 1M tokens). Used to compute
# the cost_usd_estimate stamped on the final DiagnosticReport. The
# number is an estimate — we sum all input tokens (including cache
# read / creation) at the fresh-input rate, which slightly
# over-estimates actual cost for cache-heavy workloads. That
# conservatism is intentional: we'd rather surface a safely-high
# number than under-report spend.
_COST_PER_M_INPUT_USD = 15.0
_COST_PER_M_OUTPUT_USD = 75.0

# Per-phase "degrade instead of kill" failure classes. Covers:
#   - our own TimeoutError / TurnLimitExceeded (budget exhaustion)
#   - ValidationFailedError (schema drift the repair pass couldn't fix)
#   - NonRecoverableAPIError (session.status_terminated)
#   - UnavailableError (Managed Agents not configured)
#   - anthropic.APIConnectionError (network drop mid-stream — surfaces
#     as "peer closed connection without sending complete message body")
#   - anthropic.APITimeoutError (HTTP timeout, distinct from our wait_for)
#   - anthropic.InternalServerError / RateLimitError (transient 5xx / 429)
#   - httpx.HTTPError fallback for cases where the SDK lets a raw
#     transport error leak through.
# AuthenticationError, BadRequestError, PermissionDeniedError stay
# fatal — they mean the whole config is wrong and retrying won't help.
_DEGRADABLE_ERRORS: tuple[type[BaseException], ...] = (
    TimeoutError,
    TurnLimitExceeded,
    ValidationFailedError,
    NonRecoverableAPIError,
    UnavailableError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
    anthropic.RateLimitError,
    httpx.HTTPError,
)


class AuditPipeline:
    """Four-agent audit orchestrator for a single ``AuditRecord``."""

    def __init__(
        self,
        audit: AuditRecord,
        store: AuditStore,
        bus: EventBus,
        runner: AgentRunner,
        normalizer: Normalizer,
        settings: Settings,
    ) -> None:
        self.audit = audit
        self.store = store
        self.bus = bus
        self.runner = runner
        self.normalizer = normalizer
        self.settings = settings
        self._seq = 0
        self._start_ns = 0
        self._paths: Optional[NormalizedPaths] = None
        self._manifest: Optional[RepoManifest] = None
        # Per-agent token totals, populated by intercepting
        # EvtAgentFinished via ``self.publish``. Summed into a USD
        # cost estimate and stamped on the final DiagnosticReport.
        self._token_totals: dict[str, dict[str, int]] = {}

    # ---- event plumbing ----

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def emit(self, cls: type, **kwargs: Any):
        event = cls(
            audit_id=self.audit.id,
            seq=self._next_seq(),
            ts=utcnow_iso(),
            **kwargs,
        )
        await self.store.append_event(self.audit.id, event)
        await self.bus.publish(self.audit.id, event)
        return event

    async def publish(self, event) -> None:
        """Publish a pre-constructed event (used by the runner callback)."""
        await self.store.append_event(self.audit.id, event)
        await self.bus.publish(self.audit.id, event)
        # Intercept EvtAgentFinished to accumulate per-agent token
        # usage for the report's cost estimate.
        if getattr(event, "type", None) == "agent.finished":
            agent = getattr(event, "agent", None)
            if agent:
                self._token_totals[agent] = {
                    "input": getattr(event, "input_tokens", None) or 0,
                    "output": getattr(event, "output_tokens", None) or 0,
                }

    # ---- main loop ----

    async def run(self) -> None:
        self._start_ns = time.monotonic_ns()
        try:
            await self._normalize_phase()
            # Managed Agents can't mount the host filesystem, so local
            # data paths degrade to "skip data audit" rather than
            # killing the run. Flag the degradation up-front so the
            # user sees it in the activity feed instead of wondering
            # why EDA is empty at the end.
            if isinstance(self.audit.request.data, DataSourceLocal):
                await self.emit(
                    EvtAuditStatus,
                    phase="normalizing",
                    message=(
                        "Local data path provided, but Managed Agents "
                        "cannot access host filesystems — data-side "
                        "checks will be skipped. Use a download URL "
                        "or bundle the dataset into the repo for full "
                        "EDA coverage."
                    ),
                )
            if isinstance(self.audit.request.paper, PaperSourceNone):
                claims = await self._run_paper_analyst_code_only()
            else:
                claims = await self._run_paper_analyst()
            findings = await self._run_code_auditor(claims)
            validation = await self._run_validator(claims, findings)
            report = await self._run_reviewer(claims, findings, validation)

            # Emit report.final before flipping phase=done in SQLite so
            # the UI unblocks from the FinalizingOverlay on the wire
            # write, not the second disk write.
            self.audit.phase = "done"
            await self.emit(EvtReportFinal, report=report)
            await self.store.upsert(self.audit)
            await self.emit(EvtAuditStatus, phase="done")
        except BaseException as e:
            await self._handle_failure(e)
            raise

    # ---- phases ----

    async def _normalize_phase(self) -> None:
        self.audit.phase = "normalizing"
        await self.store.upsert(self.audit)

        # Resume path: if a previous run already resolved inputs and
        # the repo is still on disk, reuse.
        if (
            self.audit.repo_path is not None
            and self.audit.repo_path.exists()
        ):
            self._paths = NormalizedPaths(
                paper_path=self.audit.paper_path,
                repo_path=self.audit.repo_path,
                data_path=self.audit.data_path,
                source_summary="resumed",
            )
            await self.emit(
                EvtAuditStatus,
                phase="normalizing",
                message="Inputs already normalized — resumed.",
            )
            return

        await self.emit(
            EvtAuditStatus, phase="normalizing", message="Resolving inputs"
        )
        paths = await self.normalizer.normalize(
            self.audit.id, self.audit.request
        )
        self._paths = paths
        self.audit.paper_path = paths.paper_path
        self.audit.repo_path = paths.repo_path
        self.audit.data_path = paths.data_path
        await self.store.upsert(self.audit)

    async def _run_paper_analyst_code_only(self) -> PaperClaims:
        """Produce PaperClaims for code-only audits.

        If the repo has a README ≥ 500 chars, run the Paper Analyst
        against it as a weak claim source (extraction_confidence hard-
        capped at 0.5 to protect verdict integrity — the README is
        not an academic paper). Otherwise emit an empty claims
        artifact with extraction_confidence=0.0.
        """
        self.audit.phase = "paper_analyst"
        await self.store.upsert(self.audit)

        # Resume path: reuse claims if a previous run produced them.
        existing = await self.store.load_artifact(
            self.audit.id, "claims", PaperClaims
        )
        if existing is not None:
            await self.emit(
                EvtAuditStatus,
                phase="paper_analyst",
                message="Claims already extracted — resumed.",
            )
            await self.emit(EvtClaimsExtracted, claims=existing)
            return existing

        readme_text = self._find_readme_text()
        if readme_text is not None and len(readme_text) >= _README_MIN_CHARS:
            return await self._run_paper_analyst_from_readme(readme_text)

        await self.emit(
            EvtAuditStatus,
            phase="paper_analyst",
            message=(
                "No paper provided and no README ≥ "
                f"{_README_MIN_CHARS} chars — skipping extraction."
            ),
        )
        claims = PaperClaims(
            paper_title="(no paper provided)",
            authors=[],
            abstract_summary="Code-only audit; no paper to analyse.",
            metrics=[],
            datasets=[],
            architectures=[],
            training_config=[],
            evaluation_protocol=[],
            extraction_confidence=0.0,
        )
        await self.store.save_artifact(self.audit.id, "claims", claims)
        await self.emit(EvtClaimsExtracted, claims=claims)
        return claims

    def _find_readme_text(self) -> Optional[str]:
        """Return README text at repo root, or None if absent/unreadable."""
        assert self._paths is not None
        repo_root = self._paths.repo_path
        if not repo_root.is_dir():
            return None
        candidates = {"readme.md", "readme.rst", "readme.txt", "readme"}
        for p in sorted(repo_root.iterdir()):
            if p.is_file() and p.name.lower() in candidates:
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return None
                if text.strip():
                    return text
        return None

    async def _run_paper_analyst_from_readme(
        self, readme_text: str
    ) -> PaperClaims:
        """Run the Paper Analyst against the repo README.

        Extraction confidence is hard-capped at ``_README_CONFIDENCE_CAP``
        regardless of what the agent self-reports — the README is not an
        academic paper and the diagnostic verdict must not treat it as
        one. 'readme_derived' is added to ``unresolved_questions`` so
        the Reviewer knows to weight claims accordingly.
        """
        title_hint = getattr(self.audit.request.paper, "title_hint", None)
        await self.emit(
            EvtAuditStatus,
            phase="paper_analyst",
            message=(
                "No paper provided — extracting claims from repo README "
                "instead (confidence capped at "
                f"{_README_CONFIDENCE_CAP})."
            ),
        )

        content = build_readme_analyst_content(
            readme_text,
            title_hint=title_hint,
            audit_summary=self._audit_summary(),
            user_notes=self.audit.request.user_notes,
        )
        try:
            raw_text = await asyncio.wait_for(
                self.runner.run_agent(
                    audit_id=self.audit.id,
                    role="paper_analyst",
                    user_content=content,
                    on_event=self.publish,
                    next_seq=self._next_seq,
                    max_turns=_MAX_TURNS["paper_analyst"],
                ),
                timeout=self._timeout_for("paper_analyst"),
            )
            self._save_raw("paper_analyst", raw_text)
            claims = await parse_json_output(
                raw_text, PaperClaims,
                repair_with=self._make_repair("paper_analyst"),
                normalize_with=normalize_paper_claims,
            )
            updates: dict = {
                "extraction_confidence": min(
                    claims.extraction_confidence, _README_CONFIDENCE_CAP
                ),
            }
            if "readme_derived" not in claims.unresolved_questions:
                updates["unresolved_questions"] = [
                    *claims.unresolved_questions,
                    "readme_derived",
                ]
            claims = claims.model_copy(update=updates)
        except _DEGRADABLE_ERRORS as e:
            # README-derived claims are already weak evidence; on
            # failure, degrade to empty claims (not minimal-with-
            # confidence-0.2, since we never had a paper to begin with).
            error_type = _classify_error(e)
            _log.warning(
                "paper_analyst (README path) failed (%s); degrading to "
                "empty claims",
                error_type,
            )
            await self.emit(
                EvtAuditError,
                agent="paper_analyst",
                error_type=error_type,
                message=str(e) or type(e).__name__,
                recoverable=True,
            )
            claims = self._minimal_paper_claims(
                reason=f"paper_analyst_readme_{error_type}",
                confidence=0.0,
            )

        await self.store.save_artifact(self.audit.id, "claims", claims)
        await self.emit(EvtClaimsExtracted, claims=claims)
        return claims

    def _minimal_paper_claims(
        self, *, reason: str, confidence: float
    ) -> PaperClaims:
        """Build a safe PaperClaims when extraction fails.

        Used by both the regular paper_analyst and the README fallback
        when they hit timeout / turn-limit / validation errors. Uses
        ``title_hint`` if available. The reason string is appended to
        ``unresolved_questions`` so the Reviewer knows why extraction
        was skipped.
        """
        title_hint = getattr(self.audit.request.paper, "title_hint", None)
        return PaperClaims(
            paper_title=title_hint or "(extraction unavailable)",
            authors=[],
            abstract_summary=(
                f"Paper Analyst fallback ({reason}); no claims extracted."
            ),
            metrics=[],
            datasets=[],
            architectures=[],
            training_config=[],
            evaluation_protocol=[],
            extraction_confidence=confidence,
            unresolved_questions=[reason],
        )

    async def _run_paper_analyst(self) -> PaperClaims:
        assert self._paths is not None
        assert self._paths.paper_path is not None, (
            "PaperSourceNone should be routed through "
            "_run_paper_analyst_code_only"
        )
        self.audit.phase = "paper_analyst"
        await self.store.upsert(self.audit)

        # Resume path: reuse claims if previous run produced them.
        existing = await self.store.load_artifact(
            self.audit.id, "claims", PaperClaims
        )
        if existing is not None:
            await self.emit(
                EvtAuditStatus,
                phase="paper_analyst",
                message="Claims already extracted — resumed.",
            )
            await self.emit(EvtClaimsExtracted, claims=existing)
            return existing

        await self.emit(EvtAuditStatus, phase="paper_analyst")

        content = build_paper_analyst_content(
            self._paths.paper_path,
            self.audit.request.paper,
            audit_summary=self._audit_summary(),
            user_notes=self.audit.request.user_notes,
        )
        try:
            raw_text = await asyncio.wait_for(
                self.runner.run_agent(
                    audit_id=self.audit.id,
                    role="paper_analyst",
                    user_content=content,
                    on_event=self.publish,
                    next_seq=self._next_seq,
                    max_turns=_MAX_TURNS["paper_analyst"],
                ),
                timeout=self._timeout_for("paper_analyst"),
            )
            self._save_raw("paper_analyst", raw_text)
            claims = await parse_json_output(
                raw_text, PaperClaims,
                repair_with=self._make_repair("paper_analyst"),
                normalize_with=normalize_paper_claims,
            )
        except _DEGRADABLE_ERRORS as e:
            # ARCHITECTURE.md §6.5: Paper Analyst failure degrades to a
            # minimal PaperClaims; the audit is not killed. The Reviewer
            # sees extraction_confidence=0.2 and weights claims low.
            error_type = _classify_error(e)
            _log.warning(
                "paper_analyst failed (%s); falling back to minimal claims",
                error_type,
            )
            await self.emit(
                EvtAuditError,
                agent="paper_analyst",
                error_type=error_type,
                message=str(e) or type(e).__name__,
                recoverable=True,
            )
            claims = self._minimal_paper_claims(
                reason=f"paper_analyst_{error_type}",
                confidence=0.2,
            )

        await self.store.save_artifact(self.audit.id, "claims", claims)
        await self.emit(EvtClaimsExtracted, claims=claims)
        return claims

    async def _run_code_auditor(self, claims: PaperClaims) -> AuditFindings:
        assert self._paths is not None
        self.audit.phase = "code_auditor"
        await self.store.upsert(self.audit)

        # Resume path: reuse findings + manifest if present.
        existing = await self.store.load_artifact(
            self.audit.id, "findings", AuditFindings
        )
        if existing is not None:
            self._manifest = await self.store.load_artifact(
                self.audit.id, "repo_manifest", RepoManifest
            )
            await self.emit(
                EvtAuditStatus,
                phase="code_auditor",
                message="Findings already produced — resumed.",
            )
            return existing

        await self.emit(EvtAuditStatus, phase="code_auditor")

        self._manifest = build_manifest(self._paths.repo_path)
        await self.store.save_artifact(
            self.audit.id, "repo_manifest", self._manifest
        )

        content = build_code_auditor_content(
            self.audit.request.code,
            self.audit.request.data,
            claims_json=claims.model_dump_json(),
            manifest_json=self._manifest.model_dump_json(),
            audit_summary=self._audit_summary(),
            user_notes=self.audit.request.user_notes,
            data_structure_text=self.audit.request.data_structure_text,
        )

        # Capture every agent.message text so we can attempt partial
        # recovery if the session drops mid-stream. The Code Auditor is
        # the most expensive agent; losing all of its work to a
        # transient network error is the biggest money sink we have.
        captured_texts: list[str] = []

        async def capturing_publish(event) -> None:
            await self.publish(event)
            if (
                getattr(event, "type", None) == "agent.message"
                and getattr(event, "agent", None) == "code_auditor"
            ):
                text = getattr(event, "text", "") or ""
                if text.strip():
                    captured_texts.append(text)

        try:
            raw_text = await asyncio.wait_for(
                self.runner.run_agent(
                    audit_id=self.audit.id,
                    role="code_auditor",
                    user_content=content,
                    on_event=capturing_publish,
                    next_seq=self._next_seq,
                    max_turns=_MAX_TURNS["code_auditor"],
                ),
                timeout=self._timeout_for("code_auditor"),
            )
            self._save_raw("code_auditor", raw_text)
            findings = await parse_json_output(
                raw_text, AuditFindings,
                repair_with=self._make_repair("code_auditor"),
                normalize_with=normalize_audit_findings,
            )
        except _DEGRADABLE_ERRORS as e:
            error_type = _classify_error(e)
            _log.warning(
                "code_auditor failed (%s); attempting partial recovery "
                "from %d captured messages",
                error_type, len(captured_texts),
            )
            await self.emit(
                EvtAuditError,
                agent="code_auditor",
                error_type=error_type,
                message=str(e) or type(e).__name__,
                recoverable=True,
            )
            findings = await self._recover_partial_findings(
                captured_texts, error_type=error_type
            )

        await self.store.save_artifact(self.audit.id, "findings", findings)
        for f in findings.findings:
            await self.emit(
                EvtFindingEmitted, agent="code_auditor", finding=f
            )
        return findings

    async def _recover_partial_findings(
        self, captured_texts: list[str], *, error_type: str
    ) -> AuditFindings:
        """Try to salvage partial findings from Code Auditor stream.

        Walks captured agent.message texts from newest to oldest, trying
        each as an ``AuditFindings`` JSON. The first that parses
        successfully wins. Deliberately passes ``repair_with=None`` — we
        don't want to burn additional API budget on a repair call when
        the session already dropped. If nothing parses, returns empty
        findings so the Validator / Reviewer can still produce a
        (low-confidence) report instead of killing the audit.
        """
        for text in reversed(captured_texts):
            if "{" not in text:
                continue
            try:
                findings = await parse_json_output(
                    text, AuditFindings,
                    repair_with=None,
                    normalize_with=normalize_audit_findings,
                )
            except Exception:
                continue
            _log.info(
                "recovered %d partial finding(s) from code_auditor "
                "mid-stream",
                len(findings.findings),
            )
            # Persist the salvaged text so `reparse_report.py` can see
            # what we pulled out.
            self._save_raw("code_auditor", text)
            # Tag the partial batch so the Reviewer knows coverage
            # was incomplete.
            tag = f"code_auditor_partial_delivery_{error_type}"
            notes = list(findings.coverage_notes)
            if tag not in notes:
                notes.append(tag)
            return findings.model_copy(update={"coverage_notes": notes})

        return AuditFindings(
            findings=[],
            repo_summary=(
                f"Code Auditor failed ({error_type}) before emitting a "
                "parseable findings batch; no findings recovered."
            ),
            coverage_notes=[
                f"code_auditor_partial_delivery_failed_{error_type}"
            ],
        )

    async def _run_validator(
        self, claims: PaperClaims, findings: AuditFindings
    ) -> ValidationBatch:
        self.audit.phase = "validator"
        await self.store.upsert(self.audit)

        existing = await self.store.load_artifact(
            self.audit.id, "validation", ValidationBatch
        )
        if existing is not None:
            await self.emit(
                EvtAuditStatus,
                phase="validator",
                message="Validation already produced — resumed.",
            )
            return existing

        await self.emit(EvtAuditStatus, phase="validator")

        content = build_validator_content(
            self.audit.request.code,
            self.audit.request.data,
            claims_json=claims.model_dump_json(),
            findings_json=findings.model_dump_json(),
            user_notes=self.audit.request.user_notes,
            data_structure_text=self.audit.request.data_structure_text,
        )

        # Capture validator agent.message texts so we can salvage
        # partial validation results on a mid-stream failure. Same
        # pattern as the Code Auditor.
        captured_texts: list[str] = []

        async def capturing_publish(event) -> None:
            await self.publish(event)
            if (
                getattr(event, "type", None) == "agent.message"
                and getattr(event, "agent", None) == "validator"
            ):
                text = getattr(event, "text", "") or ""
                if text.strip():
                    captured_texts.append(text)

        try:
            raw_text = await asyncio.wait_for(
                self.runner.run_agent(
                    audit_id=self.audit.id,
                    role="validator",
                    user_content=content,
                    on_event=capturing_publish,
                    next_seq=self._next_seq,
                    max_turns=_MAX_TURNS["validator"],
                ),
                timeout=self._timeout_for("validator"),
            )
            self._save_raw("validator", raw_text)
            try:
                validation = await parse_json_output(
                    raw_text, ValidationBatch,
                    repair_with=self._make_repair("validator"),
                    normalize_with=normalize_validation_batch,
                )
            except ValidationFailedError as full_err:
                # new_findings is a bonus output; if a malformed bonus
                # finding is killing the batch, drop the bonus list
                # and keep the paid-for results + proactive payload.
                _log.warning(
                    "validator full-shape parse failed; retrying with "
                    "new_findings stripped: %s", full_err,
                )
                validation = await parse_json_output(
                    raw_text, ValidationBatch,
                    repair_with=None,
                    normalize_with=normalize_validation_batch_drop_new_findings,
                )
                current_notes = validation.notes or ""
                tag = "validator_new_findings_dropped_shape_drift"
                validation = validation.model_copy(update={
                    "notes": (
                        f"{current_notes}; {tag}" if current_notes else tag
                    )[:2000]
                })
        except _DEGRADABLE_ERRORS as e:
            error_type = _classify_error(e)
            _log.warning(
                "validator failed (%s); attempting partial recovery from "
                "%d captured messages",
                error_type, len(captured_texts),
            )
            await self.emit(
                EvtAuditError,
                agent="validator",
                error_type=error_type,
                message=str(e),
                recoverable=True,
            )
            validation = await self._recover_partial_validation(
                captured_texts, findings, error_type=error_type
            )

        await self.store.save_artifact(self.audit.id, "validation", validation)
        for r in validation.results:
            await self.emit(EvtValidationCompleted, result=r)
        return validation

    async def _recover_partial_validation(
        self,
        captured_texts: list[str],
        findings: AuditFindings,
        *,
        error_type: str,
    ) -> ValidationBatch:
        """Try to salvage partial ValidationBatch from validator stream.

        Same shape as ``_recover_partial_findings``: newest-first walk
        through captured ``agent.message`` texts, ``parse_json_output``
        with no repair (no extra API spend on a dying session). First
        text that parses as ``ValidationBatch`` wins and gets tagged
        with a partial-delivery note so the Reviewer knows coverage
        was incomplete. Unvalidated finding ids are topped up from the
        Auditor's findings list for any finding we didn't confirm.
        """
        for text in reversed(captured_texts):
            if "{" not in text:
                continue
            try:
                validation = await parse_json_output(
                    text, ValidationBatch, repair_with=None,
                    normalize_with=normalize_validation_batch,
                )
            except Exception:
                continue
            _log.info(
                "recovered %d validation result(s) from validator "
                "mid-stream",
                len(validation.results),
            )
            self._save_raw("validator", text)
            # Top up unvalidated_finding_ids with anything we didn't
            # actually confirm/deny — so the Reviewer treats the
            # untouched subset correctly.
            touched = {r.finding_id for r in validation.results}
            missing = [
                f.id for f in findings.findings if f.id not in touched
            ]
            tag = f"validator_partial_delivery_{error_type}"
            current_notes = validation.notes or ""
            new_notes = (
                f"{current_notes}; {tag}" if current_notes else tag
            )[:2000]
            updates = {
                "notes": new_notes,
                "unvalidated_finding_ids": [
                    *validation.unvalidated_finding_ids,
                    *(m for m in missing
                      if m not in validation.unvalidated_finding_ids),
                ],
            }
            return validation.model_copy(update=updates)

        return ValidationBatch(
            results=[],
            proactive=[],
            runtime_total_seconds=0.0,
            notes=(
                f"Validator failed ({error_type}); "
                "all findings marked unvalidated."
            ),
            unvalidated_finding_ids=[f.id for f in findings.findings],
            new_findings=[],
        )

    async def _run_reviewer(
        self,
        claims: PaperClaims,
        findings: AuditFindings,
        validation: ValidationBatch,
    ) -> DiagnosticReport:
        self.audit.phase = "reviewer"
        await self.store.upsert(self.audit)

        existing = await self.store.load_artifact(
            self.audit.id, "report", DiagnosticReport
        )
        if existing is not None:
            await self.emit(
                EvtAuditStatus,
                phase="reviewer",
                message="Report already produced — resumed.",
            )
            return existing

        await self.emit(EvtAuditStatus, phase="reviewer")

        manifest_json = (
            self._manifest.model_dump_json()
            if self._manifest is not None
            else "{}"
        )
        content = build_reviewer_content(
            claims_json=claims.model_dump_json(),
            findings_json=findings.model_dump_json(),
            validation_json=validation.model_dump_json(),
            manifest_json=manifest_json,
            user_notes=self.audit.request.user_notes,
        )

        try:
            raw_text = await asyncio.wait_for(
                self.runner.run_agent(
                    audit_id=self.audit.id,
                    role="reviewer",
                    user_content=content,
                    on_event=self.publish,
                    next_seq=self._next_seq,
                    max_turns=_MAX_TURNS["reviewer"],
                ),
                timeout=self._timeout_for("reviewer"),
            )

            self._save_raw("reviewer", raw_text)
            await self.emit(
                EvtAuditStatus,
                phase="reviewer",
                message="Parsing reviewer output…",
            )

            eda_fallback = (
                findings.eda.model_dump() if findings.eda is not None else None
            )
            # Pre-serialize the join inputs once — parse_json_output may
            # invoke ``_normalize`` multiple times (initial pass + repair
            # retry), and model_dump() on large Pydantic trees isn't free.
            auditor_findings_dump = [f.model_dump() for f in findings.findings]
            validator_new_findings_dump = [
                f.model_dump() for f in validation.new_findings
            ]
            validation_results_dump = [r.model_dump() for r in validation.results]

            def _normalize(obj: dict) -> dict:
                return normalize_reviewer_report(
                    obj,
                    audit_id=self.audit.id,
                    generated_at=utcnow_iso(),
                    eda_fallback=eda_fallback,
                    auditor_findings=auditor_findings_dump,
                    validator_new_findings=validator_new_findings_dump,
                    validation_results=validation_results_dump,
                )

            report = await parse_json_output(
                raw_text, DiagnosticReport,
                repair_with=self._make_repair("reviewer"),
                normalize_with=_normalize,
            )
        except _DEGRADABLE_ERRORS as e:
            reason = _classify_error(e)
            _log.warning(
                "reviewer failed (%s); falling back to deterministic "
                "Python synthesizer",
                reason,
            )
            await self.emit(
                EvtAuditError,
                agent="reviewer",
                error_type=reason,
                message=str(e) or type(e).__name__,
                recoverable=True,
            )
            report = build_fallback_report(
                self.audit.id, claims, findings, validation,
                reason=reason,
            )
        report.runtime_mode_used = self.runner.last_mode
        report.runtime_ms_total = int(
            (time.monotonic_ns() - self._start_ns) // 1_000_000
        )
        report.cost_usd_estimate = self._estimate_cost_usd()
        await self.store.save_artifact(self.audit.id, "report", report)
        return report

    def _estimate_cost_usd(self) -> Optional[float]:
        """Sum per-agent token totals and price at public Opus rates.

        Returns None if no token telemetry was captured (e.g. tests
        with mocked sessions) so the frontend hides the row instead
        of showing "$0.00".
        """
        if not self._token_totals:
            return None
        total_in = sum(t.get("input", 0) for t in self._token_totals.values())
        total_out = sum(t.get("output", 0) for t in self._token_totals.values())
        if total_in == 0 and total_out == 0:
            return None
        return (
            (total_in / 1_000_000) * _COST_PER_M_INPUT_USD
            + (total_out / 1_000_000) * _COST_PER_M_OUTPUT_USD
        )

    # ---- helpers ----

    async def _handle_failure(self, e: BaseException) -> None:
        error_type = _classify_error(e)
        try:
            await self.emit(
                EvtAuditError,
                error_type=error_type,
                message=str(e),
                recoverable=False,
            )
        except Exception as emit_err:
            _log.error("failed to emit audit error event: %s", emit_err)
        self.audit.phase = "failed"
        self.audit.error = f"{type(e).__name__}: {e}"
        try:
            await self.store.upsert(self.audit)
        except Exception as store_err:
            _log.error("failed to persist failed audit: %s", store_err)

    def _timeout_for(self, role: str) -> float:
        total_s = self.audit.request.timeout_minutes * 60
        return total_s * _TIMEOUT_FRACTIONS[role]

    def _save_raw(self, role: str, raw_text: str) -> None:
        """Persist a role's raw JSON output before parsing.

        If parse_json_output fails (schema drift, malformed JSON), the
        raw text survives on disk so ``reparse_report.py``-style offline
        iteration is possible without re-invoking the agent.
        """
        art_dir = (
            self.settings.data_root_path()
            / "audits"
            / self.audit.id
            / "artifacts"
        )
        art_dir.mkdir(parents=True, exist_ok=True)
        (art_dir / f"{role}_raw.txt").write_text(raw_text, encoding="utf-8")

    def _make_repair(self, role):
        """Return a coroutine that fixes invalid JSON via the Messages API.

        Called by ``parse_json_output`` when schema validation fails
        AFTER the salvage pass (which drops only individually-invalid
        list entries). Bypasses Managed Agents entirely (no sessions,
        no tools, no cloning) — this is a pure text-in, text-out
        transformation, so a direct ``messages.create`` call is faster,
        cheaper, and far more predictable than spinning up a new agent
        session that might re-run its original workflow.

        Output-token caps: Reviewer gets 32k (a full DiagnosticReport
        with 20+ findings, claim_verifications, recommendations can
        be ~60k chars ≈ 15k tokens — 8k was tight enough to truncate
        the tail silently). Other roles get 32k too for consistency.

        Input truncation: bumped from 12k → 120k chars. The original
        12k cap was a silent footgun: on any audit where the reviewer
        emitted 40k+ chars of JSON (routine on moderate-size repos)
        and ONE key-rename drift survived normalization, the repair
        would see only the head and reconstruct a small output that
        PASSED validation but LOST the tail. That failure was invisible
        — the report looked syntactically correct but was missing
        most findings/recommendations. 120k is far above any
        reasonable reviewer output and fits comfortably in Opus 4.7's
        200k context window (schema prompt + raw + errors ≈ ~30k tokens
        at 120k chars). Comprehensive normalizers + per-entry salvage
        should make this path rarely needed, but when it IS called it
        has the full payload to work with.
        """
        max_tokens = 32_000
        timeout_s = 180.0 if role == "reviewer" else 120.0

        async def repair(raw_json: str, error_msg: str) -> str:
            if role == "reviewer":
                # Bracket the gap so the FinalizingOverlay shows why
                # the reviewer→report.final wait is longer than usual.
                try:
                    await self.emit(
                        EvtAuditStatus,
                        phase="reviewer",
                        message="Repairing reviewer JSON (schema drift)…",
                    )
                except Exception as emit_err:
                    _log.debug("repair status emit failed: %s", emit_err)

            client = self.runner._client  # anthropic.AsyncAnthropic
            truncated = raw_json[:120_000]
            was_truncated = len(raw_json) > 120_000
            note = (
                "\n\n[NOTE: PREVIOUS_JSON exceeded 120k chars and was "
                "truncated. Return the FULL corrected JSON, reusing "
                "the visible structure and preserving every list "
                "entry that you can see — do not omit any.]"
                if was_truncated else ""
            )
            response = await asyncio.wait_for(
                client.messages.create(
                    model="claude-opus-4-7",
                    max_tokens=max_tokens,
                    system=(
                        "You correct JSON objects so they validate "
                        "against a pydantic schema. You are given the "
                        "previous JSON output and the validation "
                        "errors. Preserve ALL valid content — every "
                        "list entry, every field — and only modify "
                        "what the errors explicitly call out. For "
                        "invalid fields, rename to the canonical key "
                        "or substitute a reasonable value. Do NOT "
                        "drop list entries that weren't flagged as "
                        "invalid. Emit ONLY the corrected JSON inside "
                        "a single fenced ```json block. Do not "
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
                timeout=timeout_s,
            )
            return "".join(
                getattr(block, "text", "") for block in response.content
            )

        return repair

    def _audit_summary(self) -> str:
        parts = [f"RunItBack audit {self.audit.id}"]
        paper = self.audit.request.paper
        title_hint = getattr(paper, "title_hint", None)
        if title_hint:
            parts.append(f"title hint: {title_hint}")
        return "\n".join(parts)


def _classify_error(e: BaseException) -> str:
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    if isinstance(e, TurnLimitExceeded):
        # Turn-limit is a budget-exhaustion event, same category as a
        # wall-clock timeout. Mapping it to ``timeout`` keeps the UI
        # banner informative ("ran out of budget") rather than the
        # scary-looking ``internal_error``.
        return "timeout"
    if isinstance(e, anthropic.APITimeoutError):
        return "timeout"
    if isinstance(e, InputError):
        return "input_error"
    if isinstance(e, NonRecoverableAPIError):
        return "api_error"
    if isinstance(e, (anthropic.APIConnectionError, httpx.HTTPError)):
        # Network drop / incomplete read mid-stream — transient,
        # the audit can still produce a report from what we have.
        return "api_error"
    if isinstance(
        e, (anthropic.InternalServerError, anthropic.RateLimitError)
    ):
        return "api_error"
    if isinstance(e, ValidationFailedError):
        return "validation_error"
    if isinstance(e, UnavailableError):
        return "internal_error"
    return "internal_error"
