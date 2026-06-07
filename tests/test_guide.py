from app_types import Chunk
from generation.guide import build_guide


def _c(doc_title, seq, text, imgs=(), notion=""):
    return Chunk(chunk_id=f"{doc_title}{seq}", text=text, source="s", doc_set="guide",
                 title=doc_title, doc_title=doc_title, seq=seq,
                 image_refs=tuple(imgs), notion_url=notion)


def test_build_guide_orders_by_seq_and_collects():
    chunks = [
        _c("P", 2, "둘째", ["b.png"]),
        _c("P", 0, "첫째", ["a.png"], notion="http://n"),
        _c("Q", 0, "다른문서", ["x.png"]),
    ]
    g = build_guide(chunks, "P")
    assert g["title"] == "P"
    assert g["text"].index("첫째") < g["text"].index("둘째")
    assert g["images"] == ["a.png", "b.png"]
    assert g["source_url"] == "http://n"


def test_build_guide_returns_none_when_missing():
    assert build_guide([], "P") is None
    assert build_guide([_c("Q", 0, "x")], "P") is None
