from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from app_types import ChatEvent, ScoredChunk, Source
from generation.filters import clean_response, streaming_clean
from generation.guardrail import META_REPLY, is_meta_question
from generation.persona import build_prompt
from rag.state import RagState
from retrieval.search import hybrid_search


SCORE_THRESHOLD = 0.25
# 절대 임베딩 유사도 바닥. top_score 는 후보 집합 내 정규화값이라 off-topic·거짓
# 전제 질문에도 높게 나와(거의 항상 ≥0.6) 폴백 게이트로 무력하다. 원시 임베딩
# 유사도(정규화 전)는 절대 연관도를 재므로, 가이드에 실제로 다뤄지지 않는 질문에
# 절차를 지어내는 환각을 막는다. 실측 분리 지점: 실제 FAQ 최저 0.634, 폴백 대상
# (off-topic·거짓 전제) 최고 0.592 → 그 사이 0.60.
ABS_EMBED_FLOOR = 0.60
RELEVANCE_FLOOR = 0.30
RELEVANCE_RATIO = 0.60
# 컨텍스트로 LLM에 넘기는 청크 수 상한. 1위(정답) 외에 의미적으로 유사하지만
# 다른 주제의 청크가 섞여 답변을 오염시키는 것을 막는다(#39). 1위는 항상 포함.
MAX_CONTEXT_CHUNKS = 3
# 출처(사용자에게 노출) 표시는 컨텍스트 포함보다 엄격하게 — 1위에 충분히 근접한
# 청크만 출처로 표시한다. 보조 컨텍스트로는 쓰되 약하게 관련된 이웃 문서가 출처
# 목록에 노출되는 것을 막는다(#39 출처 오염).
SOURCE_RATIO = 0.85


def _qna_fallback_msg(qna_board_url: str, qna_contact: str = "") -> str:
    """매뉴얼(준비된 답변)에서 근거를 못 찾은 질문에 대한 안내. QnA 게시판 링크와
    문의처가 설정돼 있으면 함께 안내한다."""
    lines = ["준비된 매뉴얼 답변에서 확인되지 않는 질문입니다. 자세한 사항은 QnA 게시판으로 문의해 주세요."]
    if qna_board_url:
        lines.append(f"QnA 게시판: {qna_board_url}")
    if qna_contact:
        lines.append(f"문의처: {qna_contact}")
    return "\n".join(lines)


def _has_grounding(max_embed_sim: float) -> bool:
    """질문이 가이드에서 실제로 다뤄지는가(절대 임베딩 유사도 기준)."""
    return max_embed_sim >= ABS_EMBED_FLOOR


def _is_relevant(score: float, top_score: float) -> bool:
    """1위 대비 비율 + 절대 점수 둘 다 통과해야 진짜 연관."""
    return score >= RELEVANCE_FLOOR and score >= top_score * RELEVANCE_RATIO


def _is_source_worthy(score: float, top_score: float) -> bool:
    """출처로 노출할 만큼 1위에 근접한가. 컨텍스트 포함보다 엄격."""
    return score >= top_score * SOURCE_RATIO


def _section_images(relevant: tuple[ScoredChunk, ...], limit: int = 5) -> tuple[str, ...]:
    """이미지는 1위 청크가 속한 섹션(같은 section_id)에서만 모은다. 다른 섹션이
    텍스트 컨텍스트로 끌려와도 이미지엔 기여하지 못하게 해, 형제 섹션 이미지가
    답변에 새는 것을 구조적으로 차단한다(수치 임계값 비의존). section_id 가 비어
    있으면(구 인덱스·CSV 등) 1위 청크 하나로만 제한한다."""
    if not relevant:
        return ()
    top = relevant[0]
    top_sid = top.chunk.section_id
    seen: list[str] = []
    for it in relevant:
        # 빈 section_id(구 인덱스·CSV)면 동등(==)이 아니라 1위 객체 자체(is)로만 한정.
        same = (it.chunk.section_id == top_sid) if top_sid else (it is top)
        if not same:
            continue
        for img in it.chunk.image_refs:
            if img and img not in seen:
                seen.append(img)
        if len(seen) >= limit:
            break
    return tuple(seen[:limit])


async def stream_response(state: RagState, query: str) -> AsyncIterator[ChatEvent]:
    if is_meta_question(query):
        yield ChatEvent(type="text", delta=META_REPLY)
        yield ChatEvent(type="text_final", text=META_REPLY)
        yield ChatEvent(type="done")
        return

    retrieval = hybrid_search(state, query)
    top_score = retrieval.top_score
    # 매뉴얼에 근거가 없으면(off-topic·거짓 전제·짧거나 모호한 질문 포함) 답을 만들지
    # 않고 QnA 게시판으로 안내한다. 절대 임베딩 유사도 + (정규화)점수 중 하나라도 바닥
    # 미달이면 폴백. 인사·범위·역량 입력도 여기로 떨어진다(말투 대응은 목표가 아님).
    if retrieval.max_embed_sim < ABS_EMBED_FLOOR or top_score < SCORE_THRESHOLD:
        msg = _qna_fallback_msg(state.qna_board_url, state.qna_contact)
        yield ChatEvent(type="text", delta=msg)
        yield ChatEvent(type="text_final", text=msg)
        yield ChatEvent(type="done", score=top_score)
        return

    # 컨텍스트: 1위는 무조건, 2위부터 임계 통과만, 그리고 상한 적용
    items = retrieval.items
    relevant = (items[0],) + tuple(
        it for it in items[1:] if _is_relevant(it.score, top_score)
    )
    relevant = relevant[:MAX_CONTEXT_CHUNKS]

    messages = build_prompt(
        query,
        [{"title": it.chunk.title, "text": it.chunk.text} for it in relevant],
    )
    url = f"{state.ollama_host}/api/chat"
    payload = {
        "model": state.ollama_model,
        "messages": messages,
        "stream": True,
        "options": {"num_ctx": 8192, "temperature": 0.2},
    }

    raw_buf = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
        async with client.stream("POST", url, json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                delta = obj.get("message", {}).get("content", "")
                if delta:
                    raw_buf += delta
                    yield ChatEvent(type="text", delta=streaming_clean(delta))
                if obj.get("done"):
                    break

    yield ChatEvent(type="text_final", text=clean_response(raw_buf))

    # 이미지 (상위 5장): 1위 섹션에서만 수집해 형제 섹션 이미지 누수를 차단.
    seen_imgs = list(_section_images(relevant))

    # 출처 (top-3, 'FAQ —' 접두 제외). 컨텍스트보다 엄격한 기준으로, 1위에
    # 충분히 근접한 청크만 출처로 노출한다(약하게 관련된 이웃 문서 배제).
    sources: list[Source] = []
    seen_titles: set[str] = set()
    for it in relevant:
        t = it.chunk.title
        if not t or t in seen_titles:
            continue
        if t.startswith("FAQ —"):
            continue
        if not _is_source_worthy(it.score, top_score):
            continue
        sources.append(Source(title=t, url=it.chunk.notion_url or ""))
        seen_titles.add(t)
        if len(sources) >= 3:
            break

    yield ChatEvent(
        type="done",
        images=tuple(seen_imgs),
        sources=tuple(sources),
        score=top_score,
    )
