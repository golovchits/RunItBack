from __future__ import annotations

from pathlib import Path

import pytest

from backend.orchestrator.repo_manifest import build_manifest


def _build_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# project\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (repo / "requirements.txt").write_text("torch\n")
    (repo / "train.py").write_text("# train\n")
    (repo / "eval.py").write_text("# eval\n")

    src = repo / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "dataloader.py").write_text("class DataLoader: ...\n")
    (src / "model.py").write_text("class Model: ...\n")
    (src / "utils.py").write_text("def helper(): ...\n")

    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "model.cpython-312.pyc").write_bytes(b"\x00")

    configs = repo / "configs"
    configs.mkdir()
    (configs / "base.yaml").write_text("lr: 0.001\n")
    (configs / "large.yaml").write_text("lr: 0.01\n")

    notebooks = repo / "notebooks"
    notebooks.mkdir()
    (notebooks / "exploration.ipynb").write_text("{}")

    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main")

    return repo


def test_build_manifest_counts_files(tmp_path: Path):
    repo = _build_repo(tmp_path)
    m = build_manifest(repo)

    # files: README, pyproject, requirements, train, eval,
    #        src/__init__, src/dataloader, src/model, src/utils,
    #        configs/base.yaml, configs/large.yaml,
    #        notebooks/exploration.ipynb
    # .git/ contents are skipped; __pycache__/ contents skipped.
    assert m.file_count == 12
    assert m.total_bytes > 0


def test_build_manifest_top_level_and_git(tmp_path: Path):
    repo = _build_repo(tmp_path)
    m = build_manifest(repo)
    assert m.has_git is True
    assert ".git" in m.top_level_dirs
    assert "src" in m.top_level_dirs
    assert "configs" in m.top_level_dirs
    assert "notebooks" in m.top_level_dirs


def test_build_manifest_entry_points(tmp_path: Path):
    repo = _build_repo(tmp_path)
    m = build_manifest(repo)
    assert m.entry_points.train_script == "train.py"
    assert m.entry_points.eval_script == "eval.py"
    assert "src/dataloader.py" in m.entry_points.dataloader_files
    assert "src/model.py" in m.entry_points.model_files
    assert "src/utils.py" not in m.entry_points.model_files
    assert "src/utils.py" not in m.entry_points.dataloader_files


def test_build_manifest_config_and_dep_files(tmp_path: Path):
    repo = _build_repo(tmp_path)
    m = build_manifest(repo)
    assert "pyproject.toml" in m.dependency_files
    assert "requirements.txt" in m.dependency_files
    assert "configs/base.yaml" in m.config_files
    assert "configs/large.yaml" in m.config_files
    # pyproject.toml is a dep file; must not also appear in configs
    assert "pyproject.toml" not in m.config_files


def test_build_manifest_notebooks(tmp_path: Path):
    repo = _build_repo(tmp_path)
    m = build_manifest(repo)
    assert m.notebooks == ["notebooks/exploration.ipynb"]


def test_build_manifest_language_stats(tmp_path: Path):
    repo = _build_repo(tmp_path)
    m = build_manifest(repo)
    assert m.language_stats.get(".py", 0) == 6
    assert m.language_stats.get(".yaml", 0) == 2
    assert m.language_stats.get(".ipynb", 0) == 1
    assert m.language_stats.get(".md", 0) == 1
    assert ".pyc" not in m.language_stats  # __pycache__ skipped


def test_build_manifest_rejects_nonexistent(tmp_path: Path):
    with pytest.raises(ValueError, match="does not exist"):
        build_manifest(tmp_path / "nope")


def test_build_manifest_rejects_file(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(ValueError, match="not a directory"):
        build_manifest(f)


def test_build_manifest_respects_max_depth(tmp_path: Path):
    repo = tmp_path / "deep"
    repo.mkdir()
    current = repo
    for i in range(10):
        current = current / f"d{i}"
        current.mkdir()
        (current / f"f{i}.py").write_text("# x\n")

    shallow = build_manifest(repo, max_depth=2)
    deep = build_manifest(repo, max_depth=20)
    assert shallow.file_count < deep.file_count


def test_build_manifest_repo_root_is_absolute(tmp_path: Path):
    repo = _build_repo(tmp_path)
    m = build_manifest(repo)
    assert Path(m.repo_root).is_absolute()
    assert Path(m.repo_root) == repo.resolve()
