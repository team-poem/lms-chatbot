# 섹션 단위 청킹·이미지 격리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 한 노션 페이지에 섞인 하위 섹션 때문에 다른 섹션 이미지가 답변에 딸려오는 문제를, 인제스트 섹션 분할과 1위 섹션 이미지 격리로 구조적으로 차단한다.

**Architecture:** 두 겹 격리. (1) 저장: 청커가 H2·H3 헤딩으로 섹션을 나눠 각 섹션이 자기 이미지만 보유하고 `section_id`를 갖는다. (2) 조립: `stream.py`가 이미지를 1위 청크의 섹션에서만 수집해, 텍스트 보조로 끌려온 형제 섹션 이미지를 배제한다. 수치 임계값에 의존하지 않는다.

**Tech Stack:** Python 3.11, pytest, ChromaDB(BGE-M3 임베딩), rank-bm25. 테스트는 `.venv/bin/python -m pytest`로 실행(시스템 python3엔 pandas/httpx 없음).

---

## 파일 구조

- `app_types.py` — `Chunk`에 `section_id` 필드 추가
- `ingest/chunk.py` — H2·H3 섹션 분할, preamble 처리, `section_id` 부여
- `index/vector_store.py` — 청크 메타 직렬화에 `section_id` 포함(`_chunk_meta` 헬퍼로 분리)
- `retrieval/search.py` — 메타에서 `section_id` 복원(`_chunk_from_meta` 헬퍼로 분리)
- `generation/stream.py` — 이미지 수집을 1위 섹션으로 제한(`_section_images` 헬퍼)
- 테스트: `tests/test_chunk.py`, `tests/test_vector_store.py`(신규), `tests/test_search.py`(신규), `tests/test_stream.py`

---

## Task 1: `Chunk.section_id` 필드 + CSV 청크 section_id

**Files:**
- Modify: `app_types.py:11-21`
- Modify: `ingest/chunk.py:130-155` (`chunk_csv_file`)
- Test: `tests/test_chunk.py`

- [ ] **Step 1: Write the failing test**

`tests/test_chunk.py` 끝에 추가:

```python
def test_csv_chunk_has_unique_section_id(tmp_path: Path):
    p = tmp_path / "FAQ.csv"
    pd.DataFrame({
        "FAQ": ["로그인이 안 됩니다", "수업계획서 입력 방법"],
        "메뉴명": ["기본", "수업계획서"],
    }).to_csv(p, index=False)
    chunks = chunk_csv_file(p, doc_set="faq")
    assert chunks[0].section_id  # 비어있지 않음
    assert chunks[0].section_id != chunks[1].section_id  # 행마다 고유
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_chunk.py::test_csv_chunk_has_unique_section_id -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'section_id'` 또는 빈 문자열로 AssertionError.

- [ ] **Step 3: Add field to Chunk**

`app_types.py`의 `Chunk` 데이터클래스에서 `title` 바로 아래에 한 줄 추가:

```python
@dataclass(frozen=True)
class Chunk:
    chunk_id: ChunkId
    text: str
    source: str
    doc_set: DocSet
    title: str
    section_id: str = ""
    section_path: tuple[str, ...] = ()
    image_refs: tuple[str, ...] = ()
    csv_refs: tuple[str, ...] = ()
    notion_url: str = ""
```

- [ ] **Step 4: Set section_id in chunk_csv_file**

`ingest/chunk.py`의 `chunk_csv_file` 안 `Chunk(...)` 생성에 `section_id`를 추가:

```python
        chunks.append(
            Chunk(
                chunk_id=_hash_id(source, str(i)),
                section_id=_hash_id(source, str(i)),
                text=text,
                source=source,
                doc_set=doc_set,
                title=base_title,
                section_path=(),
                csv_refs=(source,),
                notion_url=notion_url,
            )
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_chunk.py::test_csv_chunk_has_unique_section_id -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app_types.py ingest/chunk.py tests/test_chunk.py
git commit -m "feat(chunk): Chunk.section_id 필드 + CSV 행별 고유 section_id

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: H2·H3 섹션 분할과 이미지 격리 (chunk.py)

**Files:**
- Modify: `ingest/chunk.py:11-14` (정규식/상수), `ingest/chunk.py:83-127` (`chunk_markdown_file`)
- Test: `tests/test_chunk.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_chunk.py` 끝에 추가:

```python
def test_chunk_markdown_splits_h3_and_isolates_images(tmp_path: Path):
    text = (
        "# 로그인 페이지\n\n"
        "### 로그인\n\n로그인 설명 텍스트입니다.\n\n"
        "### 대시보드 표시 유형 선택\n\n설명\n\n![](img/dash.png)\n"
    )
    p = tmp_path / "로그인 34f0163ecf148120811ee6bae8783430.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    login = next(c for c in chunks if c.title.endswith("로그인"))
    dash = next(c for c in chunks if c.title.endswith("선택"))
    assert login.image_refs == ()                  # 로그인 섹션엔 이미지 없음
    assert dash.image_refs == ("img/dash.png",)    # 대시보드 섹션에만 이미지
    assert login.section_id != dash.section_id      # 섹션 분리


def test_same_section_long_split_shares_section_id(tmp_path: Path):
    big = "한국어 본문 데이터입니다 " * 400  # _MAX_CHARS(3000) 초과
    text = f"# 페이지\n\n## 섹션 A\n\n{big}\n\n## 섹션 B\n\n짧은 본문\n"
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    a = [c for c in chunks if "섹션 A" in c.title]
    b = [c for c in chunks if "섹션 B" in c.title]
    assert len(a) >= 2                              # 길이 분할됨
    assert len({c.section_id for c in a}) == 1      # 같은 섹션은 section_id 공유
    assert a[0].section_id != b[0].section_id       # 다른 섹션은 분리


def test_meaningful_preamble_becomes_chunk(tmp_path: Path):
    text = (
        "# 페이지 제목\n\n인트로 본문입니다.\n\n![](img/intro.png)\n\n"
        "## 섹션 A\n\n본문 A\n\n## 섹션 B\n\n본문 B\n"
    )
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    pre = next(c for c in chunks if "img/intro.png" in c.image_refs)
    assert "인트로 본문" in pre.text


def test_title_only_preamble_is_skipped(tmp_path: Path):
    text = "# 제목만\n\n## 섹션 A\n\n본문 A\n\n## 섹션 B\n\n본문 B\n"
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert len(chunks) == 2  # 제목만 있는 preamble은 청크가 안 생김


def test_single_heading_page_stays_one_chunk(tmp_path: Path):
    text = "# 페이지\n\n## 유일 섹션\n\n본문 짧음\n"
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert len(chunks) == 1  # 헤딩 1개면 분할하지 않음(과편화 방지)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chunk.py -k "h3 or section_id or preamble or single_heading" -v`
Expected: FAIL — 현재 청커는 H3를 분할하지 않고 작은 페이지를 통째 한 청크로 만들므로 분리/격리 단언이 깨진다.

- [ ] **Step 3: Replace heading regex and helpers**

`ingest/chunk.py` 상단의 정규식/상수 블록을 교체. 기존:

```python
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_H2_RE = re.compile(r"^##\s+(.+)$", flags=re.MULTILINE)
_TOKEN_LIMIT = 2000
_MAX_CHARS = 3000  # 임베더(BGE-M3, max_seq=1024)에 안전하게 들어가는 한국어 청크 상한
_OVERLAP = 200    # 분할 시 청크간 겹침
```

교체 후:

```python
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
# H2·H3 헤딩으로 섹션 분할. H1(#)은 페이지 제목이라 분할 대상이 아니다.
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$", flags=re.MULTILINE)
_H1_LINE_RE = re.compile(r"^#\s+.*$", flags=re.MULTILINE)
_MAX_CHARS = 3000  # 임베더(BGE-M3, max_seq=1024)에 안전하게 들어가는 한국어 청크 상한
_OVERLAP = 200    # 분할 시 청크간 겹침
```

(`_TOKEN_LIMIT`과, 아래 Step 5에서 더는 쓰이지 않는 `_approx_tokens`를 제거한다.)

- [ ] **Step 4: Remove the now-unused `_approx_tokens`**

`ingest/chunk.py`에서 다음 함수를 삭제:

```python
def _approx_tokens(text: str) -> int:
    return len(text.split())
```

- [ ] **Step 5: Add section-title cleaner and preamble check, rewrite chunk_markdown_file**

`ingest/chunk.py`에 헬퍼 2개를 추가(예: `_split_long` 위):

```python
def _clean_heading(s: str) -> str:
    return s.strip().strip("*").strip()


def _has_meaningful_preamble(preamble: str) -> bool:
    """첫 헤딩 앞 본문이 의미 있는가. 이미지가 있거나, H1 제목 줄을 뺀 텍스트가
    남으면 별도 청크로 보존한다. 제목만 있는 preamble 은 버린다."""
    if extract_image_refs(preamble):
        return True
    body = _H1_LINE_RE.sub("", preamble)
    return bool(body.strip())
```

`chunk_markdown_file`을 통째로 교체:

```python
def chunk_markdown_file(
    path: Path,
    *,
    doc_set: DocSet,
    section_path: list[str],
) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    title = _derive_title(path)
    source = str(path)
    notion_url = _extract_notion_url(path)

    def _emit(prefix: str, base_title: str, body: str) -> list[Chunk]:
        out: list[Chunk] = []
        parts = _split_long(body)
        section_id = _hash_id(source, prefix)  # 같은 섹션의 길이분할 연속분이 공유
        for j, part in enumerate(parts):
            suffix = "" if len(parts) == 1 else f" ({j + 1}/{len(parts)})"
            out.append(
                Chunk(
                    chunk_id=_hash_id(source, prefix, str(j)),
                    section_id=section_id,
                    text=part,
                    source=source,
                    doc_set=doc_set,
                    title=base_title + suffix,
                    section_path=tuple(section_path),
                    image_refs=tuple(extract_image_refs(part)),
                    notion_url=notion_url,
                )
            )
        return out

    matches = list(_HEADING_RE.finditer(text))
    # 헤딩이 2개 미만이면 분할하지 않는다(단순 페이지 과편화 방지).
    # 본문이 _MAX_CHARS 를 넘으면 _emit 내부의 _split_long 이 글자 기준으로 처리.
    if len(matches) < 2:
        return _emit("0", title, text)

    chunks: list[Chunk] = []
    preamble = text[: matches[0].start()]
    if _has_meaningful_preamble(preamble):
        chunks.extend(_emit("pre", title, preamble))
    for i, m in enumerate(matches):
        section_title = _clean_heading(m.group(2))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        chunks.extend(_emit(str(i), f"{title} — {section_title}", body))
    return chunks
```

- [ ] **Step 6: Run the new and existing chunk tests**

Run: `.venv/bin/python -m pytest tests/test_chunk.py -v`
Expected: PASS (신규 5개 + 기존 전부). 특히 기존 `test_chunk_markdown_large_splits_on_h2`(H2 2개)와 `test_chunk_markdown_enforces_char_limit`(헤딩 없음→글자분할)이 그대로 통과.

- [ ] **Step 7: Commit**

```bash
git add ingest/chunk.py tests/test_chunk.py
git commit -m "feat(chunk): H2·H3 섹션 분할로 이미지를 섹션별 격리

헤딩 2개 이상이면 토큰 수와 무관하게 섹션 분할. preamble 보존,
길이분할 연속분은 section_id 공유.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: section_id 저장·복원 (vector_store + search)

**Files:**
- Modify: `index/vector_store.py:34-49` (`upsert_chunks`)
- Modify: `retrieval/search.py:28-46`
- Test: `tests/test_vector_store.py` (신규), `tests/test_search.py` (신규)

- [ ] **Step 1: Write the failing tests**

`tests/test_vector_store.py` 생성:

```python
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
```

`tests/test_search.py` 생성:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_vector_store.py tests/test_search.py -v`
Expected: FAIL — `ImportError: cannot import name '_chunk_meta'` / `'_chunk_from_meta'`.

- [ ] **Step 3: Extract `_chunk_meta` and include section_id (vector_store)**

`index/vector_store.py`에 헬퍼를 추가하고 `upsert_chunks`가 그것을 쓰게 한다. `upsert_chunks` 위에 추가:

```python
def _chunk_meta(c: Chunk) -> dict:
    return {
        "source": c.source,
        "doc_set": c.doc_set,
        "title": c.title,
        "section_id": c.section_id,
        "section_path": " > ".join(c.section_path),
        "image_refs": ",".join(c.image_refs),
        "notion_url": c.notion_url,
    }
```

`upsert_chunks` 안의 `metas = [{...} for c in chunks]` 블록을 다음으로 교체:

```python
    ids = [c.chunk_id for c in chunks]
    docs = [c.text for c in chunks]
    metas = [_chunk_meta(c) for c in chunks]
    vecs = encode_texts(model, docs)
    coll.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)
```

- [ ] **Step 4: Extract `_chunk_from_meta` and restore section_id (search)**

`retrieval/search.py`에 헬퍼를 추가하고 루프가 그것을 쓰게 한다. `hybrid_search` 위에 추가:

```python
def _chunk_from_meta(cid: str, doc: str, meta: dict) -> Chunk:
    section_path = tuple(p for p in (meta.get("section_path") or "").split(" > ") if p)
    image_refs = tuple(s for s in (meta.get("image_refs") or "").split(",") if s)
    return Chunk(
        chunk_id=cid,
        text=doc,
        source=meta.get("source", ""),
        doc_set=meta.get("doc_set", "guide"),
        title=meta.get("title", ""),
        section_id=meta.get("section_id", "") or "",
        section_path=section_path,
        image_refs=image_refs,
        notion_url=meta.get("notion_url", "") or "",
    )
```

`hybrid_search` 안의 청크 재구성 루프를 다음으로 교체:

```python
    items: list[ScoredChunk] = []
    for cid, score in merged:
        if cid not in meta_by_id:
            continue
        doc, meta = meta_by_id[cid]
        items.append(ScoredChunk(chunk=_chunk_from_meta(cid, doc, meta), score=score))
    return Retrieval(items=tuple(items), top_score=merged[0][1], max_embed_sim=max_embed_sim)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_vector_store.py tests/test_search.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add index/vector_store.py retrieval/search.py tests/test_vector_store.py tests/test_search.py
git commit -m "feat(index): section_id 저장·복원 (chroma 메타 ↔ 검색 재구성)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 이미지는 1위 섹션에서만 (stream.py)

**Files:**
- Modify: `generation/stream.py:148-155` (이미지 수집 블록) + 헬퍼 추가
- Test: `tests/test_stream.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_stream.py` 끝에 추가:

```python
from app_types import Chunk, ScoredChunk
from generation.stream import _section_images


def _sc(section_id, imgs, cid):
    return ScoredChunk(
        chunk=Chunk(
            chunk_id=cid, text="", source="s", doc_set="guide", title="t",
            section_id=section_id, image_refs=tuple(imgs),
        ),
        score=1.0,
    )


def test_section_images_excludes_other_section():
    top = _sc("A", [], "a0")              # 1위 섹션, 이미지 없음
    neighbor = _sc("B", ["b.png"], "b0")  # 다른 섹션이 이미지 보유
    assert _section_images((top, neighbor)) == ()


def test_section_images_includes_same_section_continuation():
    top = _sc("A", ["a1.png"], "a0")
    cont = _sc("A", ["a2.png"], "a1")     # 같은 섹션 연속분
    other = _sc("B", ["b.png"], "b0")
    assert _section_images((top, cont, other)) == ("a1.png", "a2.png")


def test_section_images_empty_section_id_uses_top_only():
    top = _sc("", ["a.png"], "a0")
    other = _sc("", ["b.png"], "b0")
    assert _section_images((top, other)) == ("a.png",)


def test_section_images_empty_input():
    assert _section_images(()) == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_stream.py -k section_images -v`
Expected: FAIL — `ImportError: cannot import name '_section_images'`.

- [ ] **Step 3: Add `_section_images` helper**

`generation/stream.py`에 헬퍼 추가(예: `_is_source_worthy` 아래):

```python
def _section_images(relevant: tuple, limit: int = 5) -> tuple[str, ...]:
    """이미지는 1위 청크가 속한 섹션(같은 section_id)에서만 모은다. 다른 섹션이
    텍스트 컨텍스트로 끌려와도 이미지엔 기여하지 못하게 해, 형제 섹션 이미지가
    답변에 새는 것을 구조적으로 차단한다(수치 임계값 비의존). section_id 가 비어
    있으면(구 인덱스·CSV 등) 1위 청크 하나로만 제한한다."""
    if not relevant:
        return ()
    top = relevant[0]
    top_sid = top.chunk.section_id
    seen: list[str] = []
    for it in relevant:
        same = (it.chunk.section_id == top_sid) if top_sid else (it is top)
        if not same:
            continue
        for img in it.chunk.image_refs:
            if img and img not in seen:
                seen.append(img)
        if len(seen) >= limit:
            break
    return tuple(seen[:limit])
```

- [ ] **Step 4: Wire it into stream_response**

`generation/stream.py`의 이미지 수집 블록을 교체. 기존:

```python
    # 이미지 (상위 5장, 중복 제거, 등장 순서 보존)
    seen_imgs: list[str] = []
    for it in relevant:
        for img in it.chunk.image_refs:
            if img and img not in seen_imgs:
                seen_imgs.append(img)
        if len(seen_imgs) >= 5:
            break
```

교체 후:

```python
    # 이미지 (상위 5장): 1위 섹션에서만 수집해 형제 섹션 이미지 누수를 차단.
    seen_imgs = list(_section_images(relevant))
```

(아래 `yield ChatEvent(type="done", images=tuple(seen_imgs[:5]), ...)`는 그대로 둔다.)

- [ ] **Step 5: Run stream tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_stream.py -v`
Expected: PASS (신규 4개 + 기존 전부)

- [ ] **Step 6: Commit**

```bash
git add generation/stream.py tests/test_stream.py
git commit -m "feat(stream): 이미지를 1위 섹션에서만 수집해 섹션 누수 차단

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 코퍼스 재인덱싱

**Files:**
- 데이터만 재생성: `data/chroma/`, `data/bm25.pkl` (코드 변경 없음)

- [ ] **Step 1: 전체 테스트 통과 확인(재인덱싱 전 안전망)**

Run: `.venv/bin/python -m pytest -q`
Expected: 전부 PASS.

- [ ] **Step 2: 재인덱싱 실행**

Run: `.venv/bin/python -m ingest.cli`
Expected: `[1/5]`~`[5/5]` 로그 후 `완료`. 총 청크 수가 섹션 분할로 이전보다 늘어난다.

- [ ] **Step 3: 로그인 청크가 섹션 분리됐는지 데이터 확인**

Run:
```bash
PYTHONPATH=. .venv/bin/python -c "
from config import load_config
from rag.state import load_rag_state
from retrieval.search import hybrid_search
st = load_rag_state(load_config())
r = hybrid_search(st, '로그인이 안 되는데 어떻게 해야 하나요?')
for it in r.items[:3]:
    print(repr(it.chunk.title), '| section_id=', it.chunk.section_id, '| imgs=', it.chunk.image_refs)
"
```
Expected: 로그인 관련 청크의 `title`이 `… — 로그인` 형태로 분리되고, 그 청크의 `image_refs`가 비어 있음(대시보드 이미지가 안 붙음).

- [ ] **Step 4: Commit 재생성 인덱스(추적 대상인 경우)**

```bash
git status --short data/
# data/chroma, data/bm25.pkl 이 .gitignore 면(현재 *.pkl, data/ 무시) 커밋 불필요 — 운영은 호스트 볼륨.
# 추적 대상이면: git add data/chroma data/bm25.pkl && git commit -m "chore(index): 섹션 분할 반영 재인덱싱"
```

(주의: `.gitignore`/`.dockerignore`상 `data/`·`*.pkl`은 무시되며 운영은 호스트 볼륨 마운트다. 인덱스 산출물은 보통 커밋하지 않는다. 맥미니 배포 시에는 호스트에서 동일하게 `python -m ingest.cli`로 재인덱싱한다.)

---

## Task 6: 검증 (라이브 + 80문항 회귀)

**Files:** 없음(검증 전용)

- [ ] **Step 1: 서버 기동**

Run(백그라운드): `.venv/bin/python -m uvicorn backend:app --host 0.0.0.0 --port 8080`
대기: `until curl -fsS http://localhost:8080/health >/dev/null 2>&1; do sleep 1; done`

- [ ] **Step 2: 로그인/대시보드 이미지 격리 직접 확인**

Run:
```bash
python3 - <<'PY'
import json, urllib.request
BASE="http://localhost:8080"
sid=json.load(urllib.request.urlopen(urllib.request.Request(
    BASE+"/consent", data=json.dumps({"user_label":"verify"}).encode(),
    headers={"Content-Type":"application/json"})))["session_id"]
def ask(q):
    req=urllib.request.Request(BASE+"/chat",
        data=json.dumps({"session_id":sid,"query":q}).encode(),
        headers={"Content-Type":"application/json"})
    imgs=None
    for raw in urllib.request.urlopen(req, timeout=200):
        line=raw.decode("utf-8","replace").strip()
        if line.startswith("data:"):
            e=json.loads(line[5:].strip())
            if e.get("type")=="done": imgs=e.get("images")
    return imgs
print("로그인 images:", ask("로그인이 안 되는데 어떻게 해야 하나요?"))
print("대시보드 images:", ask("대시보드 표시 유형은 어떻게 선택하나요?"))
PY
```
Expected: "로그인" 응답의 images가 비어 있음(대시보드 이미지 안 붙음). "대시보드" 응답엔 해당 이미지가 붙음.

- [ ] **Step 3: 80문항 회귀 재실행**

Run: `node qa/devtools-qa-runner/src/cli.mjs --profile qa/devtools-qa-runner/profiles/lms-faq-verification.json --out reports/faq-full --timeout 200000`
그다음: `python3 -c "import json; rows=[json.loads(l) for l in open('reports/faq-full/answers.jsonl') if l.strip()]; print(len(rows),'건 캡처')"`
Expected: 과잉 거절 0건 유지. 섹션 분할로 인한 회귀 없음(혹시 점수 분포 변화로 떨어지는 문항이 있으면 기록).

- [ ] **Step 4: 사무직원용 보고서 생성(선택)**

Run: `node qa/devtools-qa-runner/report/human-report.mjs --report reports/faq-full`

- [ ] **Step 5: 서버 종료**

Run: `lsof -ti:8080 | xargs kill 2>/dev/null`

- [ ] **Step 6: 마무리**

검증 결과를 요약 보고. 회귀가 있으면 해당 문항을 별도 디버깅(systematic-debugging) 대상으로 분리.
