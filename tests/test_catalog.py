from generation.catalog import CATALOG, catalog_as_dict


def test_catalog_has_categories_with_items():
    assert len(CATALOG) == 10
    for c in CATALOG:
        assert c.name
        assert len(c.items) >= 1
        for it in c.items:
            assert it.label.strip() and it.doc.strip()


def test_catalog_as_dict_shape():
    d = catalog_as_dict()
    assert list(d.keys()) == ["categories"]
    first_item = d["categories"][0]["items"][0]
    assert set(first_item.keys()) == {"label", "doc"}


def test_catalog_docs_exist_in_manual():
    # 모든 doc 이 실제 매뉴얼 페이지 제목(doc_title)에 존재하는지(오타 가드).
    import pathlib
    from ingest.chunk import _derive_title
    raw = pathlib.Path("data/raw")
    titles = {
        _derive_title(p)
        for p in raw.rglob("*.md")
        if "LMS 매뉴얼" in str(p)
    }
    missing = [it.doc for c in CATALOG for it in c.items if it.doc not in titles]
    assert not missing, f"매뉴얼에 없는 doc: {missing}"


import asyncio
from backend import catalog as catalog_route


def test_catalog_endpoint_returns_categories():
    result = asyncio.run(catalog_route())
    assert "categories" in result
    assert result["categories"]
    assert result["categories"][0]["name"]
