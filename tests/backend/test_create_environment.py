from __future__ import annotations

from unittest.mock import MagicMock

from scripts.create_environment import (
    ALLOWED_HOSTS,
    APT_PACKAGES,
    PIP_PACKAGES,
    build_config,
    create_environment,
)


def test_build_config_top_level_structure():
    cfg = build_config()
    assert cfg["type"] == "cloud"
    assert cfg["networking"]["type"] == "limited"
    assert cfg["packages"]["type"] == "packages"


def test_allowlist_includes_required_hosts():
    required = {"arxiv.org", "github.com", "huggingface.co"}
    assert required.issubset(set(ALLOWED_HOSTS))
    assert required.issubset(set(build_config()["networking"]["allowed_hosts"]))


def test_package_managers_allowed_flag_set():
    # Validator runs pip_resolve; needs PyPI without enumerating every host.
    assert build_config()["networking"]["allow_package_managers"] is True


def test_banned_packages_absent_after_pdf_pivot():
    assert "poppler-utils" not in APT_PACKAGES
    assert "pdfminer.six" not in PIP_PACKAGES
    assert "pypdf2" not in PIP_PACKAGES


def test_core_pip_packages_present():
    for name in ("numpy", "pandas", "pillow", "scikit-learn", "uv"):
        assert name in PIP_PACKAGES


def test_pip_packages_have_no_index_flags():
    # The SDK rejects `--index-url ...` in pip package specs.
    for spec in PIP_PACKAGES:
        assert "--" not in spec


def test_packages_config_is_flat():
    pkgs = build_config()["packages"]
    # Schema is flat { apt, pip, ... } — no nested "python" object.
    assert "apt" in pkgs
    assert "pip" in pkgs
    assert "python" not in pkgs


def test_create_environment_calls_sdk_correctly():
    fake = MagicMock()
    fake.beta.environments.create.return_value = MagicMock(id="env_abc123")

    result = create_environment(client=fake, name="test-env")

    assert result == "env_abc123"
    fake.beta.environments.create.assert_called_once()
    kwargs = fake.beta.environments.create.call_args.kwargs
    assert kwargs["name"] == "test-env"
    assert kwargs["config"]["type"] == "cloud"
    assert kwargs["config"]["networking"]["type"] == "limited"
    assert "arxiv.org" in kwargs["config"]["networking"]["allowed_hosts"]


def test_create_environment_default_name():
    fake = MagicMock()
    fake.beta.environments.create.return_value = MagicMock(id="env_default")
    create_environment(client=fake)
    kwargs = fake.beta.environments.create.call_args.kwargs
    assert kwargs["name"] == "runitback-sandbox"
