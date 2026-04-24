from __future__ import annotations

import copy
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from backend.errors import ValidationFailedError

_log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

NormalizeFn = Callable[[dict], dict]


async def parse_json_output(
    text: str,
    cls: type[T],
    *,
    repair_with: Optional[Callable[[str, str], Awaitable[str]]] = None,
    normalize_with: Optional[NormalizeFn] = None,
) -> T:
    """Extract a JSON object from ``text`` and validate against ``cls``.

    Extraction: scans the text for every ``{`` position and tries
    ``json.JSONDecoder.raw_decode`` — the rightmost successful decode
    wins. This handles pure JSON, fenced JSON, bare JSON after prose,
    and fenced blocks where the agent mixed prose + JSON in a single
    ``` code block.

    If ``normalize_with`` is provided, the decoded dict is normalized
    before (and after any repair) validation. Used for reviewer-style
    shape-drift repair (alias renames, missing-required backfill)
    that is cheaper to fix locally than by re-prompting the model.

    Validation pipeline (most-preserving-first):
      1. ``cls.model_validate`` on the normalized dict.
      2. If validation fails, try list-entry salvage: drop only the
         list items that caused errors and re-validate. This keeps
         21 of 22 findings when one entry has a bad field, instead
         of rejecting the whole batch and sending the full raw
         through a lossy LLM repair round-trip.
      3. If salvage still fails and ``repair_with`` is provided,
         invoke it once with ``(raw_json, error_message)`` and re-
         extract / re-normalize / re-validate the repair output.
      4. If step 3 also fails (or repair callable isn't provided),
         raise ``ValidationFailedError``.

    The salvage step is new and load-bearing: it's the fix for the
    "reviewer raw doesn't translate to report" class of bugs. A single
    missing key-rename in the normalizer would previously drop the
    whole report into a truncated-repair roundtrip that lost most
    findings; salvage now keeps everything the schema can accept.
    """
    raw = _extract_json(text)
    if raw is None:
        raise ValidationFailedError(
            f"no JSON object found in output for {cls.__name__}",
            details={"head": text[:400]},
        )

    if normalize_with is not None:
        try:
            raw_dict = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValidationFailedError(
                f"extracted JSON for {cls.__name__} is not a dict: {e}",
                details={"raw": raw[:2000]},
            ) from e
        raw_dict = normalize_with(raw_dict)
        raw = json.dumps(raw_dict)

    # Step 1: straight validation on the normalized dict.
    # Capture the error outside the except block — Python scopes
    # ``except ... as e`` such that ``e`` is deleted when the handler
    # exits, so any downstream reference would be an UnboundLocalError.
    first_err: Optional[ValidationError] = None
    try:
        return cls.model_validate_json(raw)
    except ValidationError as e:
        first_err = e

    # Step 2: salvage — drop individual list entries that failed and
    # re-validate what's left. Normalization should cover most drift,
    # but any novel field mismatch on a single entry would otherwise
    # kill the whole batch. Salvage makes the parser tolerant to "one
    # bad finding out of 22" without losing the other 21.
    try:
        obj_for_salvage = json.loads(raw)
    except json.JSONDecodeError:
        obj_for_salvage = None

    assert first_err is not None
    if isinstance(obj_for_salvage, dict):
        salvaged = _salvage_invalid_list_entries(
            obj_for_salvage, first_err
        )
        if salvaged is not None:
            try:
                validated = cls.model_validate(salvaged)
                dropped = _count_salvaged_drops(first_err)
                _log.warning(
                    "salvaged %s by dropping %d invalid list entr%s",
                    cls.__name__, dropped, "y" if dropped == 1 else "ies",
                )
                return validated
            except ValidationError as salvage_err:
                first_err = salvage_err

    if repair_with is None:
        raise ValidationFailedError(
            f"{cls.__name__} validation failed: {first_err}",
            details={"raw": raw[:2000], "errors": first_err.errors()},
        ) from first_err
    first_err_msg = str(first_err)

    # Step 3: repair via LLM round-trip.
    try:
        repaired = await repair_with(raw, first_err_msg)
    except Exception as repair_err:
        raise ValidationFailedError(
            f"repair call failed for {cls.__name__}: "
            f"{type(repair_err).__name__}: {repair_err}",
            details={"raw": raw[:2000]},
        ) from repair_err

    repaired_json = _extract_json(repaired) or repaired
    if normalize_with is not None:
        try:
            repaired_dict = json.loads(repaired_json)
            repaired_dict = normalize_with(repaired_dict)
            repaired_json = json.dumps(repaired_dict)
        except json.JSONDecodeError:
            pass  # let model_validate_json surface the parse error

    try:
        return cls.model_validate_json(repaired_json)
    except ValidationError as second_err:
        # Step 4: last-ditch salvage on the repaired JSON too, because
        # the LLM repair sometimes reintroduces drift on different
        # entries. Same principle: preserve the max validatable subset.
        try:
            repaired_obj = json.loads(repaired_json)
        except json.JSONDecodeError:
            repaired_obj = None
        if isinstance(repaired_obj, dict):
            salvaged = _salvage_invalid_list_entries(
                repaired_obj, second_err
            )
            if salvaged is not None:
                try:
                    return cls.model_validate(salvaged)
                except ValidationError:
                    pass
        raise ValidationFailedError(
            f"{cls.__name__} still invalid after repair: {second_err}",
            details={
                "raw": repaired_json[:2000],
                "errors": second_err.errors(),
            },
        ) from second_err


def _salvage_invalid_list_entries(
    obj: dict, err: ValidationError
) -> Optional[dict]:
    """Return a copy of ``obj`` with list entries that caused validation
    errors removed, or ``None`` if no list-entry drops are identifiable.

    Walks every ``ValidationError.errors()[i]['loc']`` to find the
    DEEPEST list index in the path and records it as a drop. Multiple
    errors on the same entry collapse to one drop (set semantics). The
    result is a new dict (``copy.deepcopy`` of the input) so the caller
    can retry validation on a clean object.

    Drops the innermost list index so errors like
    ``findings[3].evidence[7].description`` drop ``evidence[7]`` rather
    than the whole ``findings[3]`` entry — preserves more content.
    """
    drops: dict[tuple, set[int]] = {}
    for e in err.errors():
        loc = e.get("loc") or ()
        # Find the LAST integer in the error path — that's the
        # innermost list index. Drop that entry, not its ancestor.
        last_int_pos = -1
        for i, part in enumerate(loc):
            if isinstance(part, int):
                last_int_pos = i
        if last_int_pos < 0:
            continue
        container_path = tuple(loc[:last_int_pos])
        drop_idx = loc[last_int_pos]
        drops.setdefault(container_path, set()).add(int(drop_idx))

    if not drops:
        return None

    result: Any = copy.deepcopy(obj)
    for path, indices in drops.items():
        container: Any = result
        for key in path:
            if isinstance(container, dict) and isinstance(key, str):
                container = container.get(key)
            elif isinstance(container, list) and isinstance(key, int):
                container = (
                    container[key] if 0 <= key < len(container) else None
                )
            else:
                container = None
            if container is None:
                break
        if not isinstance(container, list):
            continue
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(container):
                del container[idx]
    return result


def _count_salvaged_drops(err: ValidationError) -> int:
    """Count distinct (container, index) pairs that salvage would drop."""
    pairs = set()
    for e in err.errors():
        loc = e.get("loc") or ()
        last_int_pos = -1
        for i, part in enumerate(loc):
            if isinstance(part, int):
                last_int_pos = i
        if last_int_pos < 0:
            continue
        pairs.add((tuple(loc[:last_int_pos]), loc[last_int_pos]))
    return len(pairs)


def _apply_synonyms(
    obj: dict, canonical_to_aliases: dict[str, tuple[str, ...]]
) -> None:
    """For each canonical key, if it's missing but any alias is
    present, rename the alias to the canonical name.

    Mutates ``obj`` in place. Never overwrites a canonical key that
    is already set (the canonical always wins). Checks aliases in
    declared order, so more-specific names take precedence over
    less-specific ones when multiple aliases are present.
    """
    if not isinstance(obj, dict):
        return
    for canonical, aliases in canonical_to_aliases.items():
        if canonical in obj:
            continue
        for alias in aliases:
            if alias in obj:
                obj[canonical] = obj.pop(alias)
                break


# ---- per-schema synonym maps ----
#
# These capture every field-rename drift we've observed in agent
# outputs across audits. The rule: if the schema says canonical is X
# and an agent wrote Y, translate Y → X before validation so the
# report faithfully reflects the agent's intent. Order within a tuple
# matters: the leftmost alias wins when multiple are present.

_FINDING_SYNONYMS: dict[str, tuple[str, ...]] = {
    "id": ("finding_id", "fid", "finding"),
    "category": ("type", "kind", "class", "category_name"),
    "severity": ("level", "priority", "impact", "risk"),
    "title": ("name", "summary", "headline", "short_description"),
    "description": ("detail", "body", "text", "long_description"),
    "paper_claim_refs": (
        "claim_refs", "claim_ids", "refs_to_claims", "claims",
    ),
    "code_span": ("span", "location", "code_location"),
    "data_path": ("dataset_path", "data_ref"),
    "paper_says": ("paper_describes", "claim", "paper"),
    "code_does": ("code_implements", "implementation", "code"),
    "suggested_fix_prose": (
        "suggested_fix", "fix", "fix_prose", "patch", "remediation",
        "resolution",
    ),
    "suggested_fix_diff": ("fix_diff", "patch_diff", "diff"),
    "evidence": ("proof", "proofs", "observations", "evidences"),
    "confidence": ("conf", "score"),
    "detector": ("seen_by", "source", "emitted_by", "producer"),
    "cross_refs": ("related_findings", "related_ids", "references"),
}

_CLAIM_VERIFICATION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "claim_id": ("claim", "cid"),
    "claim_summary": ("summary", "description", "claim_text"),
    "status": ("verdict", "outcome", "result", "verification_status"),
    "code_location": ("location", "where", "file_ref", "code_ref"),
    "notes": ("note", "details", "comment", "rationale"),
    "linked_finding_ids": (
        "supporting_finding_ids", "finding_ids",
        "motivating_finding_ids", "refs", "related_finding_ids",
    ),
}

_CONFIG_COMPARISON_SYNONYMS: dict[str, tuple[str, ...]] = {
    # `field` is the single most-common drift we've seen from reviewer
    # agents — emitted in place of `parameter` because a config row
    # intuitively has a "field name". Ship it before anything else.
    "parameter": (
        "field", "key", "name", "parameter_name", "config_key",
        "setting",
    ),
    "paper_value": (
        "paper", "paper_val", "expected", "claimed", "declared",
    ),
    "code_value": (
        "code", "code_val", "actual", "observed", "implementation",
        "implemented_as",
    ),
    "code_location": ("location", "where", "file_ref"),
    "match": (
        "agrees", "ok", "same", "matches", "consistent", "identical",
    ),
    # ConfigDiscrepancy has no linked_finding_ids field, but some
    # agents attach one anyway. If the field is present under an
    # alias, rename to a canonical name so extra="ignore" cleanly
    # discards it rather than producing an unresolved drift signal.
    "linked_finding_ids": (
        "finding_ids", "motivating_finding_ids",
        "supporting_finding_ids", "refs",
    ),
}

_RECOMMENDATION_SYNONYMS: dict[str, tuple[str, ...]] = {
    # `priority` → `rank` is important: reviewer agents naturally
    # call the ordering field "priority", and without this rename
    # the value is lost and every rec gets `rank=i+1` from the
    # index fallback below.
    "rank": ("priority", "order", "position", "rank_order"),
    "title": ("name", "summary", "headline", "recommendation"),
    "rationale": ("reason", "why", "justification", "motivation"),
    "linked_finding_ids": (
        "motivating_finding_ids", "finding_ids",
        "supporting_finding_ids", "refs", "related_finding_ids",
    ),
}

_DISAGREEMENT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "finding_id": ("id", "fid"),
    "auditor_verdict": (
        "auditor_position", "auditor_claim", "auditor", "from_auditor",
    ),
    "validator_verdict": (
        "validator_position", "validator_claim", "validator",
        "from_validator",
    ),
    "reviewer_resolution": (
        "resolution", "reviewer_take", "reviewer", "resolved_as",
    ),
}

_PROACTIVE_CHECK_SYNONYMS: dict[str, tuple[str, ...]] = {
    # `kind` is the single most-common drift from validator agents
    # (the slug and the kind are naturally the same concept). Ship
    # first so subsequent defaulting logic sees a populated slug.
    "slug": ("kind", "name", "check", "type", "id_slug", "check_slug"),
}

_VALIDATION_RESULT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "verdict": ("status", "outcome", "conclusion", "result_status"),
    "method": ("how", "technique", "approach", "description"),
    "confidence": ("conf", "score", "confidence_score"),
    "finding_id": ("fid", "for_finding", "target_finding"),
}

_VR_FIELD_KEYS = frozenset({
    "command", "stdout_excerpt", "stderr_excerpt", "exit_code",
    "runtime_seconds", "numerical_evidence", "error", "confidence",
    "method", "verdict", "findings", "outcome",
})


def normalize_audit_findings(obj: dict) -> dict:
    """Coerce common Code Auditor output drift into an AuditFindings dict.

    Handles without re-prompting:
      - Missing ``repo_summary`` (the agent sometimes emits only
        ``findings`` + ``eda``): backfill with a placeholder so the
        rest of the document validates and ``Reviewer`` can still
        run against the recovered findings.
      - Missing ``findings`` key or null: default to empty list.
      - ``targeted_check_requests`` missing: default to empty list.
    """
    if not isinstance(obj, dict):
        return obj

    if "findings" not in obj or obj["findings"] is None:
        obj["findings"] = []

    if not obj.get("repo_summary"):
        obj["repo_summary"] = (
            "Repository summary not emitted by the agent; see findings "
            "for details."
        )

    if "targeted_check_requests" not in obj or obj["targeted_check_requests"] is None:
        obj["targeted_check_requests"] = []

    return obj


def normalize_paper_claims(obj: dict) -> dict:
    """Coerce common Paper Analyst output drift into a PaperClaims dict.

    Handles without re-prompting:
      - Missing ``extraction_confidence``: backfill to 0.5 (mid-range)
        so the Reviewer weights claims cautiously when the agent
        forgot to self-report. 0.5 is deliberate — lower would be
        safer but silently penalizes good extractions; higher would
        reward sloppy output.
      - Missing ``authors``: default to empty list (Lenient allows it,
        but some agents emit the key as null).
      - ``authors`` given as a single string: wrap to a list.

    Sub-schema drift (e.g. ``splits: ["train", "val"]``) is handled by
    per-field validators on the sub-models themselves.
    """
    if not isinstance(obj, dict):
        return obj

    if "extraction_confidence" not in obj or obj["extraction_confidence"] is None:
        obj["extraction_confidence"] = 0.5

    authors = obj.get("authors")
    if authors is None:
        obj["authors"] = []
    elif isinstance(authors, str):
        obj["authors"] = [authors]

    return obj


def normalize_validation_batch(obj: dict) -> dict:
    """Coerce common Validator output drift into a ValidationBatch dict.

    Handles without re-prompting the model:
      - Proactive check ``result`` emitted as ``{"outcome": "..."}``
        instead of a full ValidationResult: synthesize the required
        id/finding_id/verdict/method/confidence from the slug and
        outcome string. Verdict defaults to ``"inconclusive"`` —
        honest when the check ran but didn't definitively confirm/deny.
      - ``results[*].method`` and ``proactive[*].result.method``
        exceeding the 400-char schema cap: truncate. These descriptions
        are for the Reviewer's context, not structured fields.
      - Top-level ``notes`` exceeding 2000 chars: truncate.
      - ``new_findings[*]`` missing ``detector``: default to
        ``"validator"`` (these are validator-emitted by definition).
      - ``new_findings[*]`` missing ``confidence``: default to 0.5.
      - Top-level list/scalar fields missing: safe defaults so the
        batch validates when the agent omits optional structure.
    """
    if not isinstance(obj, dict):
        return obj

    if obj.get("results") is None:
        obj["results"] = []
    if obj.get("proactive") is None:
        obj["proactive"] = []
    if obj.get("new_findings") is None:
        obj["new_findings"] = []
    if obj.get("unvalidated_finding_ids") is None:
        obj["unvalidated_finding_ids"] = []
    if obj.get("runtime_total_seconds") is None:
        obj["runtime_total_seconds"] = 0.0

    notes = obj.get("notes")
    if isinstance(notes, str) and len(notes) > 2000:
        obj["notes"] = notes[:2000]

    results = obj.get("results")
    if isinstance(results, list):
        obj["results"] = [
            _backfill_validation_result(r, i)
            for i, r in enumerate(results)
            if isinstance(r, dict)
        ]

    proactive = obj.get("proactive")
    if isinstance(proactive, list):
        cleaned: list[dict] = []
        for i, check in enumerate(proactive):
            if not isinstance(check, dict):
                continue
            # Apply slug synonyms before anything else so downstream
            # defaulting sees a populated slug. ``kind`` is the most
            # common drift (the check kind and the slug are the same
            # concept to agents); older code only handled ``name`` /
            # ``check`` and silently dropped ``kind``, pushing the
            # whole ValidationBatch into a lossy LLM-repair roundtrip.
            _apply_synonyms(check, _PROACTIVE_CHECK_SYNONYMS)
            slug = check.get("slug") or f"unknown_{i}"
            result = check.get("result")
            # Flat-shape salvage: agents routinely emit a ProactiveCheck
            # with ValidationResult fields at the top level (command,
            # stdout_excerpt, exit_code, runtime_seconds, confidence,
            # etc.) instead of nesting them under a ``result`` dict.
            # Lift those top-level keys into a synthetic result dict
            # so the schema validates the actual payload, not an
            # empty placeholder.
            if not isinstance(result, dict):
                if any(k in check for k in _VR_FIELD_KEYS):
                    result = {}
                    for k in list(check.keys()):
                        if k in _VR_FIELD_KEYS and k != "slug":
                            result[k] = check.pop(k)
                else:
                    result = (
                        {"outcome": str(result)} if result is not None
                        else {}
                    )
            # Apply ValidationResult synonyms so status → verdict,
            # outcome → verdict, conf → confidence, etc. translate
            # cleanly before backfill. Nothing here overwrites an
            # already-present canonical key.
            _apply_synonyms(result, _VALIDATION_RESULT_SYNONYMS)
            result.setdefault("id", f"p_{slug}_{i}")
            result.setdefault("finding_id", "")
            result.setdefault("verdict", "inconclusive")
            if not result.get("method"):
                outcome = result.get("outcome")
                # If the agent stuffed narrative text into a
                # top-level ``findings`` key (common validator drift),
                # use it as the method description.
                findings_text = result.get("findings")
                if isinstance(findings_text, str) and findings_text.strip():
                    result["method"] = findings_text[:400]
                elif outcome:
                    result["method"] = (
                        f"proactive {slug}: {outcome}"
                    )[:400]
                else:
                    result["method"] = f"proactive {slug}"
            result.setdefault("confidence", 0.5)
            check["result"] = _backfill_validation_result(result, i)
            cleaned.append(check)
        obj["proactive"] = cleaned

    new_findings = obj.get("new_findings")
    if isinstance(new_findings, list):
        obj["new_findings"] = [
            _backfill_audit_finding(f, i)
            for i, f in enumerate(new_findings)
            if isinstance(f, dict)
        ]

    return obj


def normalize_validation_batch_drop_new_findings(obj: dict) -> dict:
    """Last-resort salvage: normalize, then strip ``new_findings``.

    Used by the Validator salvage path when the full ValidationBatch
    fails pydantic validation even after full normalization. The
    ``new_findings`` field is a SECONDARY bonus output; if the only
    thing keeping the batch from validating is a malformed bonus
    finding, drop the whole bonus list rather than lose the paid-for
    ``results`` + ``proactive`` payload.
    """
    obj = normalize_validation_batch(obj)
    if isinstance(obj, dict):
        obj["new_findings"] = []
    return obj


def _backfill_validation_result(r: dict, i: int) -> dict:
    # Apply ValidationResult synonyms FIRST so status→verdict etc.
    # rename before we default the canonical keys — otherwise a
    # defaulted "inconclusive" would clobber the agent's "confirmed".
    _apply_synonyms(r, _VALIDATION_RESULT_SYNONYMS)
    # Every required ValidationResult field gets a sensible default so
    # a single missing key on one result doesn't reject the whole
    # batch. The Validator's expensive work is in the results it did
    # produce — we'd rather surface a partial result than lose them all.
    r.setdefault("id", f"v_{i}")
    # finding_id: setdefault would keep an explicit ``None``, but the
    # schema requires a string. Observed in the wild when a validator
    # emits a proactive/aggregate result with no single target finding
    # ("v_23_data_structure_splits": finding_id=null). Coerce null to
    # empty string so the whole batch isn't rejected for one untethered
    # result.
    if r.get("finding_id") is None:
        r["finding_id"] = ""
    r.setdefault("verdict", "inconclusive")
    r.setdefault("method", "(method not emitted)")
    if r.get("confidence") is None:
        r["confidence"] = 0.5
    _fixup_validation_result(r)
    return r


def _backfill_audit_finding(f: dict, i: int) -> dict:
    # new_findings is a SECONDARY output — the Validator emits these as
    # bonus observations on top of its main validation work. Agents
    # routinely drop required fields here (id/category/severity/
    # description) because they treat it as free-form commentary.
    # Backfill every required field with a safe default so the bonus
    # finding survives — or gets downgraded to an obvious placeholder —
    # instead of killing the whole ValidationBatch.
    f.setdefault("id", f"f_validator_new_{i}")
    f.setdefault("category", "other")  # _coerce_category maps to OTHER
    f.setdefault("severity", "info")
    title = f.get("title") or "(untitled finding from validator)"
    f["title"] = title[:160]
    if not f.get("description"):
        f["description"] = title
    f.setdefault("detector", "validator")
    if f.get("confidence") is None:
        f["confidence"] = 0.5
    return f


def _fixup_validation_result(r) -> None:
    if not isinstance(r, dict):
        return
    method = r.get("method")
    if isinstance(method, str) and len(method) > 400:
        r["method"] = method[:400]
    conf = r.get("confidence")
    if isinstance(conf, (int, float)):
        if conf < 0:
            r["confidence"] = 0.0
        elif conf > 1:
            r["confidence"] = 1.0


def normalize_reviewer_report(
    obj: dict,
    *,
    audit_id: str,
    generated_at: str,
    eda_fallback: Optional[dict] = None,
    auditor_findings: Optional[list[dict]] = None,
    validator_new_findings: Optional[list[dict]] = None,
    validation_results: Optional[list[dict]] = None,
) -> dict:
    """Coerce common Reviewer output drift into a DiagnosticReport dict.

    Handles, without re-prompting the model:
      - Top-level alias renames: ``overall_confidence`` → ``confidence``,
        ``config_discrepancies`` → ``config_comparison``.
      - Missing required fields: stamp ``audit_id`` and
        ``generated_at`` from pipeline context.
      - Verdict casing: the schema validator already does a
        case-insensitive match, but lowercasing here keeps downstream
        comparisons predictable.
      - Missing ``headline``: derive from the first line of
        ``executive_summary`` (≤ 1000 chars).
      - Per-list-entry synonym translation for ``findings``,
        ``claim_verifications``, ``config_comparison``,
        ``recommendations``, ``unresolved_disagreements``. Uses
        comprehensive alias maps (see ``_FINDING_SYNONYMS`` etc.)
        so agent emissions like ``field`` → ``parameter``, ``agrees``
        → ``match``, ``priority`` → ``rank``, ``suggested_fix`` →
        ``suggested_fix_prose`` translate cleanly before validation.
      - ``eda_summary`` missing: backfill from ``eda_fallback``
        (typically the Auditor's ``findings.eda``) so the report
        surfaces dataset stats the Auditor already computed.

    The synonym translation is LOAD-BEARING: a single unhandled key
    rename on a single list-entry field used to reject the whole
    report into a truncated LLM-repair roundtrip that silently lost
    most findings/recommendations/severity_counts. The comprehensive
    synonym map makes that class of bug unreachable for any key we've
    observed; the parse_json_output salvage pass is a backstop for
    any that slip through.

    Unrecognized keys pass through; ``DiagnosticReport`` uses
    ``extra="ignore"``.
    """
    if not isinstance(obj, dict):
        return obj

    _rename_if_missing(obj, "overall_confidence", "confidence")
    _rename_if_missing(obj, "config_discrepancies", "config_comparison")

    obj.setdefault("audit_id", audit_id)
    obj.setdefault("generated_at", generated_at)

    if obj.get("eda_summary") is None and eda_fallback:
        obj["eda_summary"] = eda_fallback

    # Findings: rename every observed agent-side alias to the schema's
    # canonical name. Without this, ``suggested_fix`` silently drops
    # (schema has ``suggested_fix_prose``), and any agent that uses
    # ``finding_id`` instead of ``id`` loses the whole entry to a
    # required-field error.
    findings = obj.get("findings")
    if isinstance(findings, list):
        for f in findings:
            if not isinstance(f, dict):
                continue
            _apply_synonyms(f, _FINDING_SYNONYMS)
            # code_span nested renames: agents emit {file, start,
            # end} instead of {file_path, line_start, line_end}.
            span = f.get("code_span")
            if isinstance(span, dict):
                _apply_synonyms(span, {
                    "file_path": ("file", "path", "filename"),
                    "line_start": (
                        "start", "start_line", "line", "line_number",
                    ),
                    "line_end": ("end", "end_line"),
                })

    # Claim verifications: rename status synonyms (verdict/outcome/
    # result → status) and supporting_finding_ids → linked_finding_ids.
    # The ``supporting_finding_ids`` drift is the single most common
    # reviewer-output rename for claim verifications.
    cvs = obj.get("claim_verifications")
    if isinstance(cvs, list):
        for cv in cvs:
            if not isinstance(cv, dict):
                continue
            _apply_synonyms(cv, _CLAIM_VERIFICATION_SYNONYMS)

    # Deterministic claim ↔ finding join. The reviewer agent is supposed
    # to populate ``linked_finding_ids`` and flip ``status`` off the
    # default "unchecked" when findings reference a claim via
    # ``paper_claim_refs`` and the validator gave those findings a
    # verdict. In practice it frequently doesn't — we've observed
    # audits where 20 of 22 claim_verifications were stamped "unchecked"
    # despite the join data sitting on disk. This post-pass wires it up
    # so the UI reflects the evidence the pipeline already produced.
    if auditor_findings is not None or validator_new_findings is not None:
        _link_claim_verifications(
            obj,
            auditor_findings=auditor_findings or [],
            validator_new_findings=validator_new_findings or [],
            validation_results=validation_results or [],
        )

    # Unresolved disagreements: agents emit ``auditor_position`` /
    # ``validator_position`` as nested dicts (claim+evidence+confidence)
    # instead of the flat ``auditor_verdict`` / ``validator_verdict``
    # strings the schema declares. The schema now stringifies dict
    # values, but the rename has to happen before field-level
    # coercion sees the value under the wrong key.
    disagreements = obj.get("unresolved_disagreements")
    if isinstance(disagreements, list):
        for d in disagreements:
            if not isinstance(d, dict):
                continue
            _apply_synonyms(d, _DISAGREEMENT_SYNONYMS)
            d.setdefault("exposed_in_report", True)

    recs = obj.get("recommendations")
    if isinstance(recs, list):
        for i, rec in enumerate(recs):
            if not isinstance(rec, dict):
                continue
            # Apply synonyms BEFORE the rank/title fallback. The
            # ordering is load-bearing: _RECOMMENDATION_SYNONYMS maps
            # ``priority`` → ``rank``; if we defaulted ``rank`` to
            # ``i + 1`` first, the rename would be a no-op (canonical
            # already present) and the agent's intended order would
            # be discarded.
            _apply_synonyms(rec, _RECOMMENDATION_SYNONYMS)
            if "rank" not in rec or rec.get("rank") is None:
                rec["rank"] = i + 1
            action = rec.get("action")
            if not rec.get("title"):
                if isinstance(action, str) and action.strip():
                    first_sentence = action.strip().split(". ")[0]
                    rec["title"] = first_sentence[:160]
                else:
                    rec["title"] = f"Recommendation {i + 1}"
            if not rec.get("rationale"):
                if isinstance(action, str):
                    rec["rationale"] = action
                else:
                    rec["rationale"] = rec.get("title", "")

    verdict = obj.get("verdict")
    if isinstance(verdict, str) and verdict != verdict.lower():
        obj["verdict"] = verdict.lower()

    if not obj.get("headline"):
        summary = obj.get("executive_summary", "")
        if isinstance(summary, str) and summary.strip():
            first_line = summary.strip().split("\n\n")[0].split("\n")[0]
            obj["headline"] = first_line[:1000]

    # ConfigDiscrepancy: rename synonyms (field/key/name → parameter,
    # agrees/ok → match, finding_ids → linked_finding_ids), then
    # coerce severity to a valid enum value. The ``field`` → ``parameter``
    # rename is the single most-common reviewer-output drift — missing
    # it for one audit turns the whole report into the truncated-repair
    # fallback where findings/recommendations/severity_counts vanish.
    valid_severities = {"critical", "high", "medium", "low", "info"}
    config = obj.get("config_comparison")
    if isinstance(config, list):
        for item in config:
            if not isinstance(item, dict):
                continue
            _apply_synonyms(item, _CONFIG_COMPARISON_SYNONYMS)
            sev = item.get("severity")
            if isinstance(sev, str):
                lowered = sev.strip().lower()
                if lowered in valid_severities:
                    item["severity"] = lowered
                else:
                    item["severity"] = "info"
            elif sev is None and "severity" in item:
                item["severity"] = "info"

    # Defensive: backfill any list/dict field the schema requires with
    # a safe default. Reviewer output on degenerate inputs (empty
    # findings, empty validation) sometimes drops these entirely,
    # which would otherwise crash validation and force the
    # deterministic fallback.
    for list_field in (
        "claim_verifications",
        "findings",
        "config_comparison",
        "recommendations",
        "unresolved_disagreements",
    ):
        if obj.get(list_field) is None:
            obj[list_field] = []

    if obj.get("severity_counts") is None:
        obj["severity_counts"] = {}

    # ``confidence`` sometimes comes back as ``null`` when the agent
    # wasn't sure. Default to 0 (lowest) so the Reviewer's uncertainty
    # is reflected honestly.
    if obj.get("confidence") is None:
        obj["confidence"] = 0.0

    # Clamp confidence to [0, 1] — agents occasionally emit 1.5 or
    # negative-zero weirdness.
    conf = obj.get("confidence")
    if isinstance(conf, (int, float)):
        if conf < 0:
            obj["confidence"] = 0.0
        elif conf > 1:
            obj["confidence"] = 1.0

    return obj


def _link_claim_verifications(
    obj: dict,
    *,
    auditor_findings: list[dict],
    validator_new_findings: list[dict],
    validation_results: list[dict],
) -> None:
    """Populate ``linked_finding_ids`` and upgrade ``status`` from
    ``unchecked`` for every claim_verification whose evidence is
    already in the auditor's findings + validator's verdicts.

    Status mapping (only applied if reviewer left the row at
    ``unchecked`` — explicit reviewer verdicts always win):
      - any linked finding ``confirmed`` by the validator
        → ``not_verified`` (a real problem with the claim exists)
      - all linked findings ``denied`` (auditor was wrong)
        → ``verified`` (every flagged problem turned out to be a
        false alarm, so the claim holds up)
      - mix of denied + inconclusive / unverifiable
        → ``partial``
      - linked findings exist but none have a validator verdict
        → leave as ``unchecked`` (we only have suspicion, not evidence)
    """
    cvs = obj.get("claim_verifications")
    if not isinstance(cvs, list) or not cvs:
        return

    # claim_id → [finding_id]
    claim_to_findings: dict[str, list[str]] = {}
    for f in list(auditor_findings) + list(validator_new_findings):
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        if not isinstance(fid, str) or not fid:
            continue
        for claim_id in f.get("paper_claim_refs") or []:
            if isinstance(claim_id, str) and claim_id:
                claim_to_findings.setdefault(claim_id, []).append(fid)

    # finding_id → verdict (lowercased)
    finding_verdict: dict[str, str] = {}
    for vr in validation_results:
        if not isinstance(vr, dict):
            continue
        fid = vr.get("finding_id")
        verdict = vr.get("verdict")
        if isinstance(fid, str) and isinstance(verdict, str):
            finding_verdict[fid] = verdict.strip().lower()

    _UNCHECKED_ALIASES = {"", "unchecked", "unknown", "not_evaluated", "pending"}

    for cv in cvs:
        if not isinstance(cv, dict):
            continue
        claim_id = cv.get("claim_id")
        if not isinstance(claim_id, str):
            continue
        linked = claim_to_findings.get(claim_id, [])
        if not linked:
            continue

        existing = cv.get("linked_finding_ids")
        existing_list = existing if isinstance(existing, list) else []
        seen: set[str] = set()
        merged: list[str] = []
        for fid in list(existing_list) + linked:
            if isinstance(fid, str) and fid and fid not in seen:
                seen.add(fid)
                merged.append(fid)
        cv["linked_finding_ids"] = merged

        status = cv.get("status")
        status_l = status.strip().lower() if isinstance(status, str) else ""
        if status_l not in _UNCHECKED_ALIASES:
            continue  # reviewer was explicit — respect it

        verdicts = [finding_verdict[f] for f in linked if f in finding_verdict]
        if not verdicts:
            continue  # no validator signal; leave "unchecked"
        if any(v == "confirmed" for v in verdicts):
            cv["status"] = "not_verified"
        elif all(v == "denied" for v in verdicts):
            cv["status"] = "verified"
        else:
            cv["status"] = "partial"


def _rename_if_missing(obj: dict, src: str, dst: str) -> None:
    if src in obj and dst not in obj:
        obj[dst] = obj.pop(src)


def _extract_json(text: str) -> Optional[str]:
    decoder = json.JSONDecoder()
    idx = 0
    best: Optional[str] = None
    while idx < len(text):
        pos = text.find("{", idx)
        if pos == -1:
            break
        try:
            _, end = decoder.raw_decode(text, pos)
            best = text[pos:end]
            idx = end
        except json.JSONDecodeError:
            idx = pos + 1
    return best
