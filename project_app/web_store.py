"""Small persistent store for web-facing conversation and navigation state."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from problem2_parts1_2.models import now_iso


class WebStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS web_cases (
                    case_id TEXT PRIMARY KEY,
                    case_json TEXT NOT NULL,
                    latest_response_id TEXT NOT NULL DEFAULT '',
                    latest_proposal_id TEXT NOT NULL DEFAULT '',
                    artifact_dir TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS web_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS web_events_case
                    ON web_events(case_id, event_id);
                """
            )
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def save_case(
        self,
        case: dict[str, Any],
        *,
        response_id: str,
        proposal_id: str,
        artifact_dir: str,
    ) -> None:
        now = now_iso()
        payload = json.dumps(case, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO web_cases (
                    case_id, case_json, latest_response_id, latest_proposal_id,
                    artifact_dir, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    case_json = excluded.case_json,
                    latest_response_id = excluded.latest_response_id,
                    latest_proposal_id = excluded.latest_proposal_id,
                    artifact_dir = excluded.artifact_dir,
                    updated_at = excluded.updated_at
                """,
                (
                    case["case_id"], payload, response_id, proposal_id,
                    artifact_dir, now, now,
                ),
            )

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM web_cases WHERE case_id = ?", (case_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["case"] = json.loads(result.pop("case_json"))
        return result

    def list_cases(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM web_cases ORDER BY updated_at DESC, case_id"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["case"] = json.loads(item.pop("case_json"))
            result.append(item)
        return result

    def event(self, case_id: str, actor: str, kind: str, detail: dict[str, Any] | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO web_events (case_id, actor, kind, detail_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    case_id,
                    actor,
                    kind,
                    json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":")),
                    now_iso(),
                ),
            )

    def events(self, case_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM web_events WHERE case_id = ? ORDER BY event_id", (case_id,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["detail"] = json.loads(item.pop("detail_json"))
            result.append(item)
        return result
