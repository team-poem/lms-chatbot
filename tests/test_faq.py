from pathlib import Path

from generation.faq import parse_questions, pick
from tuning import FAQ_ENTRY_MAX, FAQ_ENTRY_MIN


def _write_csv(tmp_path: Path, rows: str) -> Path:
    p = tmp_path / "LMS FAQ DATABASE abc_all.csv"
    p.write_text(rows, encoding="utf-8-sig")
    return p


def test_parse_questions_reads_question_column(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "FAQ,메뉴명\n로그인이 안 돼요?,기본\n과제는 어떻게 내나요?,과제\n",
    )
    assert parse_questions(csv_path) == ("로그인이 안 돼요?", "과제는 어떻게 내나요?")


def test_parse_questions_skips_empty_and_dedupes(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "FAQ,메뉴명\n질문 A,x\n,y\n질문 A,z\n질문 B,w\n",
    )
    assert parse_questions(csv_path) == ("질문 A", "질문 B")


def test_pick_returns_n_unique():
    pool = tuple(f"q{i}" for i in range(20))
    got = pick(pool, 6)
    assert len(got) == 6
    assert len(set(got)) == 6
    assert all(q in pool for q in got)


def test_pick_caps_at_pool_size():
    pool = ("a", "b", "c")
    assert sorted(pick(pool, 99)) == ["a", "b", "c"]


def test_pick_non_positive_returns_empty():
    pool = ("a", "b")
    assert pick(pool, 0) == []
    assert pick(pool, -3) == []


def test_pick_empty_pool():
    assert pick((), 5) == []


def test_entry_range_is_sane():
    assert 1 <= FAQ_ENTRY_MIN <= FAQ_ENTRY_MAX
