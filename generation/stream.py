from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from app_types import ChatEvent, Source
from generation.filters import clean_response, streaming_clean
from generation.guardrail import META_REPLY, is_meta_question
from generation.persona import build_prompt
from rag.state import RagState
from retrieval.search import hybrid_search


SCORE_THRESHOLD = 0.25
RELEVANCE_FLOOR = 0.30
RELEVANCE_RATIO = 0.50
NO_GUIDE_MSG = (
    "해당 내용은 현재 가이드에서 확인이 어렵습니다. "
    "교육혁신처 교수학습개발센터로 문의 부탁드립니다."
)


def _is_relevant(score: float, top_score: float) -> bool:
    """1위 대비 비율 + 절대 점수 둘 다 통과해야 진짜 연관."""
    return score >= RELEVANCE_FLOOR and score >= top_score * RELEVANCE_RATIO


async def stream_response(state: RagState, query: str) -> AsyncIterator[ChatEvent]:
    if is_meta_question(query):
        yield ChatEvent(type="text", delta=META_REPLY)
        yield ChatEvent(type="text_final", text=META_REPLY)
        yield ChatEvent(type="done")
        return

    retrieval = hybrid_search(state, query)
    top_score = retrieval.top_score
    if top_score < SCORE_THRESHOLD:
        yield ChatEvent(type="text", delta=NO_GUIDE_MSG)
        yield ChatEvent(type="text_final", text=NO_GUIDE_MSG)
        yield ChatEvent(type="done", score=top_score)
        return

    # 컨텍스트: 1위는 무조건, 2위부터 임계 통과만
    items = retrieval.items
    relevant = (items[0],) + tuple(
        it for it in items[1:] if _is_relevant(it.score, top_score)
    )

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

    # 출처 (top-3, 'FAQ —' 접두 제외)
    sources: list[Source] = []
    seen_titles: set[str] = set()
    for it in relevant:
        t = it.chunk.title
        if not t or t in seen_titles:
            continue
        if t.startswith("FAQ —"):
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
