from __future__ import annotations

from datetime import datetime, timezone

from backend.util.time import utcnow_iso


def test_utcnow_iso_ends_with_z():
    s = utcnow_iso()
    assert s.endswith("Z")


def test_utcnow_iso_is_parseable():
    s = utcnow_iso()
    parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.tzinfo.utcoffset(parsed) == timezone.utc.utcoffset(parsed)
