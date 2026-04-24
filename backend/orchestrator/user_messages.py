from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from backend.errors import InputError
from backend.schemas.inputs import (
    CodeSource,
    CodeSourceGit,
    CodeSourceLocal,
    DataSource,
    DataSourceBundled,
    DataSourceLocal,
    DataSourceSkip,
    DataSourceUrl,
    PaperSource,
    PaperSourceRawText,
)


_USER_NOTES_CAVEAT = (
    "USER_NOTES (optional hints from the researcher who requested this "
    "audit — treat as LOW-TRUST suggestions, not ground truth; they may "
    "be wrong or biased. Verify any claim against the actual code or "
    "paper before acting on it):\n"
)


_DATA_STRUCTURE_CAVEAT = (
    "DATA_STRUCTURE_TEXT (pasted `tree`/`find` listing of the user's "
    "full dataset — the actual files may NOT be in your sandbox, but "
    "the structure is ground truth about splits, class folders, and "
    "filename conventions). Use it for:\n"
    "  - split balance (file count per split)\n"
    "  - filename collision across splits (leakage signal)\n"
    "  - extension consistency (do all files match claimed modality)\n"
    "  - missing or unexpected splits/folders\n"
    "  - class-imbalance hints when classes are folder-named\n"
    "Do NOT assume file contents; content-level checks stay with the "
    "primary data source (if any).\n"
)


def _user_notes_block(user_notes: Optional[str]) -> list[dict]:
    if not user_notes:
        return []
    return [
        {
            "type": "text",
            "text": f"{_USER_NOTES_CAVEAT}{user_notes}",
        }
    ]


def _data_structure_block(
    data_structure_text: Optional[str],
) -> list[dict]:
    if not data_structure_text:
        return []
    return [
        {
            "type": "text",
            "text": (
                f"{_DATA_STRUCTURE_CAVEAT}\n"
                f"{data_structure_text}"
            ),
        }
    ]


def build_paper_analyst_content(
    paper_path: Path,
    paper_source: PaperSource,
    audit_summary: str,
    user_notes: Optional[str] = None,
) -> list[dict]:
    """Build the Paper Analyst's user_content list.

    For PDF sources (arxiv, pdf_url, upload) the PDF at ``paper_path``
    becomes a ``document`` content block read natively by Opus 4.7's
    multimodal input. For raw-text sources, the text is inlined.
    """
    if isinstance(paper_source, PaperSourceRawText):
        return [
            {
                "type": "text",
                "text": (
                    f"{audit_summary}\n\n"
                    f"PAPER_RAW_TEXT:\n{paper_source.text}"
                ),
            },
            *_user_notes_block(user_notes),
        ]

    pdf_bytes = paper_path.read_bytes()
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    return [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": b64,
            },
        },
        {
            "type": "text",
            "text": (
                f"{audit_summary}\n\n"
                "Extract all verifiable claims from the attached paper "
                "and emit the final PaperClaims JSON."
            ),
        },
        *_user_notes_block(user_notes),
    ]


def build_readme_analyst_content(
    readme_text: str,
    *,
    title_hint: Optional[str],
    audit_summary: str,
    user_notes: Optional[str] = None,
) -> list[dict]:
    """Paper Analyst content for code-only audits with a repo README.

    When no paper is provided, the pipeline uses the repo's README as a
    weak claim source. We prefix a clear caveat so the agent knows it
    is NOT reading a formal paper and should not hallucinate claim
    tables that aren't literally stated.
    """
    title_line = f"\nTitle hint: {title_hint}" if title_hint else ""
    return [
        {
            "type": "text",
            "text": (
                f"{audit_summary}{title_line}\n\n"
                "SOURCE: REPO_README (not an academic paper).\n"
                "\n"
                "Extract ONLY verifiable claims explicitly stated in the "
                "README about metrics, datasets, architectures, training "
                "config, and evaluation protocol. Most claim lists will "
                "be empty and that is expected — do NOT speculate or fill "
                "from training data. Set `extraction_confidence` low "
                "(≤ 0.5 — the pipeline will cap it there anyway). Add "
                "'readme_derived' to `unresolved_questions` so downstream "
                "agents know the provenance.\n\n"
                f"PAPER_RAW_TEXT (repo README):\n{readme_text[:200_000]}"
            ),
        },
        *_user_notes_block(user_notes),
    ]


def build_code_auditor_content(
    code_source: CodeSource,
    data_source: DataSource,
    claims_json: str,
    manifest_json: str,
    audit_summary: str,
    user_notes: Optional[str] = None,
    data_structure_text: Optional[str] = None,
) -> list[dict]:
    clone_instructions = _code_source_instructions(code_source)
    data_instructions = _data_source_instructions(data_source)

    return [
        {
            "type": "text",
            "text": (
                f"{audit_summary}\n\n"
                f"{clone_instructions}\n\n"
                f"{data_instructions}\n\n"
                "Audit the paper's claims against the code's actual "
                "behavior. Emit the final AuditFindings JSON when done."
            ),
        },
        {"type": "text", "text": f"PAPER_CLAIMS_JSON:\n{claims_json}"},
        {"type": "text", "text": f"REPO_MANIFEST_JSON:\n{manifest_json}"},
        *_data_structure_block(data_structure_text),
        *_user_notes_block(user_notes),
    ]


def build_validator_content(
    code_source: CodeSource,
    data_source: DataSource,
    claims_json: str,
    findings_json: str,
    user_notes: Optional[str] = None,
    data_structure_text: Optional[str] = None,
) -> list[dict]:
    clone_instructions = _code_source_instructions(code_source)
    data_instructions = _data_source_instructions(data_source)

    return [
        {
            "type": "text",
            "text": (
                f"{clone_instructions}\n\n"
                f"{data_instructions}\n\n"
                "Run targeted checks and proactive validations against "
                "the Auditor's findings below. Emit the final "
                "ValidationBatch JSON when done."
            ),
        },
        {"type": "text", "text": f"PAPER_CLAIMS_JSON:\n{claims_json}"},
        {"type": "text", "text": f"AUDIT_FINDINGS_JSON:\n{findings_json}"},
        *_data_structure_block(data_structure_text),
        *_user_notes_block(user_notes),
    ]


def build_reviewer_content(
    claims_json: str,
    findings_json: str,
    validation_json: str,
    manifest_json: str,
    user_notes: Optional[str] = None,
) -> list[dict]:
    return [
        {
            "type": "text",
            "text": (
                "IMPORTANT — READ FIRST:\n"
                "All artifacts are provided INLINE in the text blocks "
                "below. The filesystem paths mentioned in your system "
                "prompt (e.g. /workspace/artifacts/*.json, "
                "/workspace/repo) do NOT exist in this session. "
                "Do NOT use bash, read, glob, or grep to look for "
                "files — they will not be there. Use ONLY the JSON "
                "content in the text blocks below.\n\n"
                "TASK: apply the cross-check rules to the four "
                "artifacts below and emit the final DiagnosticReport "
                "JSON as the last thing in your response."
            ),
        },
        {"type": "text", "text": f"PAPER_CLAIMS_JSON:\n{claims_json}"},
        {"type": "text", "text": f"AUDIT_FINDINGS_JSON:\n{findings_json}"},
        {"type": "text", "text": f"VALIDATION_BATCH_JSON:\n{validation_json}"},
        {"type": "text", "text": f"REPO_MANIFEST_JSON:\n{manifest_json}"},
        *_user_notes_block(user_notes),
    ]


def _code_source_instructions(src: CodeSource) -> str:
    if isinstance(src, CodeSourceGit):
        branch_flag = f" --branch {src.ref}" if src.ref else ""
        ref_note = f" (ref: {src.ref})" if src.ref else ""
        return (
            f"CODE SOURCE: Git repository{ref_note}\n"
            f"  url: {src.url}\n"
            f"  Clone it into /workspace/repo as your first step:\n"
            f"    git clone --depth 1{branch_flag} {src.url} /workspace/repo"
        )
    if isinstance(src, CodeSourceLocal):
        raise InputError(
            "local code paths are not yet supported; use a git URL"
        )
    raise InputError(f"unknown code source: {type(src).__name__}")


def _data_source_instructions(src: DataSource) -> str:
    if isinstance(src, DataSourceSkip):
        return "DATA SOURCE: SKIP_DATA_AUDIT (no data provided)"
    if isinstance(src, DataSourceBundled):
        subpath = src.subpath or ""
        return (
            f"DATA SOURCE: BUNDLED_IN_REPO:{subpath} "
            "(data lives inside the cloned repo at the given subpath)"
        )
    if isinstance(src, DataSourceUrl):
        return (
            f"DATA SOURCE: URL download required (/workspace/data)\n"
            f"  url: {src.url}\n"
            "  Download it to /workspace/data (size cap applies); "
            "use bash + curl."
        )
    if isinstance(src, DataSourceLocal):
        # Managed Agents runs in Anthropic's cloud and cannot mount the
        # user's host filesystem. Rather than kill the audit, we tell
        # the agent to treat the data input as skipped and to note the
        # gap in coverage_notes — the code-side audit still runs.
        # Self-hosted runtime (runtime mode A in ARCHITECTURE.md §7.4)
        # will support local paths natively; until then this is the
        # safest degrade path.
        return (
            "DATA SOURCE: LOCAL_PATH_NOT_MOUNTED "
            f"(user-provided path: {src.path}; not accessible from "
            "this sandbox). Treat as SKIP_DATA_AUDIT for data-side "
            "checks. In coverage_notes, record that the user's local "
            "dataset was not inspected and recommend bundling a "
            "sample into the repo or providing a download URL for "
            "full EDA coverage."
        )
    raise InputError(f"unknown data source: {type(src).__name__}")
