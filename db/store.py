from __future__ import annotations
import csv
import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from db.schema import SCHEMA


_CSV_FIELDS = (
    "turn_id", "session_id", "created_at", "query", "response",
    "retrieved_sources", "retrieved_score", "latency_ms",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _sources_default(o):
    """Source / 기타 dataclass 를 JSON 직렬화 시 dict 변환."""
    if hasattr(o, "__dataclass_fields__"):
        return {f: getattr(o, f) for f in o.__dataclass_fields__}
    raise TypeError(f"not serializable: {type(o)}")


def init_schema(db_path: Path) -> None:
    with _conn(db_path) as c:
        c.executescript(SCHEMA)


def new_session(db_path: Path, *, consent_version: str, user_label: str | None) -> str:
    sid = uuid.uuid4().hex
    ts = _now()
    with _conn(db_path) as c:
        c.execute(
            "INSERT INTO sessions(session_id, created_at, consent_version, consent_at, user_label) "
            "VALUES (?,?,?,?,?)",
            (sid, ts, consent_version, ts, user_label),
        )
    return sid


def get_session(db_path: Path, session_id: str) -> dict | None:
    with _conn(db_path) as c:
        r = c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(r) if r else None


def add_turn(db_path: Path, *, session_id: str, query: str, response: str,
             retrieved_sources: list, retrieved_score: float | None,
             latency_ms: int | None) -> int:
    with _conn(db_path) as c:
        cur = c.execute(
            "INSERT INTO turns(session_id, created_at, query, response, retrieved_sources, "
            "retrieved_score, latency_ms) VALUES (?,?,?,?,?,?,?)",
            (session_id, _now(), query, response,
             json.dumps(retrieved_sources, ensure_ascii=False, default=_sources_default),
             retrieved_score, latency_ms),
        )
        return int(cur.lastrowid)


def list_turns(db_path: Path, *, limit: int = 100, offset: int = 0) -> list[dict]:
    """기록된 턴을 최신순으로 반환(관리자 조회/내보내기용)."""
    with _conn(db_path) as c:
        rs = c.execute(
            "SELECT turn_id, session_id, created_at, query, response, "
            "retrieved_sources, retrieved_score, latency_ms "
            "FROM turns ORDER BY turn_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rs]


def count_turns(db_path: Path) -> int:
    """기록된 전체 턴 수."""
    with _conn(db_path) as c:
        return int(c.execute("SELECT COUNT(*) FROM turns").fetchone()[0])


def turns_to_csv(turns: list[dict]) -> str:
    """list_turns 결과를 CSV 문자열로 직렬화(관리자 내보내기용)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(_CSV_FIELDS), extrasaction="ignore")
    w.writeheader()
    for t in turns:
        w.writerow(t)
    return buf.getvalue()


def add_feedback(db_path: Path, *, turn_id: int, rating: int, comment: str | None) -> None:
    with _conn(db_path) as c:
        c.execute(
            "INSERT INTO feedback(turn_id, rating, comment, created_at) VALUES (?,?,?,?)",
            (turn_id, rating, comment, _now()),
        )


def feedback_for(db_path: Path, turn_id: int) -> list[dict]:
    with _conn(db_path) as c:
        rs = c.execute("SELECT * FROM feedback WHERE turn_id = ?", (turn_id,)).fetchall()
        return [dict(r) for r in rs]


def purge_session(db_path: Path, session_id: str) -> None:
    with _conn(db_path) as c:
        c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
