from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import Settings
from backend.errors import InputError
from backend.orchestrator.normalizer import Normalizer
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


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        DATA_ROOT=tmp_path,
        ANTHROPIC_API_KEY="sk-ant-test",
    )


@pytest.fixture
def _mock_fetch_and_clone(monkeypatch):
    """Just the network tools — no preflight patching."""

    async def fake_fetch(url, dest, **_kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f"%PDF-fake:{url}".encode())
        return dest

    async def fake_clone(url, dest, **_kwargs):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "README.md").write_text(f"repo from {url}")
        (dest / "src").mkdir(exist_ok=True)
        (dest / "src" / "main.py").write_text("# cloned\n")
        return dest

    monkeypatch.setattr(
        "backend.orchestrator.normalizer.fetch_to_disk", fake_fetch
    )
    monkeypatch.setattr(
        "backend.orchestrator.normalizer.clone_repo", fake_clone
    )


@pytest.fixture
def mock_tools(monkeypatch, _mock_fetch_and_clone):
    """Replace network-touching tools + stub the URL preflight so
    happy-path tests don't depend on httpx behavior. Preflight logic
    has its own dedicated tests with real-mock httpx clients below."""

    async def fake_preflight(self, url, max_bytes):
        return None

    monkeypatch.setattr(
        "backend.orchestrator.normalizer.Normalizer._preflight_data_url",
        fake_preflight,
    )


async def test_normalize_arxiv_paper(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.paper_path.name == "paper.pdf"
    assert paths.paper_path.read_bytes().startswith(b"%PDF-fake:")
    assert b"2504.01848.pdf" in paths.paper_path.read_bytes()
    assert (paths.repo_path / "README.md").exists()
    assert paths.data_path is None


async def test_normalize_pdf_url_paper(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourcePdfUrl(url="https://example.com/paper.pdf"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.paper_path.name == "paper.pdf"
    assert b"example.com/paper.pdf" in paths.paper_path.read_bytes()


async def test_normalize_no_paper_returns_none_path(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceNone(title_hint="my repo"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.paper_path is None
    assert paths.source_summary.startswith("paper=none")


async def test_normalize_raw_text_paper(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600, title_hint="T"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.paper_path.name == "paper.txt"
    assert paths.paper_path.read_text() == "x" * 600


async def test_normalize_upload_paper(settings, mock_tools, tmp_path: Path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "pdf_abc123.pdf").write_bytes(b"%PDF-upload")

    req = AuditRequest(
        paper=PaperSourceUpload(upload_id="pdf_abc123"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.paper_path.read_bytes() == b"%PDF-upload"


async def test_normalize_upload_missing_raises(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceUpload(upload_id="pdf_missing"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    with pytest.raises(InputError, match="upload not found"):
        await Normalizer(settings).normalize("aud1", req)


async def test_normalize_upload_bad_id_raises(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceUpload(upload_id="../escape"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    with pytest.raises(InputError, match="invalid upload_id"):
        await Normalizer(settings).normalize("aud1", req)


async def test_normalize_local_code(settings, mock_tools, tmp_path: Path):
    src = tmp_path / "src_repo"
    src.mkdir()
    (src / "train.py").write_text("# hi\n")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "a.cpython.pyc").write_bytes(b"\x00")

    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceLocal(path=src),
        data=DataSourceSkip(),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert (paths.repo_path / "train.py").read_text() == "# hi\n"
    assert not (paths.repo_path / "__pycache__").exists()


async def test_normalize_local_code_rejects_relative(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceLocal(path=Path("relative/path")),
        data=DataSourceSkip(),
    )
    with pytest.raises(InputError, match="must be absolute"):
        await Normalizer(settings).normalize("aud1", req)


async def test_normalize_local_code_rejects_missing(
    settings, mock_tools, tmp_path: Path
):
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceLocal(path=tmp_path / "no_such_dir"),
        data=DataSourceSkip(),
    )
    with pytest.raises(InputError, match="does not exist"):
        await Normalizer(settings).normalize("aud1", req)


async def test_normalize_local_code_accepts_shell_escaped_path(
    settings, mock_tools, tmp_path: Path,
):
    repo = tmp_path / "My Repo"
    repo.mkdir()
    (repo / "train.py").write_text("# hi\n")
    shell_style = Path(f"{repo}".replace(" ", "\\ "))
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceLocal(path=shell_style),
        data=DataSourceSkip(),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert (paths.repo_path / "train.py").exists()


async def test_normalize_local_data(settings, mock_tools, tmp_path: Path):
    data_dir = tmp_path / "dataset"
    data_dir.mkdir()

    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceLocal(path=data_dir),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.data_path == data_dir


async def test_normalize_local_data_accepts_shell_escaped_path(
    settings, mock_tools, tmp_path: Path,
):
    """Users paste shell-escaped paths (`\\ ` for space) and wrap
    them in quotes — sanitize before validating existence."""
    data_dir = tmp_path / "My Dataset"  # real path has a space
    data_dir.mkdir()

    # Simulate: user pastes '/tmp/xyz/My\\ Dataset ' — trailing
    # whitespace, backslash-escaped space.
    shell_style = Path(f"{data_dir}".replace(" ", "\\ ") + " ")
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceLocal(path=shell_style),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.data_path is not None
    assert paths.data_path == data_dir


async def test_normalize_local_data_strips_surrounding_quotes(
    settings, mock_tools, tmp_path: Path,
):
    data_dir = tmp_path / "quoted dir"
    data_dir.mkdir()
    quoted = Path(f'"{data_dir}"')
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceLocal(path=quoted),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.data_path == data_dir


async def test_normalize_local_data_error_shows_original_and_sanitized(
    settings, mock_tools,
):
    """If the sanitized path STILL doesn't exist, surface both forms
    so the user can see what we tried."""
    from backend.errors import InputError

    bogus = Path("/no/such/My\\ Dataset ")
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceLocal(path=bogus),
    )
    with pytest.raises(InputError) as ei:
        await Normalizer(settings).normalize("aud1", req)
    msg = str(ei.value)
    # Sanitized path is shown in the message.
    assert "/no/such/My Dataset" in msg
    # Original shell-escaped input is shown too, trailing space and all.
    assert "My\\\\ Dataset" in msg or "My\\ Dataset" in msg


async def test_normalize_bundled_data(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceBundled(subpath="src"),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.data_path is not None
    assert paths.data_path.name == "src"
    assert paths.data_path.is_dir()


async def test_normalize_bundled_data_missing_subpath(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceBundled(subpath="no-such-dir"),
    )
    with pytest.raises(InputError, match="subpath not found"):
        await Normalizer(settings).normalize("aud1", req)


async def test_normalize_url_data(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceUrl(url="https://example.com/data.tar.gz"),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert paths.data_path is not None
    assert paths.data_path.name == "data.bin"


# ---- URL preflight ----


class _StubResponse:
    def __init__(self, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}


class _StubHttpxClient:
    """Minimal async httpx-shape stub. Returns whatever the test sets
    in ``head_response``, or raises ``head_raises`` if set."""

    def __init__(self, *, head_response=None, head_raises=None):
        self._head_response = head_response
        self._head_raises = head_raises
        self.head_calls: list[str] = []

    async def head(self, url):
        self.head_calls.append(url)
        if self._head_raises:
            raise self._head_raises
        return self._head_response

    async def aclose(self):
        pass


async def test_preflight_blocks_google_drive_host(
    settings, _mock_fetch_and_clone,
):
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceUrl(url="https://drive.google.com/file/d/abc/view"),
    )
    with pytest.raises(InputError, match="drive.google.com"):
        await Normalizer(settings).normalize("aud1", req)


async def test_preflight_blocks_dropbox_share(
    settings, _mock_fetch_and_clone,
):
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceUrl(url="https://www.dropbox.com/s/abc/data.tar.gz"),
    )
    with pytest.raises(InputError, match="dropbox"):
        await Normalizer(settings).normalize("aud1", req)


async def test_preflight_blocks_sharepoint_and_onedrive(
    settings, _mock_fetch_and_clone,
):
    for host_url in (
        "https://contoso.sharepoint.com/dataset.zip",
        "https://onedrive.live.com/dataset.zip",
        "https://1drv.ms/u/dataset",
    ):
        req = AuditRequest(
            paper=PaperSourceRawText(text="x" * 600),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceUrl(url=host_url),
        )
        with pytest.raises(InputError, match="direct-download"):
            await Normalizer(settings).normalize("aud1", req)


async def test_preflight_rejects_html_content_type(
    settings, _mock_fetch_and_clone,
):
    client = _StubHttpxClient(
        head_response=_StubResponse(
            status=200, headers={"content-type": "text/html; charset=utf-8"},
        ),
    )
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceUrl(url="https://example.com/interstitial"),
    )
    with pytest.raises(InputError, match="HTML"):
        await Normalizer(settings, http_client=client).normalize("aud1", req)


async def test_preflight_rejects_oversized_content_length(
    settings, _mock_fetch_and_clone,
):
    five_gb = 5 * 1024 * 1024 * 1024
    client = _StubHttpxClient(
        head_response=_StubResponse(
            status=200,
            headers={
                "content-type": "application/gzip",
                "content-length": str(five_gb),
            },
        ),
    )
    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceUrl(url="https://example.com/big.tar.gz"),
    )
    with pytest.raises(InputError, match="cap|bytes"):
        await Normalizer(settings, http_client=client).normalize("aud1", req)


async def test_preflight_tolerates_head_failure(
    settings, monkeypatch, tmp_path, _mock_fetch_and_clone,
):
    """Servers that don't support HEAD or drop mid-request should not
    block the audit — the streaming GET will surface the real error."""
    import httpx as _httpx
    req_obj = _httpx.Request("HEAD", "https://example.com/data")
    client = _StubHttpxClient(
        head_raises=_httpx.ConnectError("refused", request=req_obj),
    )

    async def fake_fetch(url, dest, **_kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"stub")
        return dest

    monkeypatch.setattr(
        "backend.orchestrator.normalizer.fetch_to_disk", fake_fetch
    )

    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceUrl(url="https://example.com/data.tar.gz"),
    )
    # Should NOT raise — HEAD failure is tolerated.
    paths = await Normalizer(settings, http_client=client).normalize(
        "aud1", req
    )
    assert paths.data_path is not None


async def test_preflight_accepts_well_formed_url(
    settings, monkeypatch, tmp_path, _mock_fetch_and_clone,
):
    client = _StubHttpxClient(
        head_response=_StubResponse(
            status=200,
            headers={
                "content-type": "application/gzip",
                "content-length": str(100 * 1024 * 1024),
            },
        ),
    )

    async def fake_fetch(url, dest, **_kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"stub")
        return dest

    monkeypatch.setattr(
        "backend.orchestrator.normalizer.fetch_to_disk", fake_fetch
    )

    req = AuditRequest(
        paper=PaperSourceRawText(text="x" * 600),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceUrl(url="https://cdn.example.com/data.tar.gz"),
    )
    paths = await Normalizer(settings, http_client=client).normalize(
        "aud1", req
    )
    assert paths.data_path is not None
    assert client.head_calls == ["https://cdn.example.com/data.tar.gz"]


async def test_source_summary_contains_all_parts(settings, mock_tools):
    req = AuditRequest(
        paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/abs/2504.01848"),
        code=CodeSourceGit(url="https://github.com/a/b"),
        data=DataSourceSkip(),
    )
    paths = await Normalizer(settings).normalize("aud1", req)
    assert "paper=arxiv" in paths.source_summary
    assert "code=git" in paths.source_summary
    assert "data=skip" in paths.source_summary
