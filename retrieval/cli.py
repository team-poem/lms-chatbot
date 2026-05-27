"""검색 단독 동작 확인용 CLI. Ollama 없이도 인덱스 품질 검증 가능.

사용: .venv/bin/python -m retrieval.cli "퀴즈 출제하는 방법"
"""
from __future__ import annotations
import argparse

from config import load_config
from rag.state import load_rag_state
from retrieval.search import hybrid_search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+", help="검색할 질의")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args(argv)

    query = " ".join(args.query)
    print(f"질의: {query}\n")

    config = load_config()
    state = load_rag_state(config)
    retrieval = hybrid_search(state, query, k=args.k)

    if not retrieval.items:
        print("검색 결과 없음")
        return 1

    for rank, it in enumerate(retrieval.items, 1):
        snippet = it.chunk.text[:160].replace("\n", " ")
        print(f"[{rank}] score={it.score:.3f}  title={it.chunk.title}")
        print(f"    {snippet}...")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
