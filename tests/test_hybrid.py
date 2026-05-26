from retrieval.hybrid import combine_scores


def test_combine_basic_weighted_sum():
    bm = {"a": 1.0, "b": 0.0}
    emb = {"a": 0.0, "b": 1.0}
    out = combine_scores(bm, emb, w_bm25=0.4, w_embed=0.6, k=2)
    assert out[0][0] == "b"
    assert abs(out[0][1] - 0.6) < 1e-9
    assert out[1][0] == "a"
    assert abs(out[1][1] - 0.4) < 1e-9


def test_combine_normalizes_to_0_1():
    bm = {"a": 12.5, "b": 5.0, "c": 0.0}
    emb = {"a": 0.9, "b": 0.5, "c": 0.1}
    out = combine_scores(bm, emb, w_bm25=0.5, w_embed=0.5, k=3)
    for _, score in out:
        assert 0.0 <= score <= 1.0


def test_combine_handles_missing_keys():
    bm = {"a": 1.0}
    emb = {"b": 1.0}
    out = combine_scores(bm, emb, w_bm25=0.4, w_embed=0.6, k=2)
    ids = [i for i, _ in out]
    assert set(ids) == {"a", "b"}
