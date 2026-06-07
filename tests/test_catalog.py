from generation.catalog import CATALOG, catalog_as_dict


def test_catalog_has_categories_with_items():
    assert len(CATALOG) == 10
    for c in CATALOG:
        assert c.name
        assert len(c.items) >= 1
        assert all(isinstance(it, str) and it.strip() for it in c.items)


def test_catalog_as_dict_shape():
    d = catalog_as_dict()
    assert list(d.keys()) == ["categories"]
    assert len(d["categories"]) == len(CATALOG)
    first = d["categories"][0]
    assert set(first.keys()) == {"emoji", "name", "items"}
    assert isinstance(first["items"], list) and first["items"]
