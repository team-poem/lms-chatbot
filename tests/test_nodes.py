from app_types import Chunk, NodeLink, NodeRef, ScoredChunk, Source
from generation.catalog import Category, Manual
from generation.nodes import (Node, Registry, _cat_id, _node_id, _norm,
                              apply_overlay, build_nodes, card_of,
                              dockey_index, entry_payload, fill_auto_related,
                              find_related, group_docs, load_overlay,
                              overlay_meta, FAQ_CATEGORY)


# ── Task 1: ID helpers ───────────────────────────────────────────────────────

def test_norm_strips_emoji_and_collapses_space():
    assert _norm("  로그인   방법 ") == "로그인 방법"


def test_node_id_deterministic_and_norm_invariant():
    a = _node_id("LMS", "guide", "로그인 방법")
    b = _node_id("LMS", "guide", "로그인  방법 ")  # 공백만 다름
    assert a == b
    assert a.startswith("lms-guide-") and len(a) == len("lms-guide-") + 8


def test_cat_id_prefix():
    assert _cat_id("LMS", "로그인·기본 화면").startswith("lms-cat-")


# ── Task 2: group_docs ────────────────────────────────────────────────────────

def _chunk(**kw):
    base = dict(chunk_id="c", text="t", source="s", doc_set="guide",
               title="t", doc_title="문서", manual="LMS", seq=0,
               image_refs=(), notion_url="")
    base.update(kw)
    return Chunk(**base)


def test_group_docs_concats_by_seq_and_dedups_images():
    chunks = [
        _chunk(chunk_id="b", seq=1, text="둘째", image_refs=("/a/2.png",)),
        _chunk(chunk_id="a", seq=0, text="첫째", image_refs=("/a/1.png", "/a/2.png"),
               notion_url="https://n/1"),
    ]
    groups = group_docs(chunks)
    g = groups[("LMS", "문서")]
    assert g["text"] == "첫째\n\n둘째"            # seq 순 결합
    assert g["images"] == ("/a/1.png", "/a/2.png")  # 순서 보존·중복 제거
    assert g["notion_url"] == "https://n/1"
    assert g["doc_set"] == "guide"


# ── Task 3: build_nodes ───────────────────────────────────────────────────────

_CAT = (
    Manual(name="LMS", title="LMS 매뉴얼", categories=(
        Category(name="로그인·기본 화면", docs=("로그인 방법", "대시보드")),
    )),
)


def _guide(title, text, **kw):
    return _chunk(doc_set="guide", doc_title=title, title=title, text=text, **kw)


def _faq(title, text, **kw):
    return _chunk(doc_set="faq", doc_title=title, title=title, text=text, **kw)


def test_build_nodes_guide_from_catalog():
    chunks = [_guide("로그인 방법", "# 로그인 방법\n\n로그인은 이렇게 합니다.",
                     notion_url="https://n/1", image_refs=("/a/login.png",))]
    nodes = build_nodes(chunks, _CAT)
    nid = _node_id("LMS", "guide", "로그인 방법")
    n = nodes[nid]
    assert n.doc_set == "guide"
    assert n.category == "로그인·기본 화면"
    assert "로그인은 이렇게 합니다." in n.answer        # 원문 직출력
    assert n.images == ("/a/login.png",)
    assert n.sources == (Source(title="로그인 방법", url="https://n/1"),)
    assert n.parent == NodeRef(id=_cat_id("LMS", "로그인·기본 화면"), label="로그인·기본 화면")


def test_build_nodes_skips_doc_missing_in_index():
    nodes = build_nodes([_guide("로그인 방법", "본문")], _CAT)
    assert _node_id("LMS", "guide", "대시보드") not in nodes   # 인덱스에 없음 → 건너뜀


def test_build_nodes_faq_and_skips_empty():
    chunks = [
        _faq("비밀번호 재설정", "# 비밀번호?\n\n **답변** : 초기화는 이렇게 합니다."),
        _faq("빈껍데기", "# 제목만"),                 # faq_answer 빈 → 제외
    ]
    nodes = build_nodes(chunks, _CAT)
    fid = _node_id("LMS", "faq", "비밀번호 재설정")
    assert nodes[fid].answer == "초기화는 이렇게 합니다."
    assert nodes[fid].category == FAQ_CATEGORY
    assert _node_id("LMS", "faq", "빈껍데기") not in nodes


# ── Task 4: fill_auto_related ─────────────────────────────────────────────────

def test_fill_auto_related_links_siblings():
    chunks = [_guide("로그인 방법", "a"), _guide("대시보드", "b")]
    cat = (Manual(name="LMS", title="LMS 매뉴얼", categories=(
        Category(name="로그인·기본 화면", docs=("로그인 방법", "대시보드")),)),)
    nodes = fill_auto_related(build_nodes(chunks, cat))
    a = nodes[_node_id("LMS", "guide", "로그인 방법")]
    assert NodeRef(id=_node_id("LMS", "guide", "대시보드"), label="대시보드") in a.related
    assert all(r.id != a.id for r in a.related)   # 자기 자신 제외


# ── Task 5: overlay ───────────────────────────────────────────────────────────

def test_apply_overlay_overrides_and_ignores_unknown():
    chunks = [_guide("로그인 방법", "원래 답변")]
    nodes = build_nodes(chunks, _CAT)
    nid = _node_id("LMS", "guide", "로그인 방법")
    overlay = {
        "_meta": {"welcome": "환영", "quick_links": [{"label": "e-Class", "url": "https://e"}]},
        nid: {"answer": "고친 답변",
              "links": [{"label": "바로가기", "url": "https://x"}],
              "related": [{"id": "other", "label": "다른 질문"}]},
        "없는-id": {"answer": "무시됨"},
    }
    merged = apply_overlay(nodes, overlay)
    assert merged[nid].answer == "고친 답변"
    assert merged[nid].links == (NodeLink(label="바로가기", url="https://x"),)
    assert merged[nid].related == (NodeRef(id="other", label="다른 질문"),)
    assert "없는-id" not in merged
    assert overlay_meta(overlay)["welcome"] == "환영"


def test_load_overlay_missing_returns_empty(tmp_path):
    assert load_overlay(tmp_path / "nope.json") == {}


# ── Task 6: card_of · find_related ───────────────────────────────────────────

def test_card_of_maps_label_to_question():
    n = build_nodes([_guide("로그인 방법", "본문")], _CAT)[_node_id("LMS", "guide", "로그인 방법")]
    card = card_of(n)
    assert card.question == "로그인 방법"
    assert card.answer == n.answer
    assert card.category == n.category


def test_find_related_maps_dedups_and_limits():
    nodes = build_nodes([_guide("로그인 방법", "a"), _faq("비밀번호 재설정",
                        "# q\n\n **답변** : b.")], _CAT)
    items = (
        ScoredChunk(chunk=_guide("로그인 방법", "a"), score=0.9),
        ScoredChunk(chunk=_guide("로그인 방법", "a"), score=0.8),   # 중복 노드
        ScoredChunk(chunk=_faq("비밀번호 재설정", "x"), score=0.7),
        ScoredChunk(chunk=_guide("없는문서", "z"), score=0.6),       # 노드 없음
    )
    refs = find_related(items, nodes, limit=5)
    ids = [r.id for r in refs]
    assert ids == [_node_id("LMS", "guide", "로그인 방법"),
                   _node_id("LMS", "faq", "비밀번호 재설정")]


# ── Task 7: entry_payload ─────────────────────────────────────────────────────

def test_entry_payload_structure():
    chunks = [_guide("로그인 방법", "a"),
              _faq("비밀번호 재설정", "# q\n\n **답변** : b.")]
    nodes = fill_auto_related(build_nodes(chunks, _CAT))
    reg = Registry(by_id=nodes, meta={"welcome": "환영", "quick_links": []})
    payload = entry_payload(reg, _CAT, n_recommended=3)

    assert payload["welcome"] == "환영"
    cat = next(c for c in payload["categories"] if c["label"] == "로그인·기본 화면")
    assert {"id": _node_id("LMS", "guide", "로그인 방법"), "label": "로그인 방법"} in cat["nodes"]
    assert any(c["label"] == FAQ_CATEGORY for c in payload["categories"])
    rec_ids = {r["id"] for r in payload["recommended"]}
    assert _node_id("LMS", "faq", "비밀번호 재설정") in rec_ids   # 추천=FAQ 노드
    assert payload["quick_links"] == []
