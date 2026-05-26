"""검색 단독 동작 확인용 CLI. Ollama 없이도 인덱스 품질 검증 가능.

사용: .venv/bin/python -m retrieval.cli "퀴즈 출제하는 방법"
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from index.embed import Embedder, get_chroma, query_embed
from index.bm25_index import load_bm25, query_bm25
from retrieval.hybrid import combine_scores


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+", help="검색할 질의")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--chroma", default=os.environ.get("CHROMA_DIR", "./data/chroma"))
    parser.add_argument("--bm25", default=os.environ.get("BM25_PATH", "./data/bm25.pkl"))
    args = parser.parse_args(argv)

    query = " ".join(args.query)
    print(f"질의: {query}\n")

    embedder = Embedder()
    chroma = get_chroma(Path(args.chroma))
    bm25 = load_bm25(Path(args.bm25))

    bm = dict(query_bm25(bm25, query, k=20))
    emb = dict(query_embed(chroma, embedder, query, k=20))
    merged = combine_scores(bm, emb, k=args.k)

    coll = chroma.get_or_create_collection("lms_chunks")
    if not merged:
        print("검색 결과 없음")
        return 1
    ids = [cid for cid, _ in merged]
    fetched = coll.get(ids=ids, include=["documents", "metadatas"])
    by_id = {i: (d, m) for i, d, m in zip(fetched["ids"], fetched["documents"], fetched["metadatas"])}

    for rank, (cid, score) in enumerate(merged, 1):
        doc, meta = by_id[cid]
        title = meta.get("title", "")
        snippet = doc[:160].replace("\n", " ")
        print(f"[{rank}] score={score:.3f}  title={title}")
        print(f"    {snippet}...")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
