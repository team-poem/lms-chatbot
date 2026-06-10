from generation.persona import FALLBACK_MARK, qna_fallback_msg


def test_qna_fallback_includes_contact_and_board_phrase():
    msg = qna_fallback_msg("교육혁신처 051-320-0000")
    assert "교육혁신처 051-320-0000" in msg
    assert "e-Class QnA 게시판" in msg   # 프론트가 하이퍼링크로 거는 문구
    assert "문의 부탁드립니다" in msg


def test_qna_fallback_without_contact():
    # 기본(연락처 없음): QnA 게시판만 안내, 전화번호 일절 없음.
    msg = qna_fallback_msg("")
    assert msg == "준비된 매뉴얼 답변에서 확인되지 않는 질문입니다. e-Class QnA 게시판으로 문의 부탁드립니다."
    assert "051" not in msg and "☎" not in msg and "또는" not in msg


def test_fallback_mark_is_substring_of_fallback_msg():
    # 식별 표지는 규칙 5 문구의 부분 문자열이어야 폴백 감지가 동작한다.
    assert FALLBACK_MARK in qna_fallback_msg("")
