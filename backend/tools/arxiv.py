from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from backend.errors import InputError

_ARXIV_HOSTS = ("arxiv.org", "www.arxiv.org", "export.arxiv.org")
_NEW_ID_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
_OLD_ID_RE = re.compile(r"^([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$")


@dataclass(frozen=True)
class ArxivRef:
    id: str
    version: Optional[str] = None

    @property
    def canonical_id(self) -> str:
        return f"{self.id}{self.version or ''}"


def parse_arxiv_url(url_or_id: str) -> ArxivRef:
    """Parse an arXiv URL or bare ID into an ``ArxivRef``.

    Accepts: ``https://arxiv.org/pdf/2504.01848``,
    ``.../pdf/2504.01848.pdf``, ``arxiv:2504.01848v2``, bare IDs
    (``2504.01848``), and pre-2007 ``cs/0701001`` / ``cs.LG/0701001``.
    Rejects ``/abs/`` and ``/html/`` URL variants — only ``/pdf/`` is
    supported because the Paper Analyst ingests the raw PDF bytes.
    """
    s = url_or_id.strip()
    if not s:
        raise InputError("empty arXiv reference")

    if s.lower().startswith("arxiv:"):
        s = s[len("arxiv:"):].strip()
        if not s:
            raise InputError(f"empty arXiv reference: {url_or_id!r}")

    if "://" in s:
        parsed = urlparse(s)
        if parsed.scheme not in ("http", "https"):
            raise InputError(
                f"arXiv URL must use http/https, got {parsed.scheme!r}"
            )
        if parsed.hostname not in _ARXIV_HOSTS:
            raise InputError(f"not an arXiv URL: {url_or_id!r}")
        path = parsed.path or ""
        if path.startswith("/abs/") or path.startswith("/html/"):
            variant = "abs" if path.startswith("/abs/") else "html"
            raise InputError(
                f"arXiv /{variant}/ URLs are not supported — use the /pdf/ "
                f"variant (e.g. https://arxiv.org/pdf/2504.01848): {url_or_id!r}"
            )
        if path.startswith("/pdf/"):
            path = path[len("/pdf/"):]
        else:
            raise InputError(f"unrecognized arXiv URL path: {url_or_id!r}")
        path = path.strip("/")
        if path.endswith(".pdf"):
            path = path[:-4]
        s = path

    m = _NEW_ID_RE.match(s)
    if m:
        return ArxivRef(id=m.group(1), version=m.group(2))
    m = _OLD_ID_RE.match(s)
    if m:
        return ArxivRef(id=m.group(1), version=m.group(2))
    raise InputError(f"unparseable arXiv reference: {url_or_id!r}")


def pdf_url_for(ref: ArxivRef) -> str:
    """Canonical https PDF URL for the reference."""
    return f"https://arxiv.org/pdf/{ref.canonical_id}.pdf"
