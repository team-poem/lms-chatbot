from __future__ import annotations


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {k: 0.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def combine_scores(
    bm25_scores: dict[str, float],
    embed_scores: dict[str, float],
    *,
    w_bm25: float = 0.4,
    w_embed: float = 0.6,
    k: int = 5,
) -> list[tuple[str, float]]:
    bm_n = _normalize(bm25_scores)
    em_n = _normalize(embed_scores)
    ids = set(bm_n) | set(em_n)
    combined: list[tuple[str, float]] = []
    for cid in ids:
        score = w_bm25 * bm_n.get(cid, 0.0) + w_embed * em_n.get(cid, 0.0)
        combined.append((cid, score))
    combined.sort(key=lambda x: x[1], reverse=True)
    return combined[:k]
