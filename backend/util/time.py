from __future__ import annotations

from datetime import datetime, timezone


def utcnow_iso() -> str:
    """Return current UTC time as ISO 8601 with a trailing ``Z``."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
