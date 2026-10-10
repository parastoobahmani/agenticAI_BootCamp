from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import CaseState, now_iso


class Storage:
    def __init__(self, path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT,
                kind TEXT NOT NULL,
                detail TEXT NOT NULL,
                at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def save_case(self, state: CaseState) -> CaseState:
        state.updated_at = now_iso()
        payload = json.dumps(state.to_dict(), ensure_ascii=False)
        self.connection.execute(
            "INSERT INTO cases (case_id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(case_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (state.case_id, payload, state.updated_at),
        )
        self.connection.commit()
        return state

    def load_case(self, case_id: str) -> CaseState | None:
        row = self.connection.execute(
            "SELECT data FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        return CaseState.from_dict(json.loads(row["data"]))

    def list_cases(self) -> list[str]:
        rows = self.connection.execute("SELECT case_id FROM cases ORDER BY case_id").fetchall()
        return [row["case_id"] for row in rows]

    def clear_cases(self) -> None:
        self.connection.execute("DELETE FROM cases")
        self.connection.commit()

    def log(self, case_id, kind: str, detail: dict) -> None:
        self.connection.execute(
            "INSERT INTO events (case_id, kind, detail, at) VALUES (?, ?, ?, ?)",
            (case_id, kind, json.dumps(detail, ensure_ascii=False, default=str), now_iso()),
        )
        self.connection.commit()

    def events(self, case_id=None, limit: int = 50) -> list[dict]:
        if case_id is None:
            rows = self.connection.execute(
                "SELECT * FROM events ORDER BY event_id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM events WHERE case_id = ? ORDER BY event_id DESC LIMIT ?",
                (case_id, limit),
            ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["detail"] = json.loads(record["detail"])
            records.append(record)
        return records

    def clear_events(self) -> None:
        self.connection.execute("DELETE FROM events")
        self.connection.commit()

    def meta_get(self, key: str) -> str | None:
        row = self.connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def meta_set(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
