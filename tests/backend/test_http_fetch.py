from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from backend.errors import DataTooLargeError, InputError, UnavailableError
from backend.tools.http_fetch import fetch_to_disk


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )


async def test_fetch_writes_to_dest(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hello world")

    dest = tmp_path / "out.bin"
    async with _mock_client(handler) as client:
        result = await fetch_to_disk(
            "https://example.com/x",
            dest,
            max_bytes=1024,
            client=client,
        )
    assert result == dest
    assert dest.read_bytes() == b"hello world"


async def test_fetch_creates_parent_dir(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    dest = tmp_path / "deep" / "nested" / "file.bin"
    async with _mock_client(handler) as client:
        await fetch_to_disk(
            "https://example.com/x", dest, max_bytes=1024, client=client
        )
    assert dest.exists()


async def test_fetch_rejects_oversized_and_cleans_up(tmp_path: Path):
    big = b"A" * 2048

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    dest = tmp_path / "out.bin"
    async with _mock_client(handler) as client:
        with pytest.raises(DataTooLargeError):
            await fetch_to_disk(
                "https://example.com/x",
                dest,
                max_bytes=1024,
                client=client,
            )
    assert not dest.exists()


async def test_fetch_rejects_4xx_as_input_error(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _mock_client(handler) as client:
        with pytest.raises(InputError):
            await fetch_to_disk(
                "https://example.com/gone",
                tmp_path / "x.bin",
                max_bytes=1024,
                client=client,
            )


async def test_fetch_rejects_5xx_as_unavailable(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with _mock_client(handler) as client:
        with pytest.raises(UnavailableError):
            await fetch_to_disk(
                "https://example.com/broken",
                tmp_path / "x.bin",
                max_bytes=1024,
                client=client,
            )


async def test_fetch_rejects_bad_scheme(tmp_path: Path):
    with pytest.raises(InputError):
        await fetch_to_disk(
            "ftp://example.com/x",
            tmp_path / "x.bin",
            max_bytes=1024,
        )


async def test_fetch_rejects_wrong_content_type(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>not a pdf</html>",
            headers={"content-type": "text/html"},
        )

    async with _mock_client(handler) as client:
        with pytest.raises(InputError):
            await fetch_to_disk(
                "https://example.com/x",
                tmp_path / "x.bin",
                max_bytes=1024,
                allowed_content_types=("application/pdf",),
                client=client,
            )


async def test_fetch_accepts_allowed_content_type(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.4...",
            headers={"content-type": "application/pdf"},
        )

    async with _mock_client(handler) as client:
        dest = tmp_path / "x.pdf"
        result = await fetch_to_disk(
            "https://example.com/x.pdf",
            dest,
            max_bytes=1024,
            allowed_content_types=("application/pdf",),
            client=client,
        )
    assert result.read_bytes() == b"%PDF-1.4..."


async def test_fetch_network_error_becomes_unavailable(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with _mock_client(handler) as client:
        with pytest.raises(UnavailableError):
            await fetch_to_disk(
                "https://example.com/x",
                tmp_path / "x.bin",
                max_bytes=1024,
                client=client,
            )


async def test_fetch_content_type_matches_on_substring(tmp_path: Path):
    """Content-type often has charset suffix, e.g. 'text/plain; charset=utf-8'."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"hi",
            headers={"content-type": "text/plain; charset=utf-8"},
        )

    async with _mock_client(handler) as client:
        result = await fetch_to_disk(
            "https://example.com/x",
            tmp_path / "x.txt",
            max_bytes=1024,
            allowed_content_types=("text/plain",),
            client=client,
        )
    assert result.exists()
