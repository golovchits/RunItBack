from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.errors import DataTooLargeError, InputError, UnavailableError
from backend.tools.github import clone_repo

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git binary not on PATH"
)


def _make_origin(tmp_path: Path, branch: str = "main") -> Path:
    origin = tmp_path / "origin"
    origin.mkdir()
    env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "t@t.com",
    }
    subprocess.run(
        ["git", "init", "-b", branch],
        cwd=origin,
        check=True,
        capture_output=True,
    )
    (origin / "README.md").write_text("hello\n")
    subprocess.run(
        ["git", "add", "."], cwd=origin, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=origin,
        check=True,
        capture_output=True,
        env={**env},
    )
    return origin


async def test_clone_succeeds(tmp_path: Path):
    origin = _make_origin(tmp_path)
    dest = tmp_path / "work"
    result = await clone_repo(str(origin), dest)
    assert result == dest
    assert (dest / "README.md").read_text() == "hello\n"
    assert (dest / ".git").exists()


async def test_clone_with_ref(tmp_path: Path):
    origin = _make_origin(tmp_path, branch="main")
    # add a second branch with different content
    subprocess.run(
        ["git", "checkout", "-b", "feature"],
        cwd=origin,
        check=True,
        capture_output=True,
    )
    (origin / "feature.md").write_text("feature\n")
    env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "t@t.com",
    }
    subprocess.run(
        ["git", "add", "."], cwd=origin, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "feature"],
        cwd=origin,
        check=True,
        capture_output=True,
        env={**env},
    )

    dest = tmp_path / "work"
    await clone_repo(str(origin), dest, ref="feature")
    assert (dest / "feature.md").exists()


async def test_clone_nonexistent_url_raises_input_error(tmp_path: Path):
    nonexistent = tmp_path / "nope"
    with pytest.raises(InputError):
        await clone_repo(str(nonexistent), tmp_path / "work", timeout=10)


async def test_clone_into_nonempty_dest_rejected(tmp_path: Path):
    dest = tmp_path / "work"
    dest.mkdir()
    (dest / "existing.txt").write_text("hi")
    with pytest.raises(InputError, match="not empty"):
        await clone_repo("https://example.com/x.git", dest)


async def test_clone_exceeds_max_bytes(tmp_path: Path):
    origin = _make_origin(tmp_path)
    (origin / "big.bin").write_bytes(b"X" * 10000)
    env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "t@t.com",
    }
    subprocess.run(
        ["git", "add", "."], cwd=origin, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "big"],
        cwd=origin,
        check=True,
        capture_output=True,
        env={**env},
    )

    dest = tmp_path / "work"
    with pytest.raises(DataTooLargeError):
        await clone_repo(str(origin), dest, max_bytes=1000)
    assert not dest.exists()


async def test_clone_timeout(tmp_path: Path, monkeypatch):
    class _HangingProc:
        returncode: int | None = None

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(3600)
            return b"", b""

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    async def fake_exec(*_args, **_kwargs) -> _HangingProc:
        return _HangingProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(UnavailableError, match="timed out"):
        await clone_repo(
            "https://example.com/r.git",
            tmp_path / "work",
            timeout=0.1,
        )


async def test_clone_git_not_installed(tmp_path: Path, monkeypatch):
    async def raise_fnfe(*_args, **_kwargs):
        raise FileNotFoundError("git: No such file")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", raise_fnfe)

    with pytest.raises(UnavailableError, match="git is not installed"):
        await clone_repo("https://example.com/r.git", tmp_path / "work")
