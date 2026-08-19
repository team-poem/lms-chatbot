from generation.persona import FALLBACK_MARK, qna_fallback_msg


def test_qna_fallback_includes_contact_and_board_phrase():
    msg = qna_fallback_msg("교육혁신처 051-320-0000")
    assert "교육혁신처 051-320-0000" in msg
    assert "Q&A 게시판" in msg   # 프론트가 이 문구를 보고 게시판 버튼을 붙인다
    assert "문의해 주세요" in msg


def test_qna_fallback_without_contact():
    # 기본(연락처 없음): QnA 게시판만 안내, 전화번호 일절 없음.
    msg = qna_fallback_msg("")
    assert msg == "요청하신 내용에 대한 답변을 찾지 못했습니다.\n자세한 안내는 Q&A 게시판으로 문의해 주세요."
    assert "051" not in msg and "☎" not in msg and "또는" not in msg


def test_fallback_mark_is_substring_of_fallback_msg():
    # 식별 표지는 규칙 5 문구의 부분 문자열이어야 폴백 감지가 동작한다.
    assert FALLBACK_MARK in qna_fallback_msg("")
