from __future__ import annotations

from app_types import Chunk, Retrieval, ScoredChunk
from index.bm25 import query_bm25
from index.vector_store import get_collection, query_embed
from rag.state import RagState
from retrieval.hybrid import combine_scores


TOP_K = 5
EMBED_K = 20
BM25_K = 20


def hybrid_search(state: RagState, query: str, *, k: int = TOP_K) -> Retrieval:
    bm = dict(query_bm25(state.bm25, query, k=BM25_K))
    emb = dict(query_embed(state.chroma, state.embedder, query, k=EMBED_K))
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
        section_path = tuple(p for p in (meta.get("section_path") or "").split(" > ") if p)
        image_refs = tuple(s for s in (meta.get("image_refs") or "").split(",") if s)
        chunk = Chunk(
            chunk_id=cid,
            text=doc,
            source=meta.get("source", ""),
            doc_set=meta.get("doc_set", "guide"),
            title=meta.get("title", ""),
            section_path=section_path,
            image_refs=image_refs,
            notion_url=meta.get("notion_url", "") or "",
        )
        items.append(ScoredChunk(chunk=chunk, score=score))
    return Retrieval(items=tuple(items), top_score=merged[0][1], max_embed_sim=max_embed_sim)
