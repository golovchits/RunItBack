from __future__ import annotations

import pytest

from backend.agents.prompts import load_prompt

ROLES = ["paper_analyst", "code_auditor", "validator", "reviewer"]


@pytest.mark.parametrize("role", ROLES)
def test_load_prompt_substantial(role):
    p = load_prompt(role)
    assert p.strip()
    assert len(p) > 500, f"{role} prompt suspiciously short"


@pytest.mark.parametrize("role", ROLES)
def test_load_prompt_includes_preamble(role):
    p = load_prompt(role)
    assert "<identity>" in p
    assert "</identity>" in p
    assert "<global_rules>" in p


@pytest.mark.parametrize("role", ROLES)
def test_load_prompt_has_role_body(role):
    p = load_prompt(role)
    assert "<role>" in p
    assert "<output_format>" in p


def test_unknown_role_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent")  # type: ignore[arg-type]


def test_paper_analyst_pdf_document_pivot():
    # Verify the PDF-document-block language is present. The word
    # "pdftotext" appears intentionally, in the "do NOT run pdftotext"
    # negative instruction; what must be absent is the old command-line
    # usage that was the arch's original primary path.
    p = load_prompt("paper_analyst")
    assert "document" in p.lower()
    assert "multimodal" in p.lower()
    assert "pdftotext /workspace" not in p


def test_code_auditor_preproc_flag_swapped_category():
    p = load_prompt("code_auditor")
    assert "PREPROC_FLAG_SWAPPED" in p


def test_code_auditor_targeted_check_requests():
    p = load_prompt("code_auditor")
    assert "targeted_check_requests" in p


def test_validator_new_findings_in_output_format():
    p = load_prompt("validator")
    assert "new_findings" in p


def test_reviewer_cross_check_rules():
    p = load_prompt("reviewer")
    for rule_letter in ("Rule A", "Rule B", "Rule C", "Rule D", "Rule E", "Rule F", "Rule G"):
        assert rule_letter in p


def test_load_prompt_is_cached():
    a = load_prompt("paper_analyst")
    b = load_prompt("paper_analyst")
    assert a is b


def test_preamble_appears_before_role_body():
    p = load_prompt("paper_analyst")
    identity_end = p.index("</identity>")
    role_open = p.index("<role>")
    assert identity_end < role_open


# ---- drift-guard regression tests ----
#
# Every prompt must pin the most commonly-drifted field names so the
# agent doesn't reach for a natural-language alias that the parser
# has to untangle. These tests lock in the specific canonical-vs-alias
# pairs that have previously caused silent report truncation. If a
# future prompt edit drops one of these guards, the test fails loud.


def test_reviewer_prompt_pins_config_comparison_parameter():
    """`parameter` (not `field`) is the canonical key in every
    ConfigDiscrepancy. This drift is what collapsed audit 212b6ea4
    into a truncated-repair roundtrip that lost all findings."""
    p = load_prompt("reviewer")
    assert "`parameter`" in p and "NOT `field`" in p
    assert "NOT `agrees`" in p


def test_reviewer_prompt_pins_finding_fix_prose():
    p = load_prompt("reviewer")
    assert "suggested_fix_prose" in p
    assert "NOT `suggested_fix`" in p or "not `suggested_fix`" in p.lower()


def test_reviewer_prompt_pins_linked_finding_ids():
    p = load_prompt("reviewer")
    assert "linked_finding_ids" in p
    assert "supporting_finding_ids" in p  # called out as forbidden
    # The `priority` → `rank` rename for Recommendation
    assert "`rank`" in p and "NOT `priority`" in p


def test_reviewer_prompt_has_populated_example():
    """The minimal example must show POPULATED nested shapes. An
    example with empty lists leaves the agent guessing at nested
    keys — exactly how ConfigDiscrepancy.field and
    ClaimVerification.supporting_finding_ids slipped into the
    wild."""
    p = load_prompt("reviewer")
    # The example block should include a claim_verifications entry
    # with linked_finding_ids and a config_comparison entry with
    # parameter — i.e. not just empty arrays.
    assert '"linked_finding_ids":' in p
    assert '"parameter":' in p


def test_validator_prompt_pins_proactive_slug():
    """`slug` (not `kind`) is the canonical key for ProactiveCheck.
    Agents routinely reach for `kind` because the slug and the
    check kind are conceptually the same; missing this guard
    caused audit 212b6ea4's validator to under-report 10/22
    findings."""
    p = load_prompt("validator")
    assert "ProactiveCheck" in p
    assert "`slug`" in p
    assert "NOT `kind`" in p


def test_validator_prompt_has_proactive_correct_and_wrong_examples():
    """Both CORRECT and WRONG examples of ProactiveCheck must be
    present so the agent can pattern-match against the right
    shape. One example alone leaves the flat-shape drift
    available as an attractor."""
    p = load_prompt("validator")
    assert "CORRECT" in p
    assert "WRONG" in p or "do_not_emit" in p


def test_validator_prompt_pins_finding_id_empty_string():
    """finding_id on aggregate results must be ``""`` (empty
    string), not ``null``. Null-on-required-string kills the
    whole batch."""
    p = load_prompt("validator")
    # The prompt should spell out the empty-string requirement.
    assert "empty string" in p.lower() or '""' in p
    assert "null" in p.lower()


def test_code_auditor_prompt_has_inline_schema():
    """The Auditor prompt used to say 'Schema on disk at
    /workspace/schemas/findings.json' — but that file does NOT
    exist. Hunting for it wastes budget and can time out the
    whole audit. Inline schema must be present and the phantom
    disk reference must be gone."""
    p = load_prompt("code_auditor")
    assert "AuditFinding:" in p
    assert "CodeSpan:" in p
    assert "Evidence:" in p
    assert "/workspace/schemas/findings.json" not in p
    # Positive: warns against hunting for phantom files.
    assert "files do not exist" in p.lower() or (
        "no filesystem schema file exists" in p.lower()
    )


def test_validator_prompt_has_inline_schema():
    p = load_prompt("validator")
    assert "ValidationResult:" in p
    assert "ProactiveCheck" in p
    assert "/workspace/schemas/validation.json" not in p
    assert "files do not exist" in p.lower() or (
        "no filesystem schema file exists" in p.lower()
    )


def test_code_auditor_prompt_pins_suggested_fix_prose():
    """The Auditor emits findings that the Reviewer passes through
    unchanged. If the Auditor drifts on `suggested_fix` vs
    `suggested_fix_prose`, the fix suggestion silently drops."""
    p = load_prompt("code_auditor")
    assert "suggested_fix_prose" in p
    assert "NOT `suggested_fix`" in p


def test_code_auditor_prompt_pins_code_span_keys():
    p = load_prompt("code_auditor")
    assert "file_path" in p
    assert "line_start" in p and "line_end" in p
    # Common drift names called out as forbidden.
    assert "NOT `file`" in p or "not `file`" in p.lower()


def test_paper_analyst_prompt_pins_num_samples_total():
    p = load_prompt("paper_analyst")
    assert "num_samples_total" in p
    assert "NOT `n_samples`" in p


def test_paper_analyst_prompt_pins_extraction_confidence():
    p = load_prompt("paper_analyst")
    assert "extraction_confidence" in p
    assert "REQUIRED" in p
