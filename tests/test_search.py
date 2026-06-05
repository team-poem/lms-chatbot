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
