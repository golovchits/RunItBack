"""Resume an audit from a chosen phase by deleting downstream artifacts.

Each pipeline phase is "skip if the artifact exists"; so to re-run
from code_auditor onward while keeping paper_analyst's claims,
delete findings.json / validation.json / report.json, then POST to
/api/v1/audit/{id}/resume. This script does the deletion (with
confirmation) and prints the curl command.

Usage:
    uv run python scripts/resume_from_phase.py <audit_id> <from_phase>
        [--yes] [--dry-run]

Where <from_phase> is one of:
    paper_analyst | code_auditor | validator | reviewer

Examples:
    # Re-run everything after paper_analyst (the common case when
    # the auditor/validator/reviewer degraded).
    uv run python scripts/resume_from_phase.py abc-123 code_auditor

    # Re-run only the reviewer (auditor + validator both succeeded).
    uv run python scripts/resume_from_phase.py abc-123 reviewer
"""

from __future__ import annotations

import sys
from pathlib import Path

from backend.config import get_settings

# Order matches pipeline phase sequence. Each phase's artifact must be
# removed (along with all later artifacts) to force that phase to run.
_PHASE_ARTIFACTS: list[tuple[str, list[str]]] = [
    ("paper_analyst", ["claims.json"]),
    ("code_auditor", ["findings.json", "repo_manifest.json"]),
    ("validator", ["validation.json"]),
    ("reviewer", ["report.json"]),
]

# Also clean up the agent's raw output text if present (otherwise the
# old raw will be overwritten by the new run — not a correctness
# issue, but removing makes it obvious something was redone).
_PHASE_RAW: dict[str, str] = {
    "paper_analyst": "paper_analyst_raw.txt",
    "code_auditor": "code_auditor_raw.txt",
    "validator": "validator_raw.txt",
    "reviewer": "reviewer_raw.txt",
}


def _usage() -> int:
    print(__doc__)
    return 1


def main() -> int:
    args = sys.argv[1:]
    yes = "--yes" in args
    dry_run = "--dry-run" in args
    args = [a for a in args if not a.startswith("--")]

    if len(args) != 2:
        return _usage()

    audit_id, from_phase = args
    phase_names = [p for p, _ in _PHASE_ARTIFACTS]
    if from_phase not in phase_names:
        print(
            f"Unknown phase: {from_phase!r}. Choose one of: "
            + ", ".join(phase_names)
        )
        return 2

    settings = get_settings()
    art_dir = settings.data_root_path() / "audits" / audit_id / "artifacts"
    if not art_dir.exists():
        print(f"Artifacts directory does not exist: {art_dir}")
        print(
            "Check the audit ID; the directory should be at "
            "runtime/audits/<id>/artifacts/"
        )
        return 3

    # Collect everything we'll remove: `from_phase` and all later phases.
    idx = phase_names.index(from_phase)
    to_remove: list[Path] = []
    for phase, artifacts in _PHASE_ARTIFACTS[idx:]:
        for name in artifacts:
            p = art_dir / name
            if p.exists():
                to_remove.append(p)
        raw_name = _PHASE_RAW.get(phase)
        if raw_name:
            raw_p = art_dir / raw_name
            if raw_p.exists():
                to_remove.append(raw_p)

    # Report plan.
    print(f"Audit: {audit_id}")
    print(f"Resuming from phase: {from_phase}")
    print(f"Artifacts directory: {art_dir}")
    print()
    if not to_remove:
        print(
            f"No artifacts to remove — phase {from_phase!r} and later "
            "already have no persisted output."
        )
        print(
            "If you just want to run the audit again, POST to "
            f"/api/v1/audit/{audit_id}/resume as-is."
        )
        return 0

    print(f"Will remove {len(to_remove)} file(s):")
    for p in to_remove:
        size = p.stat().st_size
        print(f"  {p.name:30s}  ({size:,} bytes)")
    print()

    if idx > 0:
        kept_phases = [p for p, _ in _PHASE_ARTIFACTS[:idx]]
        print(f"Will KEEP artifacts from: {', '.join(kept_phases)}")
        print()

    if dry_run:
        print("--dry-run set; nothing removed.")
        return 0

    if not yes:
        resp = input("Proceed with deletion? [y/N]: ").strip().lower()
        if resp not in ("y", "yes"):
            print("Aborted.")
            return 0

    for p in to_remove:
        p.unlink()
    print(f"Removed {len(to_remove)} file(s).")
    print()
    print("Now trigger the resume via API:")
    print(
        f"  curl -X POST "
        f"http://localhost:8000/api/v1/audit/{audit_id}/resume"
    )
    print()
    print(
        "The frontend will see new SSE events arriving on "
        f"/api/v1/audit/{audit_id}/stream if you have a client "
        "subscribed to that audit."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
