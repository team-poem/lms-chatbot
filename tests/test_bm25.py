from pathlib import Path
from index.bm25 import build_bm25, save_bm25, load_bm25, query_bm25
from app_types import Chunk


def _chunk(cid: str, text: str, title: str = "T") -> Chunk:
    return Chunk(chunk_id=cid, text=text, source=f"s/{cid}.md",
                 doc_set="guide", title=title)


def test_build_and_query_returns_scores():
    chunks = [
        _chunk("c1", "퀴즈 출제 방법은 다음과 같습니다", title="퀴즈 개요"),
        _chunk("c2", "출결 현황 조회 방법", title="출결현황"),
        _chunk("c3", "토론 그룹 만들기", title="토론"),
    ]
    bm = build_bm25(chunks)
    hits = query_bm25(bm, "퀴즈 출제", k=2)
    assert len(hits) == 2
    assert hits[0][0] == "c1"
    assert hits[0][1] > hits[1][1]


def test_save_and_load_roundtrip(tmp_path: Path):
    chunks = [_chunk("c1", "퀴즈", title="퀴즈")]
    bm = build_bm25(chunks)
    p = tmp_path / "bm25.pkl"
    save_bm25(bm, p)
    bm2 = load_bm25(p)
    hits = query_bm25(bm2, "퀴즈", k=1)
    assert hits[0][0] == "c1"
