from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from backend.config import Settings
from backend.errors import InputError
from backend.schemas.inputs import (
    AuditRequest,
    CodeSourceGit,
    CodeSourceLocal,
    DataSourceBundled,
    DataSourceLocal,
    DataSourceSkip,
    DataSourceUrl,
    PaperSourceArxiv,
    PaperSourceNone,
    PaperSourcePdfUrl,
    PaperSourceRawText,
    PaperSourceUpload,
)
from backend.tools.arxiv import parse_arxiv_url, pdf_url_for
from backend.tools.github import clone_repo
from backend.tools.http_fetch import fetch_to_disk

_UPLOAD_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_MAX_PAPER_BYTES = 50 * 1024 * 1024  # 50 MB cap per §4.2
_MAX_REPO_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB cap per §6.2

# Hosts that look like "I have a download link" but actually serve
# HTML interstitials / auth walls instead of file bytes. We reject
# these at submit time so users don't burn their audit budget on a
# doomed download.
_BLOCKED_DATA_HOSTS = (
    "drive.google.com",
    "docs.google.com",
    "www.dropbox.com",
    "dropbox.com",
    "www.sharepoint.com",
    "sharepoint.com",
    "onedrive.live.com",
    "1drv.ms",
    "mega.nz",
    "mega.co.nz",
)

# Users frequently paste paths that were shell-escaped (``\ `` for
# spaces) or wrapped in quotes — Python's ``Path`` keeps them
# verbatim, so ``/Volumes/My\ Passport/...`` comes through with
# literal backslashes and never matches anything on disk. This regex
# strips a single backslash before any character (``\ `` → space,
# ``\(`` → ``(`` etc.), which covers the common shell escapes
# without mangling legitimate content.
_SHELL_ESCAPE_RE = re.compile(r"\\(.)")


def _sanitize_local_path(p: Path) -> Path:
    """Un-shell-escape and clean up a user-supplied local path.

    Handles:
      - leading / trailing whitespace (copy-paste tails)
      - surrounding single or double quotes
      - shell-style backslash escapes (``\\ ``, ``\\(``, ``\\'``, etc.)
      - tilde expansion (``~/data`` → ``$HOME/data``)

    If the caller passes a well-formed path the function is a no-op
    except for whitespace / quote stripping, so it's always safe to
    run before the existence check.
    """
    s = str(p).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    s = _SHELL_ESCAPE_RE.sub(r"\1", s)
    return Path(s).expanduser()


@dataclass
class NormalizedPaths:
    # paper_path is None when the user chose code-only audit
    # (PaperSourceNone). The pipeline skips the Paper Analyst phase.
    paper_path: Optional[Path]
    repo_path: Path
    data_path: Optional[Path]
    source_summary: str


class Normalizer:
    """Resolve an ``AuditRequest`` to concrete on-disk paths."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client

    async def normalize(
        self, audit_id: str, request: AuditRequest
    ) -> NormalizedPaths:
        root = self._settings.data_root_path() / "audits" / audit_id
        root.mkdir(parents=True, exist_ok=True)

        paper_path = await self._resolve_paper(root, request)
        repo_path = await self._resolve_repo(root, request)
        data_path = await self._resolve_data(root, repo_path, request)

        return NormalizedPaths(
            paper_path=paper_path,
            repo_path=repo_path,
            data_path=data_path,
            source_summary=self._summarize(request),
        )

    # ---- paper ----

    async def _resolve_paper(
        self, root: Path, request: AuditRequest
    ) -> Optional[Path]:
        src = request.paper

        if isinstance(src, PaperSourceNone):
            return None

        if isinstance(src, PaperSourceArxiv):
            ref = parse_arxiv_url(str(src.arxiv_url))
            return await fetch_to_disk(
                pdf_url_for(ref),
                root / "paper.pdf",
                max_bytes=_MAX_PAPER_BYTES,
                allowed_content_types=("application/pdf",),
                client=self._http_client,
            )

        if isinstance(src, PaperSourcePdfUrl):
            return await fetch_to_disk(
                str(src.url),
                root / "paper.pdf",
                max_bytes=_MAX_PAPER_BYTES,
                allowed_content_types=("application/pdf",),
                client=self._http_client,
            )

        if isinstance(src, PaperSourceUpload):
            if not _UPLOAD_ID_RE.match(src.upload_id):
                raise InputError(
                    f"invalid upload_id format: {src.upload_id!r}"
                )
            upload_path = (
                self._settings.data_root_path()
                / "uploads"
                / f"{src.upload_id}.pdf"
            )
            if not upload_path.exists():
                raise InputError(
                    f"upload not found: {src.upload_id!r}",
                    details={"upload_id": src.upload_id},
                )
            dest = root / "paper.pdf"
            shutil.copyfile(upload_path, dest)
            return dest

        if isinstance(src, PaperSourceRawText):
            dest = root / "paper.txt"
            dest.write_text(src.text, encoding="utf-8")
            return dest

        raise InputError(f"unknown paper source: {type(src).__name__}")

    # ---- code ----

    async def _resolve_repo(
        self, root: Path, request: AuditRequest
    ) -> Path:
        src = request.code
        dest = root / "repo"

        if isinstance(src, CodeSourceGit):
            return await clone_repo(
                str(src.url),
                dest,
                ref=src.ref,
                depth=1,
                timeout=300,
                max_bytes=_MAX_REPO_BYTES,
            )

        if isinstance(src, CodeSourceLocal):
            path = _sanitize_local_path(src.path)
            if not path.is_absolute():
                raise InputError(
                    f"local code path must be absolute: {path!r}"
                )
            if not path.exists():
                raise InputError(
                    f"local code path does not exist: {str(path)!r} "
                    f"(original input: {str(src.path)!r})"
                )
            if not path.is_dir():
                raise InputError(
                    f"local code path is not a directory: {path!r}"
                )
            shutil.copytree(
                path,
                dest,
                symlinks=False,
                dirs_exist_ok=False,
                ignore=shutil.ignore_patterns(
                    ".git", "__pycache__", ".venv", "node_modules"
                ),
            )
            return dest

        raise InputError(f"unknown code source: {type(src).__name__}")

    # ---- data ----

    async def _resolve_data(
        self,
        root: Path,
        repo_path: Path,
        request: AuditRequest,
    ) -> Optional[Path]:
        src = request.data

        if isinstance(src, DataSourceSkip):
            return None

        if isinstance(src, DataSourceLocal):
            path = _sanitize_local_path(src.path)
            if not path.is_absolute():
                raise InputError(
                    f"local data path must be absolute: {path!r}"
                )
            if not path.exists():
                raise InputError(
                    f"local data path does not exist: {str(path)!r} "
                    f"(original input: {str(src.path)!r})"
                )
            return path

        if isinstance(src, DataSourceBundled):
            if src.subpath:
                p = repo_path / src.subpath
                if not p.exists():
                    raise InputError(
                        f"bundled data subpath not found: {src.subpath!r}",
                        details={"subpath": src.subpath},
                    )
                return p
            return repo_path

        if isinstance(src, DataSourceUrl):
            max_bytes = int(
                self._settings.MAX_DATA_DOWNLOAD_GB * 1024 * 1024 * 1024
            )
            await self._preflight_data_url(str(src.url), max_bytes)
            return await fetch_to_disk(
                str(src.url),
                root / "data.bin",
                max_bytes=max_bytes,
                client=self._http_client,
            )

        raise InputError(f"unknown data source: {type(src).__name__}")

    async def _preflight_data_url(self, url: str, max_bytes: int) -> None:
        """HEAD the URL before committing to a full stream download.

        Blocks three failure modes up-front so we don't burn the
        audit budget on a doomed request:
          - Known HTML-interstitial hosts (GDrive, Dropbox shares,
            SharePoint, OneDrive, Mega) — fail fast with a clear
            "use S3/HF/R2 instead" message.
          - ``Content-Length`` already exceeds ``max_bytes``.
          - ``Content-Type: text/html`` (means we'd be downloading
            a web page, not a dataset).

        Missing headers / servers that don't support HEAD are treated
        as "proceed" — we'd rather try and fail during streaming than
        refuse a legit URL. Network / timeout errors ALSO fall through;
        ``fetch_to_disk`` will surface them with better error messages.
        """
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
        for blocked in _BLOCKED_DATA_HOSTS:
            if host == blocked or host.endswith("." + blocked):
                raise InputError(
                    f"{host} links aren't direct downloads — they serve "
                    "an HTML interstitial or auth wall that `curl` can't "
                    "follow inside the audit sandbox. Host the file at "
                    "an auth-free direct-download URL instead "
                    "(HuggingFace dataset, S3 presigned URL, Cloudflare "
                    "R2 public bucket, or a plain HTTP server).",
                    details={"host": host, "url": url},
                )

        owned = self._http_client is None
        client = self._http_client or httpx.AsyncClient(
            timeout=10.0, follow_redirects=True
        )
        try:
            try:
                resp = await client.head(url)
            except httpx.HTTPError:
                # Servers that don't answer HEAD are common; let the
                # streaming GET handle the real errors.
                return

            if resp.status_code >= 400:
                # Some servers 405 HEAD but allow GET. Don't block on
                # 4xx here; the streaming fetch will raise a better
                # error if the GET also fails.
                if resp.status_code != 405:
                    return

            ctype = resp.headers.get("content-type", "").lower()
            if ctype.startswith("text/html"):
                raise InputError(
                    f"URL serves HTML ({ctype!r}), not a data file. "
                    "This usually means a share page / interstitial. "
                    "Use a direct-download URL instead.",
                    details={"content_type": ctype, "url": url},
                )

            cl = resp.headers.get("content-length")
            if cl and cl.isdigit():
                size = int(cl)
                if size > max_bytes:
                    mb = max_bytes / (1024 * 1024)
                    raise InputError(
                        f"URL reports {size:,} bytes; the audit download "
                        f"cap is {mb:.0f} MB. The Validator has ~10 min "
                        "to download + audit, so bigger isn't always "
                        "better — host a representative sample instead.",
                        details={
                            "content_length": size,
                            "max_bytes": max_bytes,
                            "url": url,
                        },
                    )
        finally:
            if owned:
                await client.aclose()

    # ---- helpers ----

    @staticmethod
    def _summarize(request: AuditRequest) -> str:
        parts: list[str] = []
        paper = request.paper
        if isinstance(paper, PaperSourceArxiv):
            parts.append(f"paper=arxiv({paper.arxiv_url})")
        elif isinstance(paper, PaperSourcePdfUrl):
            parts.append(f"paper=pdf({paper.url})")
        elif isinstance(paper, PaperSourceUpload):
            parts.append(f"paper=upload({paper.upload_id})")
        elif isinstance(paper, PaperSourceRawText):
            parts.append("paper=raw_text")
        elif isinstance(paper, PaperSourceNone):
            parts.append("paper=none (code-only audit)")

        code = request.code
        if isinstance(code, CodeSourceGit):
            parts.append(f"code=git({code.url})")
        elif isinstance(code, CodeSourceLocal):
            parts.append(f"code=local({code.path})")

        data = request.data
        if isinstance(data, DataSourceSkip):
            parts.append("data=skip")
        elif isinstance(data, DataSourceLocal):
            parts.append(f"data=local({data.path})")
        elif isinstance(data, DataSourceBundled):
            parts.append(f"data=bundled({data.subpath or '/'})")
        elif isinstance(data, DataSourceUrl):
            parts.append(f"data=url({data.url})")

        return " | ".join(parts)
