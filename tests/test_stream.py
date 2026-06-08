from __future__ import annotations

from generation.stream import (
    ABS_EMBED_FLOOR,
    MAX_CONTEXT_CHUNKS,
    RELEVANCE_FLOOR,
    RELEVANCE_RATIO,
    _faq_answer,
    _is_relevant,
    _qna_fallback_msg,
    _route_manual,
)


def test_faq_answer_extracts_answer_only():
    text = "# 블루프린트 동기화가 안돼요?\n\n **답변** : 연결된 주차 삭제 시 동기화가 안 됩니다. 복원하세요.\n"
    assert _faq_answer(text) == "연결된 주차 삭제 시 동기화가 안 됩니다. 복원하세요."


def test_faq_answer_strips_image_and_keeps_link_phrase():
    text = ("# 문의는 어디에?\n\n **답변** : 문의는 Q&A 게시판으로 남겨주세요.\n\n"
            "- 메인 페이지 : Q&A 바로가기\n\n![image.png](/assets/x.png)\n")
    out = _faq_answer(text)
    assert "![" not in out
    assert "Q&A 바로가기" in out
    assert out.startswith("문의는 Q&A 게시판으로 남겨주세요.")


def test_route_manual_defaults_lms():
    # 자유 입력은 CMS 직접 언급이 없으면 항상 LMS(대다수 질문 보호).
    assert _route_manual("출결 현황 어떻게 조회하나요") == "LMS"
    assert _route_manual("주차학습에 콘텐츠 올리는 법") == "LMS"  # '콘텐츠'만으론 CMS 아님


def test_route_manual_cms_on_direct_mention():
    assert _route_manual("CMS에서 콘텐츠 등록 어떻게 하나요") == "CMS"
    assert _route_manual("cloud editor 편집 방법") == "CMS"
    assert _route_manual("클라우드 에디터 편집 도구") == "CMS"


def test_abs_embed_floor_in_calibrated_range():
    # 매뉴얼 내 질문 최저(~0.547)는 통과하고 명백한 헛질문(~0.50 이하)은 막도록 보정.
    # 과거 0.60은 실제 질문(사업계획서 0.547 등)을 막아 폐기됨.
    assert 0.40 < ABS_EMBED_FLOOR <= 0.55


def test_qna_fallback_includes_contact_and_board_phrase():
    msg = _qna_fallback_msg("교육혁신처 051-320-0000")
    assert "교육혁신처 051-320-0000" in msg
    assert "e-Class QnA 게시판" in msg   # 프론트가 하이퍼링크로 거는 문구
    assert "문의 부탁드립니다" in msg


def test_qna_fallback_without_contact():
    # 기본(연락처 없음): QnA 게시판만 안내, 전화번호 일절 없음.
    msg = _qna_fallback_msg("")
    assert msg == "준비된 매뉴얼 답변에서 확인되지 않는 질문입니다. e-Class QnA 게시판으로 문의 부탁드립니다."
    assert "051" not in msg and "☎" not in msg and "또는" not in msg


def test_is_relevant_requires_absolute_floor():
    # FLOOR 경계만 격리하려면 비율 조건이 항상 충족되도록 top_score=score로 둔다
    # (score >= score*RATIO 는 RATIO<=1 이면 항상 참).
    below = RELEVANCE_FLOOR - 0.01
    assert _is_relevant(below, below) is False  # 비율은 OK, FLOOR 미달 -> 탈락
    assert _is_relevant(RELEVANCE_FLOOR, RELEVANCE_FLOOR) is True


def test_is_relevant_requires_ratio_of_top():
    # 절대 바닥은 통과하지만 1위 대비 비율 미달이면 탈락
    top = 1.0
    just_below_ratio = top * RELEVANCE_RATIO - 0.01
    just_at_ratio = top * RELEVANCE_RATIO
    # FLOOR 영향을 배제하기 위해 둘 다 FLOOR 이상이 되도록 top을 키움
    if just_below_ratio < RELEVANCE_FLOOR:
        top = 1.0  # RATIO=0.6, FLOOR=0.3 -> 0.6*1.0=0.6 > 0.3 OK
        just_below_ratio = top * RELEVANCE_RATIO - 0.01
        just_at_ratio = top * RELEVANCE_RATIO
    assert _is_relevant(just_below_ratio, top) is False
    assert _is_relevant(just_at_ratio, top) is True


def test_is_relevant_both_conditions_required():
    # 비율은 통과하나 절대 바닥 미달: 작은 top에서 score가 비율은 넘어도 FLOOR 미달
    # top=0.4, RATIO=0.6 -> 임계 0.24, score=0.25는 비율 통과지만 FLOOR(0.3) 미달
    assert _is_relevant(0.25, 0.4) is False


def test_max_context_chunks_is_bounded():
    # #39 완화: 컨텍스트 청크 수에 상한이 있어야 무관 이웃 청크가 잘려나감
    assert isinstance(MAX_CONTEXT_CHUNKS, int)
    assert 1 <= MAX_CONTEXT_CHUNKS <= 5
