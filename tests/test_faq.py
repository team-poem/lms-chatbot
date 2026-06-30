from pathlib import Path

from generation.faq import faq_answer, parse_questions, pick
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


def test_faq_answer_extracts_answer_only():
    text = "# 블루프린트 동기화가 안돼요?\n\n **답변** : 연결된 주차 삭제 시 동기화가 안 됩니다. 복원하세요.\n"
    assert faq_answer(text) == "연결된 주차 삭제 시 동기화가 안 됩니다. 복원하세요."


def test_faq_answer_strips_image_and_keeps_link_phrase():
    text = ("# 문의는 어디에?\n\n **답변** : 문의는 Q&A 게시판으로 남겨주세요.\n\n"
            "- 메인 페이지 : Q&A 바로가기\n\n![image.png](/assets/x.png)\n")
    out = faq_answer(text)
    assert "![" not in out
    assert "Q&A 바로가기" in out
    assert out.startswith("문의는 Q&A 게시판으로 남겨주세요.")
