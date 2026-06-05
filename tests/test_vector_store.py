from app_types import Chunk
from index.vector_store import _chunk_meta


def test_chunk_meta_includes_section_id():
    c = Chunk(
        chunk_id="c1", text="t", source="s", doc_set="guide", title="T",
        section_id="sec1", image_refs=("a.png",),
    )
    meta = _chunk_meta(c)
    assert meta["section_id"] == "sec1"
    assert meta["image_refs"] == "a.png"
    assert meta["title"] == "T"
