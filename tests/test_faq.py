from pathlib import Path

from generation.faq import _find_faq_csv, faq_answer, parse_questions, pick, plain_answer
from tuning import FAQ_TOP, FAQ_TOP_FIXED, FAQ_TOP_PINS


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


def test_faq_top_labels_display_only_emoji():
    # 첫 화면은 고정 TOP 목록을 노출한다는 결정(2026-08-19). 라벨의 메달 이모지는
    # 표시용 — 전송 질문에 섞이면 임베딩 매칭이 흔들릴 수 있어 전송 텍스트에는 없어야 한다.
    assert len(FAQ_TOP) == 3  # 4·5번은 준비될 때까지 숨김(핀은 유지)
    for label, text in FAQ_TOP:
        assert not any(ch in text for ch in "🥇🥈🥉🏅")
        assert text == label.lstrip("🥇🥈🥉🏅 ")  # 라벨 = 메달 + 전송 텍스트


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


def test_find_faq_csv_prefers_all_suffix(tmp_path):
    """뷰별 CSV 는 필터가 걸린 부분집합일 수 있어 전체(_all)가 우선이다."""
    (tmp_path / "LMS FAQ DATABASE view.csv").write_text("FAQ\n일부\n", encoding="utf-8-sig")
    (tmp_path / "LMS FAQ DATABASE abc_all.csv").write_text("FAQ\n전체\n", encoding="utf-8-sig")
    assert _find_faq_csv(tmp_path).name.endswith("_all.csv")


def test_find_faq_csv_falls_back_without_all_suffix(tmp_path):
    """HTML export 에는 `_all.csv` 가 없다. 폴백이 없으면 첫 진입 FAQ 칩이
    조용히 통째로 비어버린다(실제로 겪은 회귀)."""
    (tmp_path / "LMS FAQ DATABASE 3560163e.csv").write_text("FAQ\n질문\n", encoding="utf-8-sig")
    found = _find_faq_csv(tmp_path)
    assert found is not None
    assert parse_questions(found) == ("질문",)


def test_find_faq_csv_returns_none_when_absent(tmp_path):
    # 없으면 첫 진입 제안만 graceful 하게 생략된다(예외 아님).
    assert _find_faq_csv(tmp_path) is None


def test_plain_answer_strips_markers_the_frontend_would_show_literally():
    """프론트는 마크다운을 파싱하지 않는다(ui.setAnswerText 는 escapeHtml→innerHTML).
    남은 마커는 렌더링되지 않고 문자 그대로 보이므로 여기서 걷어낸다."""
    src = "# 제목\n\n본문 **강조** 입니다.\n\n![](/assets/a.png)\n\n다음 줄"
    out = plain_answer(src)
    assert "#" not in out
    assert "**" not in out
    assert "![](" not in out
    assert "본문 강조 입니다." in out
    assert "다음 줄" in out


def test_plain_answer_keeps_table_pipes():
    # 평문으로도 열 구분이 읽히고, 대안이 더 낫다는 근거가 없다.
    assert "|" in plain_answer("출결방식 | 메뉴명 | 내용")


def test_faq_answer_still_strips_label():
    assert faq_answer("# Q\n\n**답변** : 내용") == "내용"


def test_faq_top_pins_are_wellformed():
    """핀은 숨긴 질문에도 걸려 있을 수 있다(직접 입력 시험용). 형식만 고정한다 —
    (manual, 제목) 이 유효하고, 고정 문안 질문과 겹치지 않아야 한다(겹치면 어느
    쪽이 이기는지가 병합 순서에 달린 조용한 우연이 된다)."""
    for manual, title in FAQ_TOP_PINS.values():
        assert manual in ("LMS", "CMS") and title
    assert not set(FAQ_TOP_PINS) & set(FAQ_TOP_FIXED)


def test_faq_top_fixed_gold_answer_carries_download_link():
    """🥇 질문의 답은 자료실 링크 안내가 전부다(2026-08-19 결정). 링크가 빠지면
    안내문만 남는 빈 답이 된다."""
    ans = FAQ_TOP_FIXED["원격수업, 블렌디드수업, 플립러닝 수업 운영 방법"]
    assert "https://dcms.dongseo.ac.kr/em/6a7c05f03e7d6" in ans
