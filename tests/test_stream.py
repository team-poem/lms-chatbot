from __future__ import annotations

from generation.stream import (
    ABS_EMBED_FLOOR,
    MAX_CONTEXT_CHUNKS,
    RELEVANCE_FLOOR,
    RELEVANCE_RATIO,
    SOURCE_RATIO,
    _has_grounding,
    _is_relevant,
    _is_source_worthy,
)


def test_abs_embed_floor_separates_faq_from_false_premise():
    # 실측(80 FAQ vs false-premise/off-topic): 실제 질문 최저 raw 임베딩 유사도 0.634,
    # 폴백 대상 최고 0.592. 그 사이에 임계가 놓여 회귀 0 + 환각 차단을 동시에 만족.
    assert 0.592 < ABS_EMBED_FLOOR < 0.634
    assert _has_grounding(0.634) is True   # 실제 FAQ 최저 -> 답변
    assert _has_grounding(0.592) is False  # 폴백 대상 최고 -> 폴백


def test_has_grounding_is_inclusive_at_floor():
    assert _has_grounding(ABS_EMBED_FLOOR) is True
    assert _has_grounding(ABS_EMBED_FLOOR - 0.001) is False


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


def test_source_ratio_stricter_than_relevance_ratio():
    # 출처 표시는 컨텍스트 포함보다 엄격해야 약하게 관련된 청크가 출처에 노출되지 않음
    assert SOURCE_RATIO > RELEVANCE_RATIO


def test_is_source_worthy_excludes_weak_neighbor():
    # #39 출처 오염: 1위=1.0, 무관 이웃=0.601 (RELEVANCE_RATIO=0.6은 간신히 통과하나
    # SOURCE_RATIO 기준으로는 출처에서 제외돼야 함)
    assert _is_source_worthy(1.0, 1.0) is True
    assert _is_source_worthy(0.601, 1.0) is False


def test_is_source_worthy_keeps_strong_neighbor():
    # 1위에 충분히 근접한 청크는 출처로 유지
    assert _is_source_worthy(0.95, 1.0) is True


import asyncio

from app_types import Retrieval
from generation import stream as stream_mod


def _finals(query):
    async def run():
        out = []
        async for ev in stream_mod.stream_response(None, query):
            if ev.type == "text_final":
                out.append(ev.text)
        return out
    return asyncio.run(run())


def test_help_request_short_circuits_before_retrieval(monkeypatch):
    def boom(state, q):
        raise AssertionError("retrieval must not run for help requests")
    monkeypatch.setattr(stream_mod, "hybrid_search", boom)
    finals = _finals("어떤걸 가이드 받을수잇죠?")
    assert finals and "도와드릴 수 있어요" in finals[0]


def test_topic_declaration_short_circuits_before_retrieval(monkeypatch):
    def boom(state, q):
        raise AssertionError("retrieval must not run for topic declarations")
    monkeypatch.setattr(stream_mod, "hybrid_search", boom)
    finals = _finals("강의 운영 관련해서 문의하고 싶어요")
    assert finals and "강의 운영" in finals[0]


def test_scope_question_short_circuits_to_social(monkeypatch):
    def boom(state, q):
        raise AssertionError("retrieval must not run for scope questions")
    monkeypatch.setattr(stream_mod, "hybrid_search", boom)
    finals = _finals("lms에 대해서?")
    assert finals and "LMS 사용법을 안내" in finals[0]


def test_real_question_falls_through_to_gate(monkeypatch):
    # 임베딩이 낮으면 게이트가 거절(NO_GUIDE_MSG) → 라우팅이 게이트까지 도달했음을 증명.
    low = Retrieval(items=(), top_score=0.0, max_embed_sim=0.0)
    monkeypatch.setattr(stream_mod, "hybrid_search", lambda state, q: low)
    finals = _finals("오늘 점심 뭐 먹지?")
    assert finals and "확인이 어렵습니다" in finals[0]
