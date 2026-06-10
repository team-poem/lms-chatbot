from __future__ import annotations

from app_types import Chunk, Retrieval, ScoredChunk
from index.bm25 import query_bm25
from index.vector_store import get_collection, query_embed
from rag.state import RagState
from retrieval.hybrid import combine_scores
from tuning import BM25_K, EMBED_K, TOP_K


def _chunk_from_meta(cid: str, doc: str, meta: dict) -> Chunk:
    section_path = tuple(p for p in (meta.get("section_path") or "").split(" > ") if p)
    image_refs = tuple(s for s in (meta.get("image_refs") or "").split(",") if s)
    return Chunk(
        chunk_id=cid,
        text=doc,
        source=meta.get("source") or "",
        doc_set=meta.get("doc_set") or "guide",
        title=meta.get("title") or "",
        section_id=meta.get("section_id") or "",
        doc_title=meta.get("doc_title", "") or "",
        seq=int(meta.get("seq", 0) or 0),
        section_path=section_path,
        image_refs=image_refs,
        notion_url=meta.get("notion_url") or "",
        manual=meta.get("manual") or "LMS",
    )


def hybrid_search(
    state: RagState, query: str, *, k: int = TOP_K, manual: str | None = None
) -> Retrieval:
    # manual 지정 시 BM25·임베딩 양쪽을 해당 매뉴얼로 하드 스코핑(LMS↔CMS 격리).
    bm = dict(query_bm25(state.bm25, query, k=BM25_K, manual=manual))
    emb = dict(query_embed(state.chroma, state.embedder, query, k=EMBED_K, manual=manual))
    max_embed_sim = max(emb.values(), default=0.0)
    merged = combine_scores(bm, emb, k=k)
    if not merged:
        return Retrieval(items=(), top_score=0.0, max_embed_sim=max_embed_sim)

    coll = get_collection(state.chroma)
    ids = [cid for cid, _ in merged]
    res = coll.get(ids=ids, include=["documents", "metadatas"])
    meta_by_id = {i: (d, m) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])}

    items: list[ScoredChunk] = []
    for cid, score in merged:
        if cid not in meta_by_id:
            continue
        doc, meta = meta_by_id[cid]
        items.append(ScoredChunk(chunk=_chunk_from_meta(cid, doc, meta), score=score))
    return Retrieval(items=tuple(items), top_score=merged[0][1], max_embed_sim=max_embed_sim)
