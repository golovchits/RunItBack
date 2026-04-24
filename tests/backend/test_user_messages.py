from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from backend.errors import InputError
from backend.orchestrator.user_messages import (
    build_code_auditor_content,
    build_paper_analyst_content,
    build_reviewer_content,
    build_validator_content,
)
from backend.schemas.inputs import (
    CodeSourceGit,
    CodeSourceLocal,
    DataSourceBundled,
    DataSourceLocal,
    DataSourceSkip,
    DataSourceUrl,
    PaperSourceArxiv,
    PaperSourcePdfUrl,
    PaperSourceRawText,
    PaperSourceUpload,
)


# ---- Paper Analyst ----


def test_paper_analyst_arxiv_produces_document_block(tmp_path: Path):
    pdf_bytes = b"%PDF-1.4 fake content"
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(pdf_bytes)

    content = build_paper_analyst_content(
        pdf,
        PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
        "AuditRequest: example",
    )
    assert len(content) == 2
    doc, text = content
    assert doc["type"] == "document"
    assert doc["source"]["type"] == "base64"
    assert doc["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(doc["source"]["data"]) == pdf_bytes
    assert text["type"] == "text"
    assert "AuditRequest: example" in text["text"]
    assert "PaperClaims JSON" in text["text"]


def test_paper_analyst_pdf_url_is_document_block(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-u")
    content = build_paper_analyst_content(
        pdf,
        PaperSourcePdfUrl(url="https://example.com/p.pdf"),
        "summary",
    )
    assert content[0]["type"] == "document"


def test_paper_analyst_upload_is_document_block(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-up")
    content = build_paper_analyst_content(
        pdf,
        PaperSourceUpload(upload_id="pdf_123"),
        "summary",
    )
    assert content[0]["type"] == "document"


def test_paper_analyst_raw_text_is_inline(tmp_path: Path):
    txt = tmp_path / "paper.txt"
    body = "x" * 600
    txt.write_text(body)

    content = build_paper_analyst_content(
        txt,
        PaperSourceRawText(text=body, title_hint="Test Paper"),
        "my-summary",
    )
    assert len(content) == 1
    assert content[0]["type"] == "text"
    assert "PAPER_RAW_TEXT:" in content[0]["text"]
    assert body in content[0]["text"]
    assert "my-summary" in content[0]["text"]


# ---- Code & Data Auditor ----


def test_code_auditor_content_structure():
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json='{"paper_title": "T"}',
        manifest_json='{"file_count": 42}',
        audit_summary="RunItBack audit",
    )
    assert len(content) == 3
    assert all(b["type"] == "text" for b in content)
    assert "git clone" in content[0]["text"]
    assert "https://github.com/a/b" in content[0]["text"]
    assert "RunItBack audit" in content[0]["text"]
    assert "PAPER_CLAIMS_JSON" in content[1]["text"]
    assert '"paper_title"' in content[1]["text"]
    assert "REPO_MANIFEST_JSON" in content[2]["text"]


def test_code_auditor_with_branch_ref():
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b", ref="dev"),
        DataSourceSkip(),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
    )
    assert "ref: dev" in content[0]["text"]
    assert "--branch dev" in content[0]["text"]


def test_code_auditor_with_bundled_data():
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceBundled(subpath="datasets/mnist"),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
    )
    assert "BUNDLED_IN_REPO:datasets/mnist" in content[0]["text"]


def test_code_auditor_with_url_data():
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceUrl(url="https://example.com/data.tar.gz"),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
    )
    assert "URL download required" in content[0]["text"]
    assert "https://example.com/data.tar.gz" in content[0]["text"]


def test_code_auditor_skip_data():
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
    )
    assert "SKIP_DATA_AUDIT" in content[0]["text"]


def test_code_auditor_rejects_local_code():
    with pytest.raises(InputError, match="local code paths"):
        build_code_auditor_content(
            CodeSourceLocal(path=Path("/abs/repo")),
            DataSourceSkip(),
            claims_json="{}",
            manifest_json="{}",
            audit_summary="",
        )


def test_code_auditor_local_data_degrades_to_skip_with_notice():
    """Local data paths can't mount into Managed Agents sandboxes —
    instead of killing the audit, we tell the agent to skip data
    checks and record the gap in coverage_notes."""
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceLocal(path=Path("/abs/data")),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
    )
    body = "\n".join(b["text"] for b in content)
    assert "LOCAL_PATH_NOT_MOUNTED" in body
    assert "SKIP_DATA_AUDIT" in body
    assert "/abs/data" in body
    assert "coverage_notes" in body


def test_validator_local_data_degrades_to_skip_with_notice():
    from backend.orchestrator.user_messages import build_validator_content
    content = build_validator_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceLocal(path=Path("/abs/data")),
        claims_json="{}",
        findings_json='{"findings": []}',
    )
    body = "\n".join(b["text"] for b in content)
    assert "LOCAL_PATH_NOT_MOUNTED" in body
    assert "SKIP_DATA_AUDIT" in body


def test_code_auditor_inlines_data_structure_text_when_provided():
    tree = "dataset/\n├── train/\n└── val/\n"
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
        data_structure_text=tree,
    )
    body = "\n".join(b["text"] for b in content)
    assert "DATA_STRUCTURE_TEXT" in body
    assert "dataset/" in body
    assert "train/" in body


def test_code_auditor_omits_structure_block_when_absent():
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
    )
    body = "\n".join(b["text"] for b in content)
    assert "DATA_STRUCTURE_TEXT" not in body


def test_validator_inlines_data_structure_text_when_provided():
    from backend.orchestrator.user_messages import build_validator_content
    tree = "dataset/\n├── train/class_a/ (2000 files)\n└── val/class_a/ (200 files)\n"
    content = build_validator_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json="{}",
        findings_json='{"findings": []}',
        data_structure_text=tree,
    )
    body = "\n".join(b["text"] for b in content)
    assert "DATA_STRUCTURE_TEXT" in body
    assert "filename collision" in body.lower() or "split" in body.lower()
    assert "class_a" in body


# ---- Validator ----


def test_validator_content_structure():
    content = build_validator_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json="{}",
        findings_json='{"findings": []}',
    )
    assert len(content) == 3
    assert "git clone" in content[0]["text"]
    assert "PAPER_CLAIMS_JSON" in content[1]["text"]
    assert "AUDIT_FINDINGS_JSON" in content[2]["text"]


def test_validator_rejects_local_code():
    with pytest.raises(InputError, match="local code paths"):
        build_validator_content(
            CodeSourceLocal(path=Path("/abs/repo")),
            DataSourceSkip(),
            claims_json="{}",
            findings_json="{}",
        )


# ---- Reviewer ----


def test_reviewer_content_structure():
    content = build_reviewer_content(
        claims_json='{"paper_title": "T"}',
        findings_json='{"findings": []}',
        validation_json='{"results": []}',
        manifest_json='{"file_count": 1}',
    )
    assert len(content) == 5
    assert all(b["type"] == "text" for b in content)
    assert "cross-check" in content[0]["text"].lower()
    joined = "\n".join(b["text"] for b in content)
    assert "PAPER_CLAIMS_JSON" in joined
    assert "AUDIT_FINDINGS_JSON" in joined
    assert "VALIDATION_BATCH_JSON" in joined
    assert "REPO_MANIFEST_JSON" in joined


def test_reviewer_has_no_git_instructions():
    content = build_reviewer_content(
        claims_json="{}",
        findings_json="{}",
        validation_json="{}",
        manifest_json="{}",
    )
    joined = "\n".join(b["text"] for b in content)
    assert "git clone" not in joined.lower()


# ---- Robustness ----


# ---- user_notes ----


def test_user_notes_appended_to_paper_analyst(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-x")
    content = build_paper_analyst_content(
        pdf,
        PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
        "summary",
        user_notes="I suspect the backbone is not actually frozen.",
    )
    joined = "\n".join(b["text"] for b in content if b.get("type") == "text")
    assert "USER_NOTES" in joined
    assert "LOW-TRUST" in joined
    assert "backbone" in joined


def test_user_notes_appended_to_code_auditor():
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
        user_notes="Train/test split may be leaky.",
    )
    joined = "\n".join(b["text"] for b in content)
    assert "USER_NOTES" in joined
    assert "leaky" in joined


def test_user_notes_appended_to_validator():
    content = build_validator_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json="{}",
        findings_json="{}",
        user_notes="Checkpoints might be broken.",
    )
    joined = "\n".join(b["text"] for b in content)
    assert "USER_NOTES" in joined
    assert "broken" in joined


def test_user_notes_appended_to_reviewer():
    content = build_reviewer_content(
        claims_json="{}",
        findings_json="{}",
        validation_json="{}",
        manifest_json="{}",
        user_notes="The headline number seemed high.",
    )
    joined = "\n".join(b["text"] for b in content)
    assert "USER_NOTES" in joined
    assert "headline number" in joined


def test_user_notes_omitted_when_none():
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json="{}",
        manifest_json="{}",
        audit_summary="",
        user_notes=None,
    )
    joined = "\n".join(b["text"] for b in content)
    assert "USER_NOTES" not in joined


def test_user_notes_skepticism_caveat_present():
    content = build_reviewer_content(
        claims_json="{}", findings_json="{}",
        validation_json="{}", manifest_json="{}",
        user_notes="anything",
    )
    joined = "\n".join(b["text"] for b in content)
    # The caveat should explicitly warn agents not to blindly trust the
    # user's input.
    assert "LOW-TRUST" in joined or "low-trust" in joined.lower()


def test_large_json_payloads_preserved():
    big_claims = json.dumps(
        {"metrics": [{"id": f"m{i:04d}"} for i in range(1000)]}
    )
    content = build_code_auditor_content(
        CodeSourceGit(url="https://github.com/a/b"),
        DataSourceSkip(),
        claims_json=big_claims,
        manifest_json="{}",
        audit_summary="",
    )
    assert big_claims in content[1]["text"]
