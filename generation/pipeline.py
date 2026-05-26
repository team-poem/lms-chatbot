from __future__ import annotations
import json
import os
from pathlib import Path
from typing import AsyncIterator

import httpx

from index.embed import Embedder, get_chroma, query_embed
from index.bm25_index import load_bm25, query_bm25
from retrieval.hybrid import combine_scores
from generation.persona import build_prompt
from generation.filters import clean_response, streaming_clean


SCORE_THRESHOLD = 0.25       # 1위 점수가 이 미만이면 "가이드에 없음" 정형 응답
TOP_K = 5                    # 하이브리드 검색 풀
RELEVANCE_FLOOR = 0.30       # 출처/컨텍스트에 포함될 최소 절대 점수
RELEVANCE_RATIO = 0.50       # 1위 점수의 이 비율 미만이면 노이즈로 간주 후 제외
EMBED_K = 20
BM25_K = 20
COLLECTION = "lms_chunks"


def _is_relevant(score: float, top_score: float) -> bool:
    """1위 대비 비율 + 절대 점수 둘 다 통과해야 진짜 연관."""
    return score >= RELEVANCE_FLOOR and score >= top_score * RELEVANCE_RATIO


class RagEngine:
    def __init__(self) -> None:
        self.embedder = Embedder()
        self.chroma = get_chroma(Path(os.environ.get("CHROMA_DIR", "./data/chroma")))
        self.bm25 = load_bm25(Path(os.environ.get("BM25_PATH", "./data/bm25.pkl")))
        self.ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "gemma3:4b")

    def _fetch_chunks(self, ids: list[str]) -> dict[str, dict]:
        coll = self.chroma.get_or_create_collection(COLLECTION)
        res = coll.get(ids=ids, include=["documents", "metadatas"])
        out: dict[str, dict] = {}
        for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
            out[cid] = {"text": doc, **meta}
        return out

    def retrieve(self, query: str) -> tuple[list[dict], float]:
        bm = dict(query_bm25(self.bm25, query, k=BM25_K))
        emb = dict(query_embed(self.chroma, self.embedder, query, k=EMBED_K))
        merged = combine_scores(bm, emb, k=TOP_K)
        if not merged:
            return [], 0.0
        chunk_map = self._fetch_chunks([cid for cid, _ in merged])
        contexts: list[dict] = []
        for cid, score in merged:
            c = chunk_map.get(cid)
            if not c:
                continue
            contexts.append({
                "chunk_id": cid,
                "score": score,
                "title": c.get("title", ""),
                "text": c.get("text", ""),
                "image_refs": [s for s in (c.get("image_refs") or "").split(",") if s],
                "source": c.get("source", ""),
                "notion_url": c.get("notion_url", "") or "",
            })
        top_score = merged[0][1]
        return contexts, top_score

    async def stream_chat(self, query: str) -> AsyncIterator[dict]:
        contexts, top_score = self.retrieve(query)
        if top_score < SCORE_THRESHOLD:
            yield {"type": "text", "delta": "해당 내용은 현재 가이드에서 확인이 어렵습니다. 교육혁신처 교수학습개발센터로 문의 부탁드립니다."}
            yield {"type": "done", "images": [], "sources": [], "score": top_score}
            return

        # 컨텍스트도 임계 통과한 것만 LLM 에 주입. 단 1위는 무조건 포함.
        relevant_ctx = [contexts[0]] + [c for c in contexts[1:] if _is_relevant(c["score"], top_score)]

        messages = build_prompt(query, [{"title": c["title"], "text": c["text"]} for c in relevant_ctx])
        url = f"{self.ollama_host}/api/chat"
        payload = {
            "model": self.model,
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
                        # 스트리밍은 이모지만 즉시 제거 (안전). 마크업은 종료 시 일괄.
                        yield {"type": "text", "delta": streaming_clean(delta)}
                    if obj.get("done"):
                        break

        # 스트림 종료: 누적 텍스트에 full 클린업 적용 후 프런트가 교체
        yield {"type": "text_final", "text": clean_response(raw_buf)}

        # 이미지도 연관성 통과한 청크에서만 수집 (관련 없는 캡처가 따라 나오지 않게)
        seen_imgs: list[str] = []
        for c in relevant_ctx:
            for img in c["image_refs"]:
                if img and img not in seen_imgs:
                    seen_imgs.append(img)
            if len(seen_imgs) >= 5:
                break
        # 출처 표시: 연관성 임계 통과 + CSV 파생(FAQ — ...) 제외 + 중복 제목 제거 + top-3.
        sources: list[dict] = []
        seen_titles: set[str] = set()
        for c in relevant_ctx:
            t = c["title"]
            if not t or t in seen_titles:
                continue
            if t.startswith("FAQ —"):
                continue
            sources.append({"title": t, "url": c.get("notion_url", "") or ""})
            seen_titles.add(t)
            if len(sources) >= 3:
                break
        yield {"type": "done", "images": seen_imgs[:5], "sources": sources, "score": top_score}
