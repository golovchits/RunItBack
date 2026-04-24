from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


_SKIP_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".eggs",
    ".tox",
}

_TRAIN_NAMES = {"train.py", "main_train.py", "run_train.py", "pretrain.py"}
_EVAL_NAMES = {
    "eval.py",
    "evaluate.py",
    "test.py",
    "inference.py",
    "predict.py",
}
_DATALOADER_HINTS = ("dataloader", "dataset", "data_module", "loader")
_MODEL_HINTS = ("model", "net", "network", "arch", "backbone")

_DEP_FILES = {
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "environment.yml",
    "environment.yaml",
    "Pipfile",
    "Pipfile.lock",
    "setup.py",
    "setup.cfg",
    "poetry.lock",
    "uv.lock",
    "conda.yaml",
}

_CONFIG_EXTS = {".yaml", ".yml", ".toml", ".ini", ".cfg"}


class EntryPoints(_Strict):
    train_script: Optional[str] = None
    eval_script: Optional[str] = None
    dataloader_files: list[str] = Field(default_factory=list)
    model_files: list[str] = Field(default_factory=list)


class RepoManifest(_Strict):
    repo_root: str
    file_count: int
    total_bytes: int
    top_level_dirs: list[str] = Field(default_factory=list)
    language_stats: dict[str, int] = Field(default_factory=dict)
    entry_points: EntryPoints = Field(default_factory=EntryPoints)
    config_files: list[str] = Field(default_factory=list)
    dependency_files: list[str] = Field(default_factory=list)
    notebooks: list[str] = Field(default_factory=list)
    has_git: bool = False


def build_manifest(repo_path: Path, *, max_depth: int = 8) -> RepoManifest:
    """Walk ``repo_path`` and produce a ``RepoManifest``.

    Skips junk dirs (``__pycache__``, ``.venv``, etc.) during file
    counts. Top-level dirs are listed verbatim (including ``.git``) to
    give the agent a full layout view.
    """
    repo_path = repo_path.resolve()
    if not repo_path.exists():
        raise ValueError(f"path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise ValueError(f"not a directory: {repo_path}")

    top_level: list[str] = []
    has_git = False
    for child in sorted(repo_path.iterdir()):
        if child.is_dir():
            top_level.append(child.name)
            if child.name == ".git":
                has_git = True

    file_count = 0
    total_bytes = 0
    lang_stats: dict[str, int] = {}
    config_files: list[str] = []
    dependency_files: list[str] = []
    notebooks: list[str] = []
    dataloader_files: list[str] = []
    model_files: list[str] = []
    train_candidates: list[str] = []
    eval_candidates: list[str] = []

    for dirpath, dirs, files in os.walk(repo_path, followlinks=False):
        rel_depth = len(Path(dirpath).relative_to(repo_path).parts)
        if rel_depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

        for name in files:
            fp = Path(dirpath) / name
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            file_count += 1
            total_bytes += size

            rel = fp.relative_to(repo_path).as_posix()
            ext = fp.suffix.lower()
            low = name.lower()

            if ext:
                lang_stats[ext] = lang_stats.get(ext, 0) + 1

            if name in _DEP_FILES:
                dependency_files.append(rel)
            elif ext in _CONFIG_EXTS:
                config_files.append(rel)

            if ext == ".ipynb":
                notebooks.append(rel)

            if low in _TRAIN_NAMES:
                train_candidates.append(rel)
            if low in _EVAL_NAMES:
                eval_candidates.append(rel)

            if ext == ".py":
                if any(h in low for h in _DATALOADER_HINTS):
                    dataloader_files.append(rel)
                elif any(h in low for h in _MODEL_HINTS):
                    model_files.append(rel)

    entry = EntryPoints(
        train_script=train_candidates[0] if train_candidates else None,
        eval_script=eval_candidates[0] if eval_candidates else None,
        dataloader_files=sorted(dataloader_files),
        model_files=sorted(model_files),
    )

    return RepoManifest(
        repo_root=str(repo_path),
        file_count=file_count,
        total_bytes=total_bytes,
        top_level_dirs=sorted(top_level),
        language_stats=lang_stats,
        entry_points=entry,
        config_files=sorted(config_files),
        dependency_files=sorted(dependency_files),
        notebooks=sorted(notebooks),
        has_git=has_git,
    )
