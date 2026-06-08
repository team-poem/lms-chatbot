from __future__ import annotations
import pickle
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from app_types import Chunk


_TOKEN_RE = re.compile(r"[\w가-힣]+", flags=re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class BM25Pack:
    bm25: BM25Okapi
    chunk_ids: list[str]
    # chunk_ids 와 평행한 매뉴얼 스코프 키. manual 필터에 사용(옛 pkl 엔 없어
    # query_bm25 가 getattr 로 안전 처리). 재인덱싱 시 채워진다.
    manuals: list[str] | None = None


# 하위호환 alias: 옛 인덱스 pkl 은 클래스 경로가 index.bm25_index.BM25Pack 로 박혀 있음
# (모듈이 index/bm25_index.py → index/bm25.py 로 이름만 바뀌고 클래스는 동일).
# 옛 경로를 현재 모듈로 매핑해, 기존 운영 pkl(data/bm25.pkl)을 재인덱싱 없이 그대로 역직렬화.
# load_bm25 가 이 모듈에 있으므로 어떤 load 호출보다 먼저 등록됨이 보장된다.
import sys as _sys

_sys.modules.setdefault("index.bm25_index", _sys.modules[__name__])


def build_bm25(chunks: list[Chunk]) -> BM25Pack:
    docs = [_tokenize(f"{c.title}\n{' '.join(c.section_path)}\n{c.text}") for c in chunks]
    bm25 = BM25Okapi(docs)
    return BM25Pack(
        bm25=bm25,
        chunk_ids=[c.chunk_id for c in chunks],
        manuals=[c.manual for c in chunks],
    )


def save_bm25(pack: BM25Pack, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(pack, f)


def load_bm25(path: Path) -> BM25Pack:
    with open(path, "rb") as f:
        return pickle.load(f)


def query_bm25(
    pack: BM25Pack, query: str, k: int = 20, *, manual: str | None = None
) -> list[tuple[str, float]]:
    q = _tokenize(query)
    scores = pack.bm25.get_scores(q)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    # manual 지정 시 해당 매뉴얼 청크만(top-k 이전에 필터해 다른 매뉴얼이 자리를
    # 차지하지 않게). 옛 pkl(manuals 없음)은 필터 생략.
    manuals = getattr(pack, "manuals", None)
    if manual and manuals:
        order = [i for i in order if manuals[i] == manual]
    idx = order[:k]
    return [(pack.chunk_ids[i], float(scores[i])) for i in idx]
