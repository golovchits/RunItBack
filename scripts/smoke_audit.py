"""Smoke-test the running backend end-to-end.

Fetches a small repo's README to use as a quasi-paper (raw_text mode),
posts an audit, and prints the audit_id + URLs to follow up with.

Usage: uv run python scripts/smoke_audit.py
"""

from __future__ import annotations

import sys

import httpx

API_BASE = "http://localhost:8000/api/v1"
README_URL = "https://raw.githubusercontent.com/karpathy/nanoGPT/master/README.md"
REPO_URL = "https://github.com/karpathy/nanoGPT"
TITLE_HINT = "nanoGPT"
TIMEOUT_MINUTES = 30  # paper_analyst gets ~3.75 min, code_auditor ~15 min


def main() -> int:
    print(f"fetching {README_URL} ...", flush=True)
    try:
        readme = httpx.get(README_URL, timeout=30, follow_redirects=True).text
    except httpx.HTTPError as e:
        print(f"failed to fetch README: {e}")
        return 1
    if len(readme) < 500:
        print(f"README too short ({len(readme)} chars); schema needs ≥500")
        return 1
    print(f"  got {len(readme)} chars", flush=True)

    body = {
        "paper": {
            "kind": "raw_text",
            "text": readme,
            "title_hint": TITLE_HINT,
        },
        "code": {"kind": "git", "url": REPO_URL},
        "data": {"kind": "skip"},
        "timeout_minutes": TIMEOUT_MINUTES,
    }

    print(f"POST {API_BASE}/audit ...", flush=True)
    try:
        resp = httpx.post(f"{API_BASE}/audit", json=body, timeout=30)
    except httpx.ConnectError:
        print(f"cannot reach {API_BASE}. Is `make dev` running?")
        return 3
    except httpx.HTTPError as e:
        print(f"HTTP error: {e}")
        return 2

    if resp.status_code != 202:
        print(f"unexpected status {resp.status_code}:")
        print(resp.text)
        return 2

    payload = resp.json()
    audit_id = payload["audit_id"]

    print()
    print(f"status:     {resp.status_code}")
    print(f"audit_id:   {audit_id}")
    print(f"phase:      {payload['phase']}")
    print(f"runtime:    {payload['runtime_mode']}")
    print()
    print("Follow up with:")
    print(f"  curl -N {API_BASE}/audit/{audit_id}/stream")
    print(f"  curl -s {API_BASE}/audit/{audit_id}/status | python -m json.tool")
    print(
        f"  curl -s {API_BASE}/audit/{audit_id}/report | python -m json.tool"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
