"""One-shot script: create the RunItBack sandbox environment.

Requires ``ANTHROPIC_API_KEY`` in the environment. Prints a line ready
to paste into ``.env``.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from anthropic import Anthropic

from backend.config import get_settings

ALLOWED_HOSTS = [
    "arxiv.org",
    "export.arxiv.org",
    "github.com",
    "raw.githubusercontent.com",
    "api.github.com",
    "codeload.github.com",
    "huggingface.co",
    "cdn-lfs.huggingface.co",
]

APT_PACKAGES = [
    "git",
    "curl",
    "build-essential",
    "ffmpeg",
    "libsndfile1",
]

# Flat list of pip-installable packages. The SDK packages schema doesn't
# accept pip index-url flags or Python version pins; the Validator can
# install torch into an ephemeral venv on demand (see validator.md).
PIP_PACKAGES = [
    "uv",
    "numpy",
    "pandas",
    "pyyaml",
    "pillow",
    "scikit-learn",
    "librosa",
    "matplotlib",
    "ruff",
]


def build_config() -> dict[str, Any]:
    return {
        "type": "cloud",
        "networking": {
            "type": "limited",
            "allowed_hosts": list(ALLOWED_HOSTS),
            "allow_package_managers": True,
        },
        "packages": {
            "type": "packages",
            "apt": list(APT_PACKAGES),
            "pip": list(PIP_PACKAGES),
        },
    }


def _default_client() -> Anthropic:
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Put it in .env or export it."
        )
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def create_environment(
    client: Optional[Anthropic] = None, name: str = "runitback-sandbox"
) -> str:
    client = client or _default_client()
    env = client.beta.environments.create(name=name, config=build_config())
    return env.id


def main() -> int:
    env_id = create_environment()
    print("# Paste into .env:")
    print(f"MANAGED_ENVIRONMENT_ID={env_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
