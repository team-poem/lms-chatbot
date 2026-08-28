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


def test_list_turns_returns_newest_first(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    t1 = store.add_turn(db_path, session_id=sid, query="q1", response="r1",
                        retrieved_sources=[], retrieved_score=0.1, latency_ms=10)
    t2 = store.add_turn(db_path, session_id=sid, query="q2", response="r2",
                        retrieved_sources=[], retrieved_score=0.2, latency_ms=20)
    rows = store.list_turns(db_path)
    assert [r["turn_id"] for r in rows] == [t2, t1]  # 최신순
    assert rows[0]["query"] == "q2"
    assert store.count_turns(db_path) == 2


def test_list_turns_respects_limit_and_offset(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    ids = [store.add_turn(db_path, session_id=sid, query=f"q{i}", response="r",
                          retrieved_sources=[], retrieved_score=0.0, latency_ms=0)
           for i in range(5)]
    page = store.list_turns(db_path, limit=2, offset=1)
    # 최신순(5,4,3,2,1)에서 offset 1, limit 2 → ids[3], ids[2]
    assert [r["turn_id"] for r in page] == [ids[3], ids[2]]


def test_turns_to_csv_has_header_and_rows(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    store.add_turn(db_path, session_id=sid, query="안녕", response="반가워요",
                   retrieved_sources=[], retrieved_score=0.5, latency_ms=12)
    csv_text = store.turns_to_csv(store.list_turns(db_path))
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("turn_id,session_id")  # 헤더
    assert "안녕" in csv_text
    assert len(lines) == 2  # 헤더 + 1행


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


def _jsonl_lines(db_path: Path, sid: str) -> list[dict]:
    import json
    p = db_path.parent / "sessions" / f"{sid}.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]


def test_jsonl_mirrors_session_turn_feedback(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    tid = store.add_turn(db_path, session_id=sid, query="퀴즈?", response="이렇게.",
                         retrieved_sources=[], retrieved_score=0.7, latency_ms=420,
                         model="gemini-2.5-flash", manual="LMS", pinned=False)
    store.add_feedback(db_path, turn_id=tid, rating=3, comment="굿")
    lines = _jsonl_lines(db_path, sid)
    assert [l["type"] for l in lines] == ["session_start", "turn", "feedback"]
    turn = lines[1]
    assert turn["turn_id"] == tid and turn["model"] == "gemini-2.5-flash"
    assert turn["manual"] == "LMS" and turn["pinned"] is False
    assert lines[2]["rating"] == 3


def test_jsonl_appends_per_turn(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    for q in ("q1", "q2"):
        store.add_turn(db_path, session_id=sid, query=q, response="r",
                       retrieved_sources=[], retrieved_score=0.0, latency_ms=0)
    assert len(_jsonl_lines(db_path, sid)) == 3  # session_start + 2 turns


def test_purge_session_removes_jsonl(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    p = db_path.parent / "sessions" / f"{sid}.jsonl"
    assert p.exists()
    store.purge_session(db_path, sid)
    assert not p.exists()


def test_jsonl_failure_does_not_break_add_turn(tmp_path: Path, capsys):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    # sessions 디렉터리 자리를 파일로 막아 append 를 실패시킨다
    sess_dir = db_path.parent / "sessions"
    import shutil
    shutil.rmtree(sess_dir)
    sess_dir.write_text("block")
    tid = store.add_turn(db_path, session_id=sid, query="q", response="r",
                         retrieved_sources=[], retrieved_score=0.0, latency_ms=0)
    assert tid > 0  # SQLite 기록은 살아있다
    assert "jsonl: append failed" in capsys.readouterr().err
