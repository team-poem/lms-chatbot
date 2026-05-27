from pathlib import Path

from db import store


def test_consent_and_session_roundtrip(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label="강민")
    s = store.get_session(db_path, sid)
    assert s["consent_version"] == "v1"
    assert s["user_label"] == "강민"


def test_turn_and_feedback(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    tid = store.add_turn(
        db_path,
        session_id=sid, query="퀴즈?", response="이렇게.",
        retrieved_sources=["퀴즈 개요"], retrieved_score=0.7, latency_ms=420,
    )
    assert tid > 0
    store.add_feedback(db_path, turn_id=tid, rating=3, comment="도움됨")
    fs = store.feedback_for(db_path, tid)
    assert fs[0]["rating"] == 3
    assert fs[0]["comment"] == "도움됨"


def test_purge_session(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    tid = store.add_turn(db_path, session_id=sid, query="q", response="r",
                         retrieved_sources=[], retrieved_score=0.0, latency_ms=0)
    store.add_feedback(db_path, turn_id=tid, rating=2, comment=None)
    store.purge_session(db_path, sid)
    assert store.get_session(db_path, sid) is None
    assert store.feedback_for(db_path, tid) == []
