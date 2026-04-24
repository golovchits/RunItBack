from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field, field_validator

from .common import Lenient
from .findings import AuditFinding

_VALID_VERDICTS = {"confirmed", "denied", "inconclusive", "unvalidated"}


class ValidationResult(Lenient):
    id: str
    finding_id: str
    verdict: Literal["confirmed", "denied", "inconclusive", "unvalidated"]
    method: str = Field(max_length=400)
    command: Optional[str] = None
    stdout_excerpt: Optional[str] = Field(default=None, max_length=4000)
    stderr_excerpt: Optional[str] = Field(default=None, max_length=2000)
    exit_code: Optional[int] = None
    runtime_seconds: Optional[float] = None
    # Was ``dict[str, Union[float, int, str]]``; widened to ``Any``
    # because agents naturally record structured evidence — centroid
    # coordinates (``[[50, 56], ...]``), confusion matrices, lists of
    # runtime warnings. This field is passthrough context for the
    # Reviewer, never structurally queried, so ``Any`` is safe and
    # the prior constraint was silently killing batches whenever the
    # Validator produced good evidence.
    numerical_evidence: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    confidence: float = Field(ge=0, le=1)

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v):
        # Agents sometimes emit "partially_confirmed", "likely", etc.
        # that aren't in our set. Coerce unknown values to
        # "inconclusive" — the honest default for "we tried but can't
        # pin it down" — so one drifty result doesn't reject the whole
        # ValidationBatch.
        if isinstance(v, str):
            lowered = v.strip().lower()
            if lowered in _VALID_VERDICTS:
                return lowered
            return "inconclusive"
        return v

    @field_validator("method", mode="before")
    @classmethod
    def _truncate_method(cls, v):
        if isinstance(v, str) and len(v) > 400:
            return v[:400]
        return v

    @field_validator("stdout_excerpt", mode="before")
    @classmethod
    def _truncate_stdout(cls, v):
        if isinstance(v, str) and len(v) > 4000:
            return v[:4000]
        return v

    @field_validator("stderr_excerpt", mode="before")
    @classmethod
    def _truncate_stderr(cls, v):
        if isinstance(v, str) and len(v) > 2000:
            return v[:2000]
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v):
        if v is None:
            return 0.5
        if isinstance(v, (int, float)):
            if v < 0:
                return 0.0
            if v > 1:
                return 1.0
        return v


class ProactiveCheck(Lenient):
    # Was a Literal of six known slugs; widened to str because agents
    # invent reasonable extras (``pytest_suite``, ``ruff_lint``,
    # ``type_check``) that weren't in the enumerated set. Same pattern
    # as ``Evidence.kind`` in common.py. The slug is only surfaced to
    # the Reviewer as context; no code path pattern-matches on it.
    slug: str
    result: ValidationResult


class ValidationBatch(Lenient):
    results: list[ValidationResult]
    proactive: list[ProactiveCheck]
    unvalidated_finding_ids: list[str] = Field(default_factory=list)
    runtime_total_seconds: float
    notes: str = Field(default="", max_length=2000)
    new_findings: list[AuditFinding] = Field(default_factory=list)

    @field_validator("notes", mode="before")
    @classmethod
    def _truncate_notes(cls, v):
        if v is None:
            return ""
        if isinstance(v, str) and len(v) > 2000:
            return v[:2000]
        return v

    @field_validator("runtime_total_seconds", mode="before")
    @classmethod
    def _coerce_runtime(cls, v):
        if v is None:
            return 0.0
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return 0.0
        return v
