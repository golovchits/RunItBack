from __future__ import annotations

import pytest

from backend.errors import InputError
from backend.tools.arxiv import ArxivRef, parse_arxiv_url, pdf_url_for


@pytest.mark.parametrize(
    "inp,expected_id,expected_version",
    [
        # New-style IDs via URL
        ("https://arxiv.org/abs/2504.01848", "2504.01848", None),
        ("https://arxiv.org/abs/2504.01848v1", "2504.01848", "v1"),
        ("https://arxiv.org/abs/2504.01848v12", "2504.01848", "v12"),
        ("https://arxiv.org/pdf/2504.01848", "2504.01848", None),
        ("https://arxiv.org/pdf/2504.01848.pdf", "2504.01848", None),
        ("https://arxiv.org/pdf/2504.01848v2.pdf", "2504.01848", "v2"),
        ("http://arxiv.org/abs/2504.01848", "2504.01848", None),
        ("https://export.arxiv.org/abs/2504.01848", "2504.01848", None),
        # 5-digit new-style
        ("https://arxiv.org/abs/2504.12345", "2504.12345", None),
        # Trailing slash / query / fragment
        ("https://arxiv.org/abs/2504.01848/", "2504.01848", None),
        ("https://arxiv.org/abs/2504.01848?context=cs.LG", "2504.01848", None),
        ("https://arxiv.org/abs/2504.01848#introduction", "2504.01848", None),
        # Prefix form
        ("arxiv:2504.01848", "2504.01848", None),
        ("ArXiv:2504.01848v1", "2504.01848", "v1"),
        # Bare id
        ("2504.01848", "2504.01848", None),
        ("2504.01848v3", "2504.01848", "v3"),
        # Old-style
        ("https://arxiv.org/abs/cs/0701001", "cs/0701001", None),
        ("cs/0701001", "cs/0701001", None),
        ("cs/0701001v2", "cs/0701001", "v2"),
        ("cs.LG/0701001", "cs.LG/0701001", None),
    ],
)
def test_parse_accepts(inp, expected_id, expected_version):
    ref = parse_arxiv_url(inp)
    assert ref.id == expected_id
    assert ref.version == expected_version


@pytest.mark.parametrize(
    "inp",
    [
        "https://example.com/abs/2504.01848",  # wrong host
        "https://arxiv.org/random-path",
        "https://arxiv.org/",  # bare root
        "not a url",
        "",
        "   ",
        "arxiv:",
        "ftp://arxiv.org/abs/2504.01848",  # wrong scheme
        "https://arxiv.org/abs/abc.def",  # bad id shape
    ],
)
def test_parse_rejects(inp):
    with pytest.raises(InputError):
        parse_arxiv_url(inp)


def test_pdf_url_for_new_style():
    ref = ArxivRef(id="2504.01848")
    assert pdf_url_for(ref) == "https://arxiv.org/pdf/2504.01848.pdf"


def test_pdf_url_for_with_version():
    ref = ArxivRef(id="2504.01848", version="v2")
    assert pdf_url_for(ref) == "https://arxiv.org/pdf/2504.01848v2.pdf"


def test_pdf_url_for_old_style():
    ref = ArxivRef(id="cs/0701001")
    assert pdf_url_for(ref) == "https://arxiv.org/pdf/cs/0701001.pdf"


def test_canonical_id_property():
    assert ArxivRef(id="2504.01848", version="v2").canonical_id == "2504.01848v2"
    assert ArxivRef(id="2504.01848").canonical_id == "2504.01848"


def test_arxiv_ref_is_frozen():
    ref = ArxivRef(id="2504.01848")
    with pytest.raises(Exception):  # FrozenInstanceError from dataclasses
        ref.id = "changed"  # type: ignore[misc]
