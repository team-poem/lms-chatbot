from pathlib import Path
from db.dao import Database


def test_consent_and_session_roundtrip(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.init()
    sid = db.new_session(consent_version="v1", user_label="강민")
    s = db.get_session(sid)
    assert s["consent_version"] == "v1"
    assert s["user_label"] == "강민"


def test_turn_and_feedback(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.init()
    sid = db.new_session(consent_version="v1", user_label=None)
    tid = db.add_turn(
        session_id=sid, query="퀴즈?", response="이렇게.",
        retrieved_sources=["퀴즈 개요"], retrieved_score=0.7, latency_ms=420,
    )
    assert tid > 0
    db.add_feedback(turn_id=tid, rating=3, comment="도움됨")
    fs = db.feedback_for(tid)
    assert fs[0]["rating"] == 3
    assert fs[0]["comment"] == "도움됨"


def test_purge_session(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.init()
    sid = db.new_session(consent_version="v1", user_label=None)
    tid = db.add_turn(session_id=sid, query="q", response="r",
                      retrieved_sources=[], retrieved_score=0.0, latency_ms=0)
    db.add_feedback(turn_id=tid, rating=2, comment=None)
    db.purge_session(sid)
    assert db.get_session(sid) is None
    assert db.feedback_for(tid) == []
