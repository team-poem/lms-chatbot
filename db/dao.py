from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from db.schema import SCHEMA


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _conn(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)

    def new_session(self, *, consent_version: str, user_label: str | None) -> str:
        sid = uuid.uuid4().hex
        ts = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO sessions(session_id, created_at, consent_version, consent_at, user_label) VALUES (?,?,?,?,?)",
                (sid, ts, consent_version, ts, user_label),
            )
        return sid

    def get_session(self, session_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            return dict(r) if r else None

    def add_turn(self, *, session_id: str, query: str, response: str,
                 retrieved_sources: list[str], retrieved_score: float | None,
                 latency_ms: int | None) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO turns(session_id, created_at, query, response, retrieved_sources, retrieved_score, latency_ms) VALUES (?,?,?,?,?,?,?)",
                (session_id, _now(), query, response, json.dumps(retrieved_sources, ensure_ascii=False), retrieved_score, latency_ms),
            )
            return int(cur.lastrowid)

    def add_feedback(self, *, turn_id: int, rating: int, comment: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO feedback(turn_id, rating, comment, created_at) VALUES (?,?,?,?)",
                (turn_id, rating, comment, _now()),
            )

    def feedback_for(self, turn_id: int) -> list[dict]:
        with self._conn() as c:
            rs = c.execute("SELECT * FROM feedback WHERE turn_id = ?", (turn_id,)).fetchall()
            return [dict(r) for r in rs]

    def purge_session(self, session_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
