from __future__ import annotations
import pickle
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from retrieval.types import Chunk


_TOKEN_RE = re.compile(r"[\w가-힣]+", flags=re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class BM25Pack:
    bm25: BM25Okapi
    chunk_ids: list[str]


def build_bm25(chunks: list[Chunk]) -> BM25Pack:
    docs = [_tokenize(f"{c.title}\n{' '.join(c.section_path)}\n{c.text}") for c in chunks]
    bm25 = BM25Okapi(docs)
    return BM25Pack(bm25=bm25, chunk_ids=[c.chunk_id for c in chunks])


def save_bm25(pack: BM25Pack, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(pack, f)


def load_bm25(path: Path) -> BM25Pack:
    with open(path, "rb") as f:
        return pickle.load(f)


def query_bm25(pack: BM25Pack, query: str, k: int = 20) -> list[tuple[str, float]]:
    q = _tokenize(query)
    scores = pack.bm25.get_scores(q)
    idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [(pack.chunk_ids[i], float(scores[i])) for i in idx]
