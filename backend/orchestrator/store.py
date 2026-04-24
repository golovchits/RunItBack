from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional, TypeVar

from pydantic import BaseModel

from backend.schemas.inputs import AuditRecord

T = TypeVar("T", bound=BaseModel)


class AuditStore:
    """Persistence for audit metadata, events, and artifacts.

    - SQLite at ``$DATA_ROOT/runitback.db`` holds one row per audit with
      the full ``AuditRecord`` serialized as JSON.
    - Events are append-only JSONL at
      ``$DATA_ROOT/audits/{id}/events.jsonl`` — the source of truth for
      SSE replay.
    - Pydantic artifacts (claims, findings, validation, report) are
      per-audit JSON files under ``$DATA_ROOT/audits/{id}/artifacts/``.

    Uses stdlib ``sqlite3`` wrapped in ``asyncio.to_thread`` to keep the
    event loop unblocked during disk I/O.
    """

    def __init__(self, data_root: Path) -> None:
        self._root = data_root
        self._db_path = data_root / "runitback.db"
        self._ensure_schema()

    # ---- paths ----

    def _audits_dir(self, audit_id: str) -> Path:
        p = self._root / "audits" / audit_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _events_path(self, audit_id: str) -> Path:
        return self._audits_dir(audit_id) / "events.jsonl"

    def _ensure_schema(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audits (
                  id           TEXT PRIMARY KEY,
                  created_at   TEXT NOT NULL,
                  phase        TEXT NOT NULL,
                  record_json  TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ---- AuditRecord ----

    async def upsert(self, record: AuditRecord) -> None:
        await asyncio.to_thread(self._upsert_sync, record)

    def _upsert_sync(self, record: AuditRecord) -> None:
        payload = record.model_dump_json()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO audits (id, created_at, phase, record_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  phase = excluded.phase,
                  record_json = excluded.record_json
                """,
                (record.id, record.created_at, record.phase, payload),
            )
            conn.commit()

    async def get(self, audit_id: str) -> Optional[AuditRecord]:
        return await asyncio.to_thread(self._get_sync, audit_id)

    def _get_sync(self, audit_id: str) -> Optional[AuditRecord]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT record_json FROM audits WHERE id = ?", (audit_id,)
            ).fetchone()
        if row is None:
            return None
        return AuditRecord.model_validate_json(row[0])

    # ---- Events (JSONL) ----

    async def append_event(self, audit_id: str, event: BaseModel) -> None:
        await asyncio.to_thread(self._append_event_sync, audit_id, event)

    def _append_event_sync(self, audit_id: str, event: BaseModel) -> None:
        line = event.model_dump_json()
        with self._events_path(audit_id).open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")

    async def read_events(
        self, audit_id: str, since_seq: int = 0
    ) -> AsyncIterator[dict]:
        """Yield every JSON-decoded event with ``seq > since_seq``.

        Returns raw dicts so SSE can re-emit them without re-typing.
        """
        rows = await asyncio.to_thread(
            self._read_events_sync, audit_id, since_seq
        )
        for row in rows:
            yield row

    def _read_events_sync(self, audit_id: str, since_seq: int) -> list[dict]:
        path = self._events_path(audit_id)
        if not path.exists():
            return []
        out: list[dict] = []
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    # partial-line races during live append are possible
                    continue
                if obj.get("seq", 0) > since_seq:
                    out.append(obj)
        return out

    # ---- Artifacts ----

    async def save_artifact(
        self, audit_id: str, name: str, model: BaseModel
    ) -> Path:
        return await asyncio.to_thread(
            self._save_artifact_sync, audit_id, name, model
        )

    def _save_artifact_sync(
        self, audit_id: str, name: str, model: BaseModel
    ) -> Path:
        art_dir = self._audits_dir(audit_id) / "artifacts"
        art_dir.mkdir(exist_ok=True)
        path = art_dir / f"{name}.json"
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        return path

    async def load_artifact(
        self, audit_id: str, name: str, cls: type[T]
    ) -> Optional[T]:
        return await asyncio.to_thread(
            self._load_artifact_sync, audit_id, name, cls
        )

    def _load_artifact_sync(
        self, audit_id: str, name: str, cls: type[T]
    ) -> Optional[T]:
        path = self._root / "audits" / audit_id / "artifacts" / f"{name}.json"
        if not path.exists():
            return None
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
