from __future__ import annotations
from typing import AsyncIterator

from app_types import ChatEvent, Source
from generation.faq import faq_answer
from generation.filters import clean_response, streaming_clean
from generation.guardrail import is_meta_question
from generation.llm import chat_stream
from generation.persona import FALLBACK_MARK, build_prompt, qna_fallback_msg
from generation.relevance import doc_answers_question
from rag.state import RagState
from retrieval.search import doc_image_refs, hybrid_search
from tuning import (
    ABS_EMBED_CONFIDENT,
    ABS_EMBED_FLOOR,
    CMS_TRIGGERS,
    GEN_OPTIONS,
    GEN_TIMEOUT_S,
    MAX_CONTEXT_CHUNKS,
    MAX_IMAGES,
    RELEVANCE_FLOOR,
    RELEVANCE_RATIO,
    SCORE_THRESHOLD,
)


def _route_manual(query: str) -> str:
    """자유 입력 질문의 매뉴얼 스코프. 기본 LMS, CMS 직접 언급 시에만 CMS."""
    q = query.lower()
    return "CMS" if any(t in q for t in CMS_TRIGGERS) else "LMS"


def fallback_events(msg: str, *, score: float = 0.0) -> tuple[ChatEvent, ...]:
    """폴백 안내를 SSE 3-이벤트(text/text_final/done)로 만든다. 게이트 셋(메타
    질문·임베딩 바닥·관련성)이 같은 형태로 종료하던 중복을 모은 순수 함수."""
    return (
        ChatEvent(type="text", delta=msg),
        ChatEvent(type="text_final", text=msg),
        ChatEvent(type="done", score=score),
    )


def _is_relevant(score: float, top_score: float) -> bool:
    """1위 대비 비율 + 절대 점수 둘 다 통과해야 진짜 연관."""
    return score >= RELEVANCE_FLOOR and score >= top_score * RELEVANCE_RATIO


def _doc_images(
    state: RagState, doc_title: str, fallback_items, limit: int = MAX_IMAGES, *, manual: str = ""
) -> list[str]:
    """1순위 문서의 전 섹션 이미지(retrieval 조회, seq 순·중복 제거)를 모은다.
    컨텍스트 청크에만 의존할 때 생기는 누락을 막는다. 조회 실패/빈 결과면
    컨텍스트 청크(fallback_items)의 이미지로 대체한다."""
    refs = list(doc_image_refs(state, doc_title, manual=manual))
    if not refs:
        for it in fallback_items:
            for img in it.chunk.image_refs:
                if img and img not in refs:
                    refs.append(img)
    return refs[:limit]


async def stream_response(
    state: RagState, query: str, *, manual: str | None = None
) -> AsyncIterator[ChatEvent]:
    if is_meta_question(query):
        # 챗봇 자체/범위 밖 질문도 매뉴얼 밖 질문과 동일하게 QnA 안내로 통일한다.
        for evt in fallback_events(qna_fallback_msg(state.qna_contact)):
            yield evt
        return

    # 매뉴얼 스코프: 네비 클릭은 manual 을 명시(CMS 문서 → 'CMS'), 자유 입력은
    # 직접 언급 라우팅(기본 LMS). 검색이 매뉴얼 단위로 하드 격리된다.
    scope = manual if manual else _route_manual(query)
    retrieval = hybrid_search(state, query, manual=scope)
    top_score = retrieval.top_score
    # 매뉴얼에 근거가 없으면(절대 임베딩 유사도 바닥 미달 또는 정규화 점수 바닥 미달)
    # 답을 지어내지 않고 QnA 안내로 폴백한다.
    if retrieval.max_embed_sim < ABS_EMBED_FLOOR or top_score < SCORE_THRESHOLD:
        for evt in fallback_events(qna_fallback_msg(state.qna_contact), score=top_score):
            yield evt
        return

    # 컨텍스트: 점수 1위 + 1위 대비 충분히 가까운 형제. 임베딩(BGE-M3)이 강해 점수
    # 1위가 대체로 정답이다. (gemma:4b 재랭킹은 정답 문서를 오히려 버리는 등 신뢰도가
    # 낮아 제거 — 선별은 점수에 맡기고, gemma 는 생성만 한다.)
    items = retrieval.items
    relevant = (items[0],) + tuple(
        it for it in items[1:] if _is_relevant(it.score, top_score)
    )

    # 단일 문서 답변(1 질문 : 1 매뉴얼 문서): 1위 청크가 속한 문서의 청크만 남긴다.
    # 한 질문은 한 문서가 답하게 해서 곁가지 다른 문서가 출처·이미지로 섞이는 것을
    # 막는다(예: '응시 이력 조회'에 '퀴즈 통계 조회하기'가 딸려오는 것 차단). 같은
    # 문서의 여러 섹션(출결현황 조회의 하위 섹션 등)은 함께 유지돼 답이 완결된다.
    primary_doc = relevant[0].chunk.doc_title or relevant[0].chunk.source
    relevant = tuple(
        it for it in relevant
        if (it.chunk.doc_title or it.chunk.source) == primary_doc
    )
    relevant = relevant[:MAX_CONTEXT_CHUNKS]

    # 관련성 게이트: 점수 1위가 정규화상 높아도 매뉴얼 밖 질문일 수 있다(예: '주차장'이
    # '과목 복사' 문서에 0.57로 매칭). 임베딩 바닥으론 못 거른다. 단 강한 매칭
    # (임베딩 ≥ ABS_EMBED_CONFIDENT)은 검색이 확실히 맞춘 것이라 게이트를 건너뛴다 —
    # 애매 구간에서만 1위 문서가 실제로 답하는지 LLM 이진 판정을 받아 '아니오'면
    # 폴백한다. (LLM 오류 시 None → 통과: 답을 막지 않는다.)
    primary = relevant[0].chunk
    if retrieval.max_embed_sim < ABS_EMBED_CONFIDENT and await doc_answers_question(
        state.llm, query, primary.title, primary.text
    ) is False:
        for evt in fallback_events(qna_fallback_msg(state.qna_contact), score=top_score):
            yield evt
        return

    # FAQ 직출력: 추천 질문 등 FAQ 문서는 사람이 쓴 정답을 그대로 내보낸다(LLM
    # 우회). gemma:4b 가 짧은 FAQ 정답을 질문 되풀이·원인 누락으로 망가뜨리던 문제를
    # 차단한다. 사람이 쓴 정답을 다시 쓸 이유가 없으므로 백엔드와 무관하게 유지한다.
    # 가이드 문서는 길어 종전대로 LLM 이 생성한다.
    if primary.doc_set == "faq":
        answer = faq_answer(primary.text)
        yield ChatEvent(type="text", delta=answer)
        yield ChatEvent(type="text_final", text=answer)
        imgs = _doc_images(state, primary.doc_title, relevant, manual=primary.manual)
        sources: tuple[Source, ...] = ()
        if primary.doc_title and not primary.doc_title.startswith("FAQ —"):
            sources = (Source(title=primary.doc_title, url=primary.notion_url or ""),)
        yield ChatEvent(
            type="done", images=tuple(imgs), sources=sources, score=top_score
        )
        return

    messages = build_prompt(
        query,
        [{"title": it.chunk.title, "text": it.chunk.text} for it in relevant],
    )

    raw_buf = ""
    async for delta in chat_stream(
        state.llm,
        messages,
        options=GEN_OPTIONS,
        timeout=GEN_TIMEOUT_S,
    ):
        raw_buf += delta
        yield ChatEvent(type="text", delta=streaming_clean(delta))

    answer = clean_response(raw_buf)
    yield ChatEvent(type="text_final", text=answer)

    # gemma 가 (관련성 게이트를 통과한 문서로도) 답을 못 찾아 폴백 문구를 생성한 경우:
    # 엉뚱한 문서의 이미지·출처를 붙이지 않는다.
    if FALLBACK_MARK in answer:
        yield ChatEvent(type="done", score=top_score)
        return

    # 이미지 (상위 5장): 1순위 문서의 '모든 섹션'에서 seq 순으로 모은다. 컨텍스트에
    # 든 청크에만 의존하면 이미지가 검색 top-k 밖 섹션에 있을 때 누락된다(예: 성적
    # 메뉴). 단일 문서 기준이라 다른 문서 이미지 누수는 없다.
    seen_imgs = _doc_images(state, primary.doc_title, relevant, manual=primary.manual)

    # 출처: 1 질문 : 1 매뉴얼 문서 — 답에 쓴 문서를 한 건만 노출한다(섹션 단위가 아닌
    # 문서 단위 제목·링크). 'FAQ —'(답변 없는 CSV) 접두는 출처로 쓰지 않는다.
    sources: tuple[Source, ...] = ()
    if primary.doc_title and not primary.doc_title.startswith("FAQ —"):
        sources = (Source(title=primary.doc_title, url=primary.notion_url or ""),)

    yield ChatEvent(
        type="done",
        images=tuple(seen_imgs),
        sources=sources,
        score=top_score,
    )
