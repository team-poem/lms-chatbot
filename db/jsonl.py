"""세션별 JSONL 대화 로그 — 분석용 사본.

소스 오브 트루스는 SQLite(chat_logs.db)다. 여기 쓰기가 실패해도 채팅
응답은 죽으면 안 되므로 오류는 stderr 로만 흘리고 삼킨다.

ponytail: 단일 프로세스 전제의 무락 append. 다중 워커로 가면 세션이
워커에 고정되지 않아 줄 인터리브가 생길 수 있다 — 그때 파일 락 추가.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HEX = set("0123456789abcdef")


def sessions_dir(logs_dir: Path) -> Path:
    return logs_dir / "sessions"


def session_path(logs_dir: Path, session_id: str) -> Path | None:
    """세션 JSONL 경로. session_id 는 uuid4().hex 여야 한다 — 외부 입력이
    파일명이 되는 지점이라 hex 이외가 섞이면 거부한다."""
    if not session_id or not set(session_id) <= _HEX:
        return None
    return sessions_dir(logs_dir) / f"{session_id}.jsonl"


def append(logs_dir: Path, session_id: str, record: dict) -> None:
    path = session_path(logs_dir, session_id)
    if path is None:
        print(f"jsonl: invalid session_id {session_id!r}", file=sys.stderr)
        return
    try:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as e:
        print(f"jsonl: append failed for {session_id}: {e}", file=sys.stderr)


def purge(logs_dir: Path, session_id: str) -> None:
    path = session_path(logs_dir, session_id)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        print(f"jsonl: purge failed for {session_id}: {e}", file=sys.stderr)
