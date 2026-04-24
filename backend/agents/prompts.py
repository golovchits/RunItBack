from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.schemas.events import AgentName

AgentRole = AgentName  # alias — same set of roles the events module knows

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_VALID_ROLES: frozenset[str] = frozenset(
    {"paper_analyst", "code_auditor", "validator", "reviewer"}
)


@lru_cache(maxsize=1)
def _preamble() -> str:
    return (_PROMPTS_DIR / "preamble.md").read_text(encoding="utf-8").strip()


@lru_cache(maxsize=8)
def load_prompt(role: AgentRole) -> str:
    """Return the full system prompt for ``role``: preamble + role body.

    The preamble (shared identity + global_rules) is prepended once at
    the top of every prompt. The role-specific body comes from
    ``prompts/<role>.md``.
    """
    if role not in _VALID_ROLES:
        raise FileNotFoundError(
            f"unknown agent role {role!r}; expected one of {sorted(_VALID_ROLES)}"
        )
    role_path = _PROMPTS_DIR / f"{role}.md"
    if not role_path.exists():
        raise FileNotFoundError(
            f"no prompt file for role {role!r} at {role_path}"
        )
    body = role_path.read_text(encoding="utf-8").strip()
    return f"{_preamble()}\n\n{body}\n"
