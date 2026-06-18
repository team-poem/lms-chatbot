# 선택형 상담 플로우 (Phase 0 + Phase 1) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LMS 챗봇에 "노드 클릭 → 확정 답변 카드" 선택형 상담 경로를 기존 RAG/LLM을 건드리지 않고 추가한다(Phase 0: 노드 모델·레지스트리, Phase 1: 공개 API + `?mode=consult` UI).

**Architecture:** 인덱스(chroma) + 카탈로그 TOC + FAQ 답변 문서에서 노드를 자동 도출하고 `data/nodes.overlay.json`으로 큐레이션을 덧입혀 서버 기동 시 1회 레지스트리를 만든다. `/answer/{id}`는 재검색·게이트·LLM 없이 확정 카드를 반환한다(FAQ=`faq_answer` 원문, 가이드=정제 본문 직출력). 자유 입력은 `/search`(노드 매칭, 생성 없음)로 추천 칩만 제시한다. 기존 `/chat` RAG 경로는 그대로 둔다.

**Tech Stack:** Python 3 / FastAPI / chromadb / sentence-transformers(BGE-M3) / 순수 ESM JS(빌드 없음) / pytest.

## Global Constraints

- 답변은 인덱싱된 가이드 근거로만 한다. 노드 경로엔 LLM을 절대 호출하지 않는다(FAQ=원문, 가이드=원문 직출력). (`AGENT.md` 신뢰 경계)
- 기존 `/faq`·`/catalog`·`/chat`·`generation/stream.py` 등 레거시 경로는 **수정하지 않는다**(Phase 1 비파괴).
- Phase 1 신규 엔드포인트는 **공개 읽기 전용**(세션 불필요). 선택 로깅·`turns.node_id`는 Phase 2. 데이터 수집 없음 → 동의 불필요.
- 응답 텍스트 규칙(존대 격식체, 마크업·이모지 금지)은 원본 데이터에 이미 적용됨 — 노드 경로는 원문을 그대로 전달한다.
- 모든 수치·경로는 하드코딩하지 말고 기존 `config.py`/`tuning.py` 패턴을 따른다.
- 테스트는 순수 함수 위주(`tests/test_*.py`, `pytest`). 엔드포인트는 얇은 wrapper라 스모크로 검증(앱에 `test_backend.py` 없음).
- 커밋 메시지는 레포 관례(Conventional, 한글 본문): `feat(nodes): …`, `feat(api): …`, `feat(ui): …`, `test(nodes): …`.
- **커밋 시 각 태스크가 만진 파일만 명시적으로 스테이징한다 — `git add -A`/`git add .` 금지.** 작업트리에 이 작업과 무관한 미커밋 변경(`AGENT.md`, `package-lock.json`, `package.json`)이 있으므로 절대 함께 커밋하지 않는다.

---

## File Structure

**신규**
- `generation/nodes.py` — 노드 레지스트리 단일 책임: 타입(`Node`/`Registry`), 도출(`group_docs`/`build_nodes`/`fill_auto_related`), 오버레이(`load_overlay`/`apply_overlay`/`overlay_meta`), 조회(`card_of`/`find_related`/`dockey_index`), 진입(`entry_payload`), chroma 셸(`enumerate_chunks`/`build_registry`).
- `data/nodes.overlay.json` — 큐레이션 오버레이(초기 시드: `_meta`만).
- `tests/test_nodes.py` — 위 순수 함수 테스트.

**수정**
- `app_types.py` — `NodeLink`/`NodeRef`/`AnswerCard` 추가(횡단 타입).
- `config.py` — `nodes_overlay_path` 추가.
- `backend.py` — startup 레지스트리 캐시 + `GET /entry`·`GET /answer/{id}`·`GET /search`.
- `static/js/api.js` — `fetchEntry`/`fetchAnswer`/`searchNodes`.
- `static/js/ui.js` — `renderEntryMenu`/`renderAnswerCard`/후보 칩.
- `static/js/main.js` — consult 컨트롤러(`?mode=consult`), 뒤로 스택, 자유입력 검색.
- `static/index.html` — placeholder/컨테이너 소폭.
- `static/css/app.css` — 카드·관련·뒤로·바로가기 스타일.

**불변(참조만)**: `generation/faq.py:faq_answer`, `generation/catalog.py:build_catalog`+`Manual`/`Category`, `retrieval/search.py:hybrid_search`/`_chunk_from_meta`, `index/vector_store.py:get_collection`, `ingest/preprocess.py:strip_emoji`, `generation/persona.py:qna_fallback_msg`.

---

## Phase 0 — 노드 모델·레지스트리 (순수 로직, 동작 무변경)

### Task 1: 횡단 타입 + ID 헬퍼

**Files:**
- Modify: `app_types.py` (끝에 추가)
- Create: `generation/nodes.py`
- Test: `tests/test_nodes.py`

**Interfaces:**
- Produces: `NodeLink(label,url)`, `NodeRef(id,label)`, `AnswerCard(...)` (app_types); `Node(...)`, `_norm(str)->str`, `_node_id(manual,doc_set,doc_title)->str`, `_cat_id(manual,category)->str` (nodes).

- [ ] **Step 1: app_types에 타입 추가**

`app_types.py` 끝에 추가:

```python
@dataclass(frozen=True)
class NodeLink:
    label: str
    url: str


@dataclass(frozen=True)
class NodeRef:
    id: str
    label: str


@dataclass(frozen=True)
class AnswerCard:
    """선택형 확정 답변 카드 — /answer/{id} 응답. LLM 미경유."""
    id: str
    category: str
    question: str
    answer: str
    images: tuple[str, ...] = ()
    links: tuple[NodeLink, ...] = ()
    related: tuple[NodeRef, ...] = ()
    parent: NodeRef | None = None
    sources: tuple[Source, ...] = ()
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_nodes.py`:

```python
from app_types import Chunk, ScoredChunk, Source
from generation.catalog import Category, Manual
from generation.nodes import (Node, Registry, _cat_id, _node_id, _norm,
                              apply_overlay, build_nodes, card_of,
                              dockey_index, entry_payload, fill_auto_related,
                              find_related, group_docs, load_overlay,
                              overlay_meta)


def test_norm_strips_emoji_and_collapses_space():
    assert _norm("  로그인   방법 ") == "로그인 방법"


def test_node_id_deterministic_and_norm_invariant():
    a = _node_id("LMS", "guide", "로그인 방법")
    b = _node_id("LMS", "guide", "로그인  방법 ")  # 공백만 다름
    assert a == b
    assert a.startswith("lms-guide-") and len(a) == len("lms-guide-") + 8


def test_cat_id_prefix():
    assert _cat_id("LMS", "로그인·기본 화면").startswith("lms-cat-")
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_nodes.py -q`
Expected: FAIL — `ImportError: cannot import name ... 'generation.nodes'`

- [ ] **Step 4: generation/nodes.py 최소 구현**

```python
"""선택형 상담 노드 레지스트리. 인덱스(chroma)+카탈로그 TOC+FAQ 답변 문서에서
노드를 자동 도출하고 data/nodes.overlay.json 큐레이션을 덧입힌다. LLM 미경유 —
FAQ는 faq_answer 원문, 가이드는 정제 본문 직출력."""
from __future__ import annotations
import hashlib
import json
import random
import re
from dataclasses import dataclass, replace
from pathlib import Path

from app_types import Chunk, NodeLink, NodeRef, ScoredChunk, Source
from generation.catalog import Manual, build_catalog
from generation.faq import faq_answer
from index.vector_store import get_collection
from ingest.preprocess import strip_emoji
from rag.state import RagState
from retrieval.search import _chunk_from_meta, hybrid_search

FAQ_CATEGORY = "자주 묻는 질문"
FAQ_ROOT_ID = "lms-faq-root"
_DEFAULT_WELCOME = (
    "동서대학교 LMS 교수자 가이드 상담입니다. 아래에서 주제를 선택하시면 "
    "확정된 안내를 보여드립니다."
)


@dataclass(frozen=True)
class Node:
    id: str
    category: str
    category_id: str
    manual: str
    doc_set: str
    label: str
    doc_title: str
    answer: str
    images: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    parent: NodeRef | None = None
    related: tuple[NodeRef, ...] = ()
    links: tuple[NodeLink, ...] = ()


@dataclass(frozen=True)
class Registry:
    by_id: dict[str, Node]
    meta: dict


def _norm(title: str) -> str:
    """조인·ID용 정규화: 이모지 제거 + 연속 공백 축약."""
    return re.sub(r"\s+", " ", strip_emoji(title or "")).strip()


def _node_id(manual: str, doc_set: str, doc_title: str) -> str:
    h = hashlib.sha1(_norm(doc_title).encode("utf-8")).hexdigest()[:8]
    return f"{manual.lower()}-{doc_set}-{h}"


def _cat_id(manual: str, category: str) -> str:
    h = hashlib.sha1(_norm(category).encode("utf-8")).hexdigest()[:8]
    return f"{manual.lower()}-cat-{h}"
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_nodes.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add app_types.py generation/nodes.py tests/test_nodes.py
git commit -m "feat(nodes): 노드 타입과 결정적 ID 헬퍼"
```

---

### Task 2: group_docs — 청크를 문서 단위로 결합

**Interfaces:**
- Consumes: `Chunk`, `_norm`
- Produces: `group_docs(chunks: list[Chunk]) -> dict[tuple[str,str], dict]` — 키 `(manual, _norm(doc_title))`, 값 `{doc_title, manual, doc_set, text, images, notion_url}`.

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_nodes.py`에 추가)

```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_nodes.py::test_group_docs_concats_by_seq_and_dedups_images -q` → FAIL (`group_docs` not defined)

- [ ] **Step 3: 구현** (`generation/nodes.py`에 추가)

```python
def group_docs(chunks: list[Chunk]) -> dict[tuple[str, str], dict]:
    """(manual, _norm(doc_title)) 로 청크를 묶어 seq 순으로 본문·이미지를 결합한다."""
    buckets: dict[tuple[str, str], list[Chunk]] = {}
    for c in chunks:
        if not c.doc_title:
            continue
        buckets.setdefault((c.manual, _norm(c.doc_title)), []).append(c)

    out: dict[tuple[str, str], dict] = {}
    for key, cs in buckets.items():
        cs = sorted(cs, key=lambda c: c.seq)
        images: list[str] = []
        for c in cs:
            for img in c.image_refs:
                if img and img not in images:
                    images.append(img)
        out[key] = {
            "doc_title": cs[0].doc_title,
            "manual": cs[0].manual,
            "doc_set": cs[0].doc_set,
            "text": "\n\n".join(c.text for c in cs).strip(),
            "images": tuple(images),
            "notion_url": next((c.notion_url for c in cs if c.notion_url), ""),
        }
    return out
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_nodes.py -q` → PASS

- [ ] **Step 5: 커밋**

```bash
git add generation/nodes.py tests/test_nodes.py
git commit -m "feat(nodes): group_docs — 청크 문서 단위 결합"
```

---

### Task 3: build_nodes — 가이드/FAQ 노드 도출

**Interfaces:**
- Consumes: `group_docs`, `_node_id`, `_cat_id`, `faq_answer`, `Manual`/`Category`, `Source`, `NodeRef`
- Produces: `build_nodes(chunks: list[Chunk], catalog: tuple[Manual,...]) -> dict[str, Node]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_nodes.py -k build_nodes -q` → FAIL

- [ ] **Step 3: 구현**

```python
def build_nodes(chunks: list[Chunk], catalog: tuple[Manual, ...]) -> dict[str, Node]:
    """카탈로그 트리로 가이드 노드를, doc_set=='faq' 문서로 FAQ 노드를 만든다.
    인덱스에 없는 카탈로그 항목·빈 FAQ 답변은 건너뛴다(graceful)."""
    docs = group_docs(chunks)
    nodes: dict[str, Node] = {}

    # 가이드: 카탈로그 순서·카테고리 기준
    for manual in catalog:
        for cat in manual.categories:
            cid = _cat_id(manual.name, cat.name)
            for doc_label in cat.docs:
                doc = docs.get((manual.name, _norm(doc_label)))
                if doc is None or doc["doc_set"] != "guide":
                    continue
                nid = _node_id(manual.name, "guide", doc["doc_title"])
                nodes[nid] = Node(
                    id=nid, category=cat.name, category_id=cid,
                    manual=manual.name, doc_set="guide",
                    label=doc["doc_title"], doc_title=doc["doc_title"],
                    answer=doc["text"], images=doc["images"],
                    sources=(Source(title=doc["doc_title"], url=doc["notion_url"]),),
                    parent=NodeRef(id=cid, label=cat.name),
                )

    # FAQ: 인덱싱된 doc_set=='faq' 문서 전부(빈 답변 제외)
    for (manual, _nt), doc in docs.items():
        if doc["doc_set"] != "faq":
            continue
        ans = faq_answer(doc["text"])
        if not ans:
            continue
        label = doc["doc_title"]
        if label.startswith("FAQ —"):           # 방어적(CSV는 미인덱싱)
            label = label[len("FAQ —"):].strip()
        nid = _node_id(manual, "faq", doc["doc_title"])
        nodes[nid] = Node(
            id=nid, category=FAQ_CATEGORY, category_id=FAQ_ROOT_ID,
            manual=manual, doc_set="faq",
            label=label, doc_title=doc["doc_title"],
            answer=ans, images=doc["images"], sources=(),
            parent=NodeRef(id=FAQ_ROOT_ID, label=FAQ_CATEGORY),
        )
    return nodes
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_nodes.py -q` → PASS

- [ ] **Step 5: 커밋**

```bash
git add generation/nodes.py tests/test_nodes.py
git commit -m "feat(nodes): build_nodes — 가이드/FAQ 노드 도출"
```

---

### Task 4: fill_auto_related — 같은 카테고리 형제 연결

**Interfaces:**
- Consumes: `Node`, `NodeRef`
- Produces: `fill_auto_related(nodes: dict[str,Node], *, limit: int = 6) -> dict[str,Node]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_fill_auto_related_links_siblings():
    chunks = [_guide("로그인 방법", "a"), _guide("대시보드", "b")]
    cat = (Manual(name="LMS", title="LMS 매뉴얼", categories=(
        Category(name="로그인·기본 화면", docs=("로그인 방법", "대시보드")),)),)
    nodes = fill_auto_related(build_nodes(chunks, cat))
    a = nodes[_node_id("LMS", "guide", "로그인 방법")]
    assert NodeRef(id=_node_id("LMS", "guide", "대시보드"), label="대시보드") in a.related
    assert all(r.id != a.id for r in a.related)   # 자기 자신 제외
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_nodes.py -k auto_related -q` → FAIL

- [ ] **Step 3: 구현**

```python
def fill_auto_related(nodes: dict[str, Node], *, limit: int = 6) -> dict[str, Node]:
    """같은 category_id 형제를 related 로 채운다(자기 제외, 카탈로그 순서 유지).
    오버레이가 이후 덮어쓸 수 있다."""
    by_cat: dict[str, list[Node]] = {}
    for n in nodes.values():
        by_cat.setdefault(n.category_id, []).append(n)
    out: dict[str, Node] = {}
    for nid, n in nodes.items():
        sibs = [s for s in by_cat.get(n.category_id, []) if s.id != n.id][:limit]
        out[nid] = replace(n, related=tuple(NodeRef(id=s.id, label=s.label) for s in sibs))
    return out
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_nodes.py -q` → PASS

- [ ] **Step 5: 커밋**

```bash
git add generation/nodes.py tests/test_nodes.py
git commit -m "feat(nodes): fill_auto_related — 형제 노드 연결"
```

---

### Task 5: 오버레이 로드·병합

**Interfaces:**
- Consumes: `Node`, `NodeLink`, `NodeRef`
- Produces: `load_overlay(path: Path) -> dict`, `apply_overlay(nodes, overlay) -> dict[str,Node]`, `overlay_meta(overlay) -> dict`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_nodes.py -k overlay -q` → FAIL

- [ ] **Step 3: 구현**

```python
def load_overlay(path: Path) -> dict:
    """오버레이 JSON 로드. 없으면 빈 dict(graceful)."""
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def overlay_meta(overlay: dict) -> dict:
    """첫 화면 메타(welcome/quick_links). 예약 키 '_meta'."""
    return overlay.get("_meta", {})


def apply_overlay(nodes: dict[str, Node], overlay: dict) -> dict[str, Node]:
    """id 기준으로 answer/links/related/parent 를 덮어쓴다. '_'로 시작하는 예약
    키와 알 수 없는 id 는 무시(graceful)."""
    out = dict(nodes)
    for nid, ov in overlay.items():
        if nid.startswith("_"):
            continue
        base = out.get(nid)
        if base is None:
            continue
        out[nid] = replace(
            base,
            answer=ov.get("answer", base.answer),
            links=(tuple(NodeLink(**x) for x in ov["links"])
                   if "links" in ov else base.links),
            related=(tuple(NodeRef(**x) for x in ov["related"])
                     if "related" in ov else base.related),
            parent=(NodeRef(**ov["parent"]) if ov.get("parent") else base.parent),
        )
    return out
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_nodes.py -q` → PASS

- [ ] **Step 5: 커밋**

```bash
git add generation/nodes.py tests/test_nodes.py
git commit -m "feat(nodes): 큐레이션 오버레이 로드·병합"
```

---

### Task 6: card_of · dockey_index · find_related

**Interfaces:**
- Consumes: `Node`, `AnswerCard`, `NodeRef`, `ScoredChunk`, `_norm`
- Produces: `card_of(node)->AnswerCard`, `dockey_index(nodes)->dict[(str,str),Node]`, `find_related(items, nodes, *, limit=5)->list[NodeRef]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_nodes.py -k "card_of or find_related" -q` → FAIL

- [ ] **Step 3: 구현**

```python
from app_types import AnswerCard  # 파일 상단 import 에 합류시켜도 됨


def card_of(node: Node) -> AnswerCard:
    """Node → /answer 응답 카드. label 이 곧 사용자가 누른 '질문'."""
    return AnswerCard(
        id=node.id, category=node.category, question=node.label,
        answer=node.answer, images=node.images, links=node.links,
        related=node.related, parent=node.parent, sources=node.sources,
    )


def dockey_index(nodes: dict[str, Node]) -> dict[tuple[str, str], Node]:
    return {(n.manual, _norm(n.doc_title)): n for n in nodes.values()}


def find_related(items, nodes: dict[str, Node], *, limit: int = 5) -> list[NodeRef]:
    """검색 결과(ScoredChunk) → 노드 후보. (manual, _norm(doc_title))로 매핑,
    중복 노드 제거, 점수 순 상위 limit. 노드 없는 청크는 건너뜀. LLM 미경유."""
    idx = dockey_index(nodes)
    seen: set[str] = set()
    out: list[NodeRef] = []
    for it in items:
        n = idx.get((it.chunk.manual, _norm(it.chunk.doc_title)))
        if n is None or n.id in seen:
            continue
        seen.add(n.id)
        out.append(NodeRef(id=n.id, label=n.label))
        if len(out) >= limit:
            break
    return out
```

> 참고: `from app_types import ... AnswerCard` 를 Task 1에서 추가한 상단 import 줄에 합치고, 위 본문의 중복 import 줄은 넣지 않는다.

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_nodes.py -q` → PASS

- [ ] **Step 5: 커밋**

```bash
git add generation/nodes.py tests/test_nodes.py
git commit -m "feat(nodes): card_of·find_related — 카드 변환·노드 매칭"
```

---

### Task 7: entry_payload — 첫 화면 페이로드

**Interfaces:**
- Consumes: `Registry`, `Node`, `Manual`, `_cat_id`, `_node_id`
- Produces: `entry_payload(registry: Registry, catalog: tuple[Manual,...], *, n_recommended: int = 6) -> dict`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_nodes.py -k entry_payload -q` → FAIL

- [ ] **Step 3: 구현**

```python
def entry_payload(registry: Registry, catalog: tuple[Manual, ...],
                  *, n_recommended: int = 6) -> dict:
    """첫 화면: welcome + 카테고리(가이드 카탈로그 순서 + FAQ 합성) + 추천 FAQ + 빠른 링크."""
    nodes = registry.by_id
    categories: list[dict] = []
    for manual in catalog:
        for cat in manual.categories:
            members = []
            for doc_label in cat.docs:
                n = nodes.get(_node_id(manual.name, "guide", doc_label))
                if n is not None:
                    members.append({"id": n.id, "label": n.label})
            if members:
                categories.append({"id": _cat_id(manual.name, cat.name),
                                   "label": cat.name, "manual": manual.name,
                                   "nodes": members})

    faq_nodes = [n for n in nodes.values() if n.doc_set == "faq"]
    if faq_nodes:
        categories.append({"id": FAQ_ROOT_ID, "label": FAQ_CATEGORY, "manual": "LMS",
                           "nodes": [{"id": n.id, "label": n.label} for n in faq_nodes]})

    sample = random.sample(faq_nodes, min(n_recommended, len(faq_nodes))) if faq_nodes else []
    return {
        "welcome": registry.meta.get("welcome", _DEFAULT_WELCOME),
        "categories": categories,
        "recommended": [{"id": n.id, "label": n.label} for n in sample],
        "quick_links": registry.meta.get("quick_links", []),
    }
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_nodes.py -q` → PASS

- [ ] **Step 5: 커밋**

```bash
git add generation/nodes.py tests/test_nodes.py
git commit -m "feat(nodes): entry_payload — 첫 화면 페이로드"
```

---

### Task 8: chroma 셸 — enumerate_chunks · build_registry

순수 로직을 인덱스에 연결하는 얇은 셸. 단위테스트 대신 실인덱스 스모크로 검증한다(다른 chroma 접촉 함수와 동일).

**Interfaces:**
- Consumes: `RagState`, `get_collection`, `_chunk_from_meta`, `build_catalog`, `build_nodes`/`fill_auto_related`/`load_overlay`/`apply_overlay`/`overlay_meta`
- Produces: `enumerate_chunks(state: RagState) -> list[Chunk]`, `build_registry(state: RagState, *, overlay_path: Path) -> Registry`

- [ ] **Step 1: 구현** (`generation/nodes.py`에 추가)

```python
def enumerate_chunks(state: RagState) -> list[Chunk]:
    """chroma 컬렉션의 모든 청크를 Chunk 로 복원한다(노드 도출용)."""
    coll = get_collection(state.chroma)
    res = coll.get(include=["documents", "metadatas"])
    return [
        _chunk_from_meta(cid, doc, meta)
        for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"])
    ]


def build_registry(state: RagState, *, overlay_path: Path) -> Registry:
    """기동 시 1회: 인덱스 전수 열거 → 노드 도출 → 자동 related → 오버레이 병합."""
    chunks = enumerate_chunks(state)
    catalog = build_catalog()
    nodes = fill_auto_related(build_nodes(chunks, catalog))
    overlay = load_overlay(overlay_path)
    nodes = apply_overlay(nodes, overlay)
    return Registry(by_id=nodes, meta=overlay_meta(overlay))
```

- [ ] **Step 2: 전체 단위테스트 회귀 확인**

Run: `python -m pytest tests/test_nodes.py -q`
Expected: PASS (전체)

- [ ] **Step 3: 실인덱스 스모크(노드 수·샘플 출력)**

Run:
```bash
python -c "
from config import load_config
from rag.state import load_rag_state
from generation.nodes import build_registry
cfg = load_config()
reg = build_registry(load_rag_state(cfg), overlay_path=cfg.nodes_overlay_path)
ns = list(reg.by_id.values())
print('총 노드', len(ns), '| 가이드', sum(n.doc_set=='guide' for n in ns), '| FAQ', sum(n.doc_set=='faq' for n in ns))
for n in ns[:3]:
    print(n.id, '|', n.doc_set, '|', n.label, '| 답변', len(n.answer), '자 | 관련', len(n.related))
"
```
Expected: 가이드·FAQ 노드 수가 0이 아니고, 각 노드에 답변 본문(>0자)과 related 가 채워진다. (실패 시: 카탈로그 label ↔ doc_title 정규화 조인 점검 — `_norm` 일치 여부.)

> 주의: 이 스모크는 BGE-M3 로드(약 10~20초)와 `data/chroma` 인덱스가 필요하다. `config.nodes_overlay_path` 는 Task 9에서 추가하므로 Task 9 이후 실행한다.

- [ ] **Step 4: 커밋**

```bash
git add generation/nodes.py
git commit -m "feat(nodes): enumerate_chunks·build_registry — 인덱스 연결"
```

---

## Phase 1 — 공개 API + 선택형 UI (비파괴 추가)

### Task 9: config 오버레이 경로 + 시드 파일

**Files:**
- Modify: `config.py:18-19` (AppConfig 필드), `config.py:35` 부근(load_config kwargs)
- Create: `data/nodes.overlay.json`

- [ ] **Step 1: AppConfig 필드 추가** — `config.py` 의 `raw_dir: Path` 다음 줄에 추가:

```python
    raw_dir: Path
    nodes_overlay_path: Path
    port: int
```

- [ ] **Step 2: load_config kwargs 추가** — `raw_dir=...` 다음에:

```python
        raw_dir=Path(os.environ.get("RAW_DIR", "./data/raw")),
        nodes_overlay_path=Path(
            os.environ.get("NODES_OVERLAY_PATH", "./data/nodes.overlay.json")
        ),
        port=int(os.environ.get("PORT", "8080")),
```

- [ ] **Step 3: 시드 오버레이 작성** — `data/nodes.overlay.json`:

```json
{
  "_meta": {
    "welcome": "동서대학교 LMS 교수자 가이드 상담입니다. 아래에서 주제를 선택하시면 확정된 안내를 보여드립니다.",
    "quick_links": [
      { "label": "e-Class 바로가기", "url": "https://eclass1.dongseo.ac.kr/" }
    ]
  }
}
```

- [ ] **Step 4: config 회귀 확인**

Run: `python -m pytest tests/test_config.py -q`
Expected: PASS (기존 필드 불변, 새 필드 기본값 적용)

- [ ] **Step 5: 커밋**

```bash
git add config.py data/nodes.overlay.json
git commit -m "feat(config): 노드 오버레이 경로 + 시드 파일"
```

---

### Task 10: 백엔드 엔드포인트 + 기동 캐시

**Files:**
- Modify: `backend.py` (import, lifespan, 라우트 3개)

- [ ] **Step 1: import 추가** (`backend.py` 상단 import 블록)

```python
from generation.catalog import build_catalog
from generation.nodes import build_registry, card_of, entry_payload, find_related
from retrieval.search import hybrid_search
```

- [ ] **Step 2: lifespan 에 레지스트리 캐시 추가** — `app.state.rag = ...` 다음 줄(`backend.py:39` 직후):

```python
    app.state.rag = await asyncio.to_thread(load_rag_state, config)
    print(f"[startup] RagState 준비 완료 ({time.time() - t0:.1f}s)", flush=True)
    app.state.nodes = await asyncio.to_thread(
        build_registry, app.state.rag, overlay_path=config.nodes_overlay_path
    )
    print(f"[startup] 노드 레지스트리 {len(app.state.nodes.by_id)}개", flush=True)
```

- [ ] **Step 3: 라우트 추가** (`/catalog` 정의 다음, `backend.py:95` 부근)

```python
@app.get("/entry")
def entry(request: Request):
    """첫 화면: 환영 + 카테고리 + 추천 FAQ + 빠른 링크. 공개(세션 불필요)."""
    reg = getattr(request.app.state, "nodes", None)
    if reg is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    return entry_payload(reg, build_catalog())


@app.get("/answer/{node_id}")
def answer(node_id: str, request: Request):
    """노드의 확정 답변 카드. 재검색·게이트·LLM 없음. 미존재 404."""
    reg = getattr(request.app.state, "nodes", None)
    if reg is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    node = reg.by_id.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="없는 항목입니다")
    return asdict(card_of(node))


@app.get("/search")
def search(request: Request, q: str = Query(..., min_length=1)):
    """자유 입력 → 가장 가까운 노드 추천(생성 없음). 공개."""
    reg = getattr(request.app.state, "nodes", None)
    state = getattr(request.app.state, "rag", None)
    if reg is None or state is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    refs = find_related(hybrid_search(state, q).items, reg.by_id)
    return {"candidates": [{"id": r.id, "label": r.label} for r in refs]}
```

- [ ] **Step 4: 기존 테스트 회귀 확인**

Run: `python -m pytest -q`
Expected: PASS (기존 전체 — 레거시 경로 무변경)

- [ ] **Step 5: 서버 기동 + 엔드포인트 스모크**

Run (별도 터미널에서 서버 기동: `bash run.sh` 또는 `uvicorn backend:app --port 8080`):
```bash
curl -s localhost:8080/entry | python -m json.tool | head -30
# categories 에서 임의 노드 id 하나 복사 후:
curl -s "localhost:8080/answer/<복사한-id>" | python -m json.tool
curl -s "localhost:8080/answer/없는-id" -o /dev/null -w "%{http_code}\n"   # 404
curl -s "localhost:8080/search?q=로그인" | python -m json.tool             # candidates 배열
```
Expected: `/entry` 가 categories·recommended 반환, `/answer/{id}` 가 question·answer·images·related 카드 반환, 없는 id 는 404, `/search` 가 후보 노드 배열 반환.

- [ ] **Step 6: 커밋**

```bash
git add backend.py
git commit -m "feat(api): 공개 /entry·/answer/{id}·/search + 기동 레지스트리 캐시"
```

---

### Task 11: 프런트 통신 계층 (api.js)

**Files:** Modify `static/js/api.js` (끝에 추가)

- [ ] **Step 1: 함수 추가**

```javascript
export async function fetchEntry() {
  try { const r = await fetch("/entry"); return r.ok ? await r.json() : null; }
  catch (e) { return null; }
}

export async function fetchAnswer(id) {
  try { const r = await fetch(`/answer/${encodeURIComponent(id)}`); return r.ok ? await r.json() : null; }
  catch (e) { return null; }
}

export async function searchNodes(q) {
  try {
    const r = await fetch(`/search?q=${encodeURIComponent(q)}`);
    return r.ok ? ((await r.json()).candidates || []) : [];
  } catch (e) { return []; }
}
```

- [ ] **Step 2: 문법 점검** — Run: `node --check static/js/api.js` → 출력 없음(성공)

- [ ] **Step 3: 커밋**

```bash
git add static/js/api.js
git commit -m "feat(ui): api.js — fetchEntry·fetchAnswer·searchNodes"
```

---

### Task 12: 프런트 렌더 계층 (ui.js)

**Files:** Modify `static/js/ui.js` (끝에 추가). 기존 `makeChip`·`renderImages`·`setAnswerText`·`renderSources`·`$`·`escapeHtml` 재사용.

**Interfaces:**
- Consumes(콜백 주입): `onSelect(id)`, `onOpenLink(url)`
- Produces: `renderEntryMenu(entry, onSelect)`, `renderAnswerCard(card, {onSelect, onBack, showBack})`, `appendCandidateBlock(userText, candidates, onSelect)`

- [ ] **Step 1: 구현**

```javascript
// ── 선택형 상담 플로우 ───────────────────────────────────────────
// 빠른 링크/바로가기(외부 URL) 칩.
function linkChip(label, url) {
  const a = document.createElement("a");
  a.className = "link-chip";
  a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer";
  a.textContent = label;
  return a;
}

// 첫 화면: 환영 카드 + 카테고리(드릴다운) + 추천 FAQ + 빠른 링크. #log 를 채운다.
export function renderEntryMenu(entry, onSelect) {
  const log = $("#log");
  log.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "consult-entry";

  const hello = document.createElement("div");
  hello.className = "welcome-card";
  hello.textContent = entry.welcome || "";
  wrap.appendChild(hello);

  if (entry.recommended?.length) {
    const rec = document.createElement("div");
    rec.className = "faq";
    const p = document.createElement("p");
    p.className = "faq-intro";
    p.textContent = "자주 묻는 질문";
    rec.appendChild(p);
    const row = document.createElement("div");
    row.className = "faq-row";
    entry.recommended.forEach(n => row.appendChild(makeChip(n.label, "faq-chip", () => onSelect(n.id))));
    rec.appendChild(row);
    wrap.appendChild(rec);
  }

  (entry.categories || []).forEach(cat => {
    const block = document.createElement("div");
    block.className = "cat-block";
    const head = makeChip(cat.label, "cat-chip", () => {
      const open = block.querySelector(".cat-docs");
      if (open) { open.remove(); return; }   // 토글
      const docs = document.createElement("div");
      docs.className = "cat-docs faq-row";
      cat.nodes.forEach(n => docs.appendChild(makeChip(n.label, "faq-chip", () => onSelect(n.id))));
      block.appendChild(docs);
    }, true);
    block.appendChild(head);
    wrap.appendChild(block);
  });

  if (entry.quick_links?.length) {
    const ql = document.createElement("div");
    ql.className = "quick-links";
    entry.quick_links.forEach(l => ql.appendChild(linkChip(l.label, l.url)));
    wrap.appendChild(ql);
  }

  log.appendChild(wrap);
  log.scrollTop = 0;
}

// 확정 답변 카드: 사용자 말풍선(질문) + 좌측 카드(본문·이미지·바로가기·관련·뒤로·출처).
export function renderAnswerCard(card, {onSelect, onBack, showBack}) {
  const log = $("#log");
  if (log.querySelector(".empty") || log.querySelector(".consult-entry")) log.innerHTML = "";

  const turn = document.createElement("div");
  turn.className = "turn";
  turn.innerHTML = `<div class="q">${escapeHtml(card.question)}</div>`
    + `<div class="a card"></div><div class="imgs"></div>`
    + `<div class="links"></div><div class="related"></div>`
    + `<div class="src"></div>`;
  log.appendChild(turn);

  setAnswerText(turn.querySelector(".a"), card.answer, "");
  renderImages(turn, card.images || []);

  if (card.links?.length) {
    const box = turn.querySelector(".links");
    card.links.forEach(l => box.appendChild(linkChip(l.label, l.url)));
  }

  const rel = turn.querySelector(".related");
  if (showBack && card.parent) {
    rel.appendChild(makeChip("‹ 뒤로", "back-chip", () => onBack()));
  }
  (card.related || []).forEach(r => rel.appendChild(makeChip(r.label, "rel-chip", () => onSelect(r.id))));

  if (card.sources?.length) renderSources(turn, card.sources);
  log.scrollTop = log.scrollHeight;
}

// 자유 입력 → 후보 노드 추천(또는 안내). userText 는 말풍선으로.
export function appendCandidateBlock(userText, candidates, onSelect) {
  appendUserBubble(userText);
  const log = $("#log");
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const p = document.createElement("p");
  p.className = "faq-intro";
  if (candidates.length) {
    p.textContent = "관련 있어 보이는 항목입니다. 선택해 주세요.";
    wrap.appendChild(p);
    const row = document.createElement("div");
    row.className = "faq-row";
    candidates.forEach(c => row.appendChild(makeChip(c.label, "faq-chip", () => onSelect(c.id))));
    wrap.appendChild(row);
  } else {
    p.textContent = "준비된 안내에서 찾지 못했습니다. e-Class QnA 게시판으로 문의 부탁드립니다.";
    wrap.appendChild(p);
  }
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}
```

- [ ] **Step 2: 문법 점검** — Run: `node --check static/js/ui.js` → 성공

- [ ] **Step 3: 커밋**

```bash
git add static/js/ui.js
git commit -m "feat(ui): renderEntryMenu·renderAnswerCard·후보 칩"
```

---

### Task 13: 컨트롤러 배선 (main.js) — `?mode=consult`

**Files:** Modify `static/js/main.js`. 기존 레거시 흐름은 유지하고, consult 모드를 분기로 추가한다.

- [ ] **Step 1: consult 컨트롤러 추가** (`main.js` 의 `ask` 정의 아래)

```javascript
// ── 선택형 상담 모드 (?mode=consult) ────────────────────────────
const CONSULT = new URLSearchParams(location.search).get("mode") === "consult";
const navStack = [];          // 방문한 노드 id (뒤로가기)
const cardCache = new Map();  // id → card (뒤로 시 재요청·재로그 없음)

async function enterMenu() {
  const entry = await api.fetchEntry();
  navStack.length = 0;
  if (!entry) { ui.renderEntry([], null, ask); return; }   // 폴백: 레거시 진입
  ui.renderEntryMenu(entry, selectNode);
}

async function selectNode(id) {
  let card = cardCache.get(id);
  if (!card) {
    card = await api.fetchAnswer(id);
    if (!card) { return; }
    cardCache.set(id, card);
  }
  navStack.push(id);
  ui.renderAnswerCard(card, {
    onSelect: selectNode,
    onBack: goBack,
    showBack: navStack.length > 1,
  });
}

function goBack() {
  navStack.pop();                       // 현재 제거
  const prev = navStack.pop();          // 직전(다시 push 됨)
  if (prev) selectNode(prev);
  else enterMenu();
}

async function consultSearch(q) {
  const candidates = await api.searchNodes(q);
  ui.appendCandidateBlock(q, candidates, selectNode);
}
```

- [ ] **Step 2: 진입 분기 — `showFaqSuggestions` 호출부 2곳을 모드 분기로 교체**

`consent()` 안의 `showFaqSuggestions();` (`main.js:36`) →
```javascript
  if (CONSULT) enterMenu(); else showFaqSuggestions();
```
복원 블록의 `showFaqSuggestions();` (`main.js:144`) →
```javascript
  if (CONSULT) enterMenu(); else showFaqSuggestions();
```

- [ ] **Step 3: 폼 submit 분기 — consult 모드는 노드 검색**

`#form` submit 핸들러(`main.js:111-119`) 의 본문 처음(값 추출 직후)에:
```javascript
  if (CONSULT) { consultSearch(q); return; }
```
(레거시 reroll/guide/ask 분기는 그대로 둔다 — 기본 모드 보존.)

- [ ] **Step 4: 문법 점검** — Run: `node --check static/js/main.js` → 성공

- [ ] **Step 5: 커밋**

```bash
git add static/js/main.js
git commit -m "feat(ui): ?mode=consult 선택형 컨트롤러 + 뒤로 스택"
```

---

### Task 14: 마크업/스타일 (index.html · app.css)

**Files:** Modify `static/index.html`(placeholder), `static/css/app.css`(스타일 추가)

- [ ] **Step 1: 입력 placeholder를 모드 무관하게 보조 문구로**

`static/index.html:21` 의 input placeholder 를 다음으로:
```html
    <input id="q" placeholder="질문을 입력하거나 위 메뉴에서 선택하세요" autocomplete="off" disabled>
```

- [ ] **Step 2: 카드/칩 스타일 추가** (`static/css/app.css` 끝에). 값은 기존 칩 톤에 맞춘 시작점이며 스모크에서 조정한다.

```css
/* ── 선택형 상담 플로우 ── */
.welcome-card { background:#f1f5ff; border:1px solid #d6e0ff; border-radius:12px;
  padding:14px 16px; margin-bottom:14px; line-height:1.6; color:#1f2d4d; }
.cat-block { margin:6px 0; }
.cat-docs { margin:8px 0 12px 8px; }
.a.card { background:#fff; border:1px solid #e6e8ec; border-radius:12px;
  padding:14px 16px; line-height:1.7; white-space:pre-wrap; }
.related { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.rel-chip, .back-chip { font-size:13px; }
.back-chip { background:#f0f1f3; }
.links, .quick-links { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.link-chip { display:inline-block; padding:8px 12px; border-radius:18px;
  background:#0b66ff; color:#fff; text-decoration:none; font-size:13px; }
.link-chip:hover { background:#0a5ae0; }
```

- [ ] **Step 3: 커밋**

```bash
git add static/index.html static/css/app.css
git commit -m "feat(ui): 상담 카드·관련·바로가기 스타일 + placeholder"
```

---

### Task 15: 라이브 스모크 + 검증 체크리스트

자동 단위테스트로 못 잡는 통합 동작을 실제 브라우저에서 확인한다.

- [ ] **Step 1: 전체 단위테스트 회귀**

Run: `python -m pytest -q`
Expected: 기존 + `test_nodes.py` 전부 PASS

- [ ] **Step 2: 서버 기동** — `bash run.sh` (또는 `uvicorn backend:app --port 8080`). 로그에 `[startup] 노드 레지스트리 N개`(N>0) 확인.

- [ ] **Step 3: 레거시 무회귀** — `http://localhost:8080/` (mode 없음): 기존 FAQ 칩·`/chat` 답변·이미지·피드백이 그대로 동작.

- [ ] **Step 4: 선택형 플로우** — `http://localhost:8080/?mode=consult`:
  - 동의 후 환영 카드 + "자주 묻는 질문" + 카테고리 + 빠른 링크 표시
  - 카테고리 클릭 → 하위 항목 펼침/접힘
  - 항목 클릭 → 질문 말풍선 + 확정 답변 카드(본문·이미지·관련 칩·출처). **gemma 스트리밍 없이 즉시 표시**
  - 관련 칩 클릭 → 새 카드, "‹ 뒤로" 로 직전 복귀(네트워크 재요청 없음)
  - 입력창에 자유 질문 → 후보 칩 또는 QnA 안내
  - 없는 항목 직접 호출(`/answer/zzz`) → 404

- [ ] **Step 5: (선택) QA 러너 프로파일** — `qa/devtools-profiles/` 에 consult 시나리오 프로파일 추가는 후속 과제. 본 단계는 수동 스모크로 충분.

- [ ] **Step 6: 스모크에서 조정한 파일만 커밋(있을 때만)**

```bash
# git add -A 금지 — 무관한 미커밋 변경(AGENT.md·package*.json)을 쓸어담지 않도록 조정한 파일만 명시.
git add static/css/app.css static/js/ui.js static/js/main.js   # 실제 조정한 파일만 골라서
git commit -m "chore(consult): 라이브 스모크 검증 결과 반영"
```
(스모크에서 고친 파일이 없으면 이 커밋은 생략한다.)

---

## Self-Review

**1. Spec coverage**
- 자동 도출 + 오버레이 → Task 2·3·5·8. 가이드 원문 직출력/FAQ 원문 → Task 3(`build_nodes`). ID 규칙(노드·카테고리·faq-root) → Task 1·3. 공개 `/entry`·`/answer/{id}`·`/search` → Task 10. 자유입력=노드 검색 → Task 6(`find_related`)·13. `?mode=consult` 병존 → Task 13. 첫 화면(환영·카테고리·추천·빠른링크) → Task 7·12. 관련/뒤로/바로가기 → Task 12·13. 레거시 무파괴 → Global Constraints + Task 10 Step 4. 선택 로깅·node_id 미포함(Phase 2) → 명시. **갭 없음.**

**2. Placeholder scan** — TBD/“적절히 처리” 없음. 모든 코드 step에 실제 코드 포함. CSS 값은 “시작점, 스모크에서 조정”으로 명시(임의 placeholder 아님).

**3. Type consistency** — `Node`/`Registry`/`AnswerCard`/`NodeLink`/`NodeRef` 시그니처가 Task 1·3·6·7에서 일치. `find_related(items, nodes, *, limit)`·`entry_payload(registry, catalog, *, n_recommended)`·`card_of(node)`·`build_registry(state, *, overlay_path)` 호출부(Task 10)와 정의부 일치. `_node_id`/`_cat_id`/`_norm` 전 Task 동일. JS: `renderEntryMenu(entry, onSelect)`·`renderAnswerCard(card, {onSelect,onBack,showBack})`·`appendCandidateBlock(userText, candidates, onSelect)` 정의(Task 12)와 호출(Task 13) 일치. `fetchEntry`/`fetchAnswer`/`searchNodes`(Task 11) ↔ 사용(Task 13) 일치.

**주의(실행자에게):** Task 6의 `AnswerCard` import는 Task 1에서 만든 `generation/nodes.py` 상단 `from app_types import ...` 줄에 합쳐 중복 import를 피한다. Task 8 스모크는 Task 9(config 경로) 이후 실행.
