from retrieval.search import _chunk_from_meta


def test_chunk_from_meta_restores_section_id():
    meta = {
        "source": "s", "doc_set": "guide", "title": "T",
        "section_id": "sec1", "section_path": "A > B",
        "image_refs": "a.png,b.png", "notion_url": "",
    }
    c = _chunk_from_meta("c1", "doc text", meta)
    assert c.section_id == "sec1"
    assert c.image_refs == ("a.png", "b.png")
    assert c.section_path == ("A", "B")
    assert c.text == "doc text"


def test_chunk_from_meta_defaults_section_id_empty():
    c = _chunk_from_meta("c1", "d", {})
    assert c.section_id == ""


from app_types import Chunk
from index.vector_store import _chunk_meta


def test_meta_roundtrip_preserves_section_fields():
    c = Chunk(
        chunk_id="c1", text="본문", source="s", doc_set="faq", title="T",
        section_id="sec9", section_path=("A", "B"), image_refs=("x.png", "y.png"),
    )
    r = _chunk_from_meta("c1", c.text, _chunk_meta(c))
    assert r.section_id == c.section_id
    assert r.image_refs == c.image_refs
    assert r.section_path == c.section_path
    assert r.doc_set == c.doc_set
    assert r.title == c.title


def test_chunk_from_meta_restores_doc_title_and_seq():
    c = _chunk_from_meta("c1", "doc", {"doc_title": "페이지", "seq": 5})
    assert c.doc_title == "페이지"
    assert c.seq == 5


def test_chunk_from_meta_seq_defaults_zero():
    c = _chunk_from_meta("c1", "d", {})
    assert c.seq == 0
