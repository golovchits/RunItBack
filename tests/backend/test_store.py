from __future__ import annotations

from pathlib import Path

import pytest

from backend.orchestrator.store import AuditStore
from backend.schemas.claims import PaperClaims
from backend.schemas.events import EvtAuditStatus
from backend.schemas.inputs import (
    AuditRecord,
    AuditRequest,
    CodeSourceGit,
    DataSourceSkip,
    PaperSourceArxiv,
)


def _make_record(audit_id: str = "a1", phase: str = "created") -> AuditRecord:
    return AuditRecord(
        id=audit_id,
        request=AuditRequest(
            paper=PaperSourceArxiv(arxiv_url="https://arxiv.org/pdf/2504.01848"),
            code=CodeSourceGit(url="https://github.com/a/b"),
            data=DataSourceSkip(),
        ),
        created_at="2026-04-22T14:00:00Z",
        phase=phase,
        runtime_mode="managed_agents",
    )


@pytest.fixture
def store(tmp_path: Path) -> AuditStore:
    return AuditStore(data_root=tmp_path)


async def test_upsert_and_get(store: AuditStore):
    rec = _make_record()
    await store.upsert(rec)
    got = await store.get("a1")
    assert got == rec


async def test_upsert_updates_existing(store: AuditStore):
    await store.upsert(_make_record(phase="created"))
    await store.upsert(_make_record(phase="paper_analyst"))
    got = await store.get("a1")
    assert got is not None
    assert got.phase == "paper_analyst"


async def test_get_missing_returns_none(store: AuditStore):
    assert await store.get("nonexistent") is None


async def test_append_and_read_events(store: AuditStore):
    e1 = EvtAuditStatus(audit_id="a1", seq=1, ts="t1", phase="normalizing")
    e2 = EvtAuditStatus(audit_id="a1", seq=2, ts="t2", phase="paper_analyst")
    await store.append_event("a1", e1)
    await store.append_event("a1", e2)

    events = [ev async for ev in store.read_events("a1")]
    assert [e["seq"] for e in events] == [1, 2]
    assert events[0]["type"] == "audit.status"


async def test_read_events_since_seq(store: AuditStore):
    for seq in range(1, 6):
        await store.append_event(
            "a1",
            EvtAuditStatus(audit_id="a1", seq=seq, ts=f"t{seq}", phase="done"),
        )

    events = [ev async for ev in store.read_events("a1", since_seq=3)]
    assert [e["seq"] for e in events] == [4, 5]


async def test_read_events_missing_audit_is_empty(store: AuditStore):
    events = [ev async for ev in store.read_events("nonexistent")]
    assert events == []


async def test_save_and_load_artifact(store: AuditStore):
    claims = PaperClaims(
        paper_title="T",
        authors=["A"],
        abstract_summary="s",
        metrics=[],
        datasets=[],
        architectures=[],
        training_config=[],
        evaluation_protocol=[],
        extraction_confidence=0.5,
    )
    path = await store.save_artifact("a1", "claims", claims)
    assert path.exists()
    assert path.name == "claims.json"

    loaded = await store.load_artifact("a1", "claims", PaperClaims)
    assert loaded == claims


async def test_load_artifact_missing_returns_none(store: AuditStore):
    loaded = await store.load_artifact("a1", "claims", PaperClaims)
    assert loaded is None


async def test_sqlite_file_created(tmp_path: Path):
    AuditStore(data_root=tmp_path)
    assert (tmp_path / "runitback.db").exists()


async def test_audit_dir_created_on_event_append(
    store: AuditStore, tmp_path: Path
):
    await store.append_event(
        "a1",
        EvtAuditStatus(audit_id="a1", seq=1, ts="t", phase="created"),
    )
    assert (tmp_path / "audits" / "a1" / "events.jsonl").exists()
