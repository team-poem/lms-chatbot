from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from app_types import ChatEvent, Source
from generation.filters import clean_response, streaming_clean
from generation.guardrail import (
    META_REPLY,
    UNSAFE_REPLY,
    is_meta_question,
    is_unsafe_request,
)
from generation.persona import build_prompt
from rag.state import RagState
from retrieval.search import hybrid_search


SCORE_THRESHOLD = 0.25
RELEVANCE_FLOOR = 0.30
RELEVANCE_RATIO = 0.60
# 컨텍스트로 LLM에 넘기는 청크 수 상한. 1위(정답) 외에 의미적으로 유사하지만
# 다른 주제의 청크가 섞여 답변을 오염시키는 것을 막는다(#39). 1위는 항상 포함.
MAX_CONTEXT_CHUNKS = 3
# 출처(사용자에게 노출) 표시는 컨텍스트 포함보다 엄격하게 — 1위에 충분히 근접한
# 청크만 출처로 표시한다. 보조 컨텍스트로는 쓰되 약하게 관련된 이웃 문서가 출처
# 목록에 노출되는 것을 막는다(#39 출처 오염).
SOURCE_RATIO = 0.85
NO_GUIDE_MSG = (
    "해당 내용은 현재 가이드에서 확인이 어렵습니다. "
    "교육혁신처 교수학습개발센터로 문의 부탁드립니다."
)


def _is_relevant(score: float, top_score: float) -> bool:
    """1위 대비 비율 + 절대 점수 둘 다 통과해야 진짜 연관."""
    return score >= RELEVANCE_FLOOR and score >= top_score * RELEVANCE_RATIO


def _is_source_worthy(score: float, top_score: float) -> bool:
    """출처로 노출할 만큼 1위에 근접한가. 컨텍스트 포함보다 엄격."""
    return score >= top_score * SOURCE_RATIO


async def stream_response(state: RagState, query: str) -> AsyncIterator[ChatEvent]:
    if is_meta_question(query):
        yield ChatEvent(type="text", delta=META_REPLY)
        yield ChatEvent(type="text_final", text=META_REPLY)
        yield ChatEvent(type="done")
        return

    # 민감·악의 요청은 검색 전에 결정적으로 차단. 민감 키워드가 LMS 가이드 어휘와
    # 겹쳐 검색 점수가 높게 나와도(SCORE_THRESHOLD 통과) LLM에 도달하지 못하게 한다.
    if is_unsafe_request(query):
        yield ChatEvent(type="text", delta=UNSAFE_REPLY)
        yield ChatEvent(type="text_final", text=UNSAFE_REPLY)
        yield ChatEvent(type="done")
        return

    retrieval = hybrid_search(state, query)
    top_score = retrieval.top_score
    if top_score < SCORE_THRESHOLD:
        yield ChatEvent(type="text", delta=NO_GUIDE_MSG)
        yield ChatEvent(type="text_final", text=NO_GUIDE_MSG)
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

    # 이미지 (상위 5장, 중복 제거, 등장 순서 보존)
    seen_imgs: list[str] = []
    for it in relevant:
        for img in it.chunk.image_refs:
            if img and img not in seen_imgs:
                seen_imgs.append(img)
        if len(seen_imgs) >= 5:
            break

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
        images=tuple(seen_imgs[:5]),
        sources=tuple(sources),
        score=top_score,
    )
