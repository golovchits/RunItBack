from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import Field, HttpUrl

from .common import Strict


class PaperSourceArxiv(Strict):
    kind: Literal["arxiv"] = "arxiv"
    arxiv_url: HttpUrl


class PaperSourcePdfUrl(Strict):
    kind: Literal["pdf_url"] = "pdf_url"
    url: HttpUrl


class PaperSourceUpload(Strict):
    kind: Literal["upload"] = "upload"
    upload_id: str


class PaperSourceRawText(Strict):
    kind: Literal["raw_text"] = "raw_text"
    text: str = Field(min_length=500, max_length=500_000)
    title_hint: Optional[str] = None


class PaperSourceNone(Strict):
    """Code-only audit — no paper is provided.

    The pipeline skips the Paper Analyst phase entirely and runs the
    Code & Data Auditor / Validator / Reviewer against general ML-
    methodology checks (no paper-vs-code claim verification).
    """

    kind: Literal["none"] = "none"
    title_hint: Optional[str] = None


PaperSource = Annotated[
    Union[
        PaperSourceArxiv,
        PaperSourcePdfUrl,
        PaperSourceUpload,
        PaperSourceRawText,
        PaperSourceNone,
    ],
    Field(discriminator="kind"),
]


class CodeSourceGit(Strict):
    kind: Literal["git"] = "git"
    url: HttpUrl
    ref: Optional[str] = None


class CodeSourceLocal(Strict):
    kind: Literal["local"] = "local"
    path: Path


CodeSource = Annotated[
    Union[CodeSourceGit, CodeSourceLocal],
    Field(discriminator="kind"),
]


class DataSourceLocal(Strict):
    kind: Literal["local"] = "local"
    path: Path


class DataSourceUrl(Strict):
    kind: Literal["url"] = "url"
    url: HttpUrl
    expected_size_gb: Optional[float] = None


class DataSourceBundled(Strict):
    kind: Literal["bundled"] = "bundled"
    subpath: Optional[str] = None


class DataSourceSkip(Strict):
    kind: Literal["skip"] = "skip"


DataSource = Annotated[
    Union[DataSourceLocal, DataSourceUrl, DataSourceBundled, DataSourceSkip],
    Field(discriminator="kind"),
]


class AuditRequest(Strict):
    paper: PaperSource
    code: CodeSource
    data: DataSource
    timeout_minutes: int = Field(default=45, ge=5, le=120)
    force_fallback: bool = False
    include_eda: bool = True
    include_suggested_fixes: bool = True
    # Optional free-form hints from the user ("I suspect a leak in X",
    # "the checkpoint for Y might be corrupt"). Agents are instructed
    # to treat these with skepticism — not ground truth.
    user_notes: Optional[str] = Field(default=None, max_length=5000)
    # Optional pasted `tree`/`find` output describing the dataset
    # directory structure. Orthogonal to ``data`` — a user can point
    # ``data`` at a URL/bundle AND paste the full-dataset tree here
    # to get split-balance + filename-collision + extension-
    # consistency checks even when only a sample is available to
    # download. Max 200 KB keeps the Validator's context window sane.
    data_structure_text: Optional[str] = Field(
        default=None, max_length=200_000
    )


AuditPhase = Literal[
    "created",
    "normalizing",
    "paper_analyst",
    "code_auditor",
    "validator",
    "reviewer",
    "done",
    "failed",
]

RuntimeMode = Literal["managed_agents", "messages_api"]


class AuditRecord(Strict):
    id: str
    request: AuditRequest
    created_at: str
    phase: AuditPhase
    runtime_mode: RuntimeMode
    repo_path: Optional[Path] = None
    paper_path: Optional[Path] = None
    data_path: Optional[Path] = None
    artifact_paths: dict[str, Path] = Field(default_factory=dict)
    error: Optional[str] = None
