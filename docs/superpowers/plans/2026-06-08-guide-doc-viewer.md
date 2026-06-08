# 메뉴 → 가이드 문서 뷰어 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 메뉴 항목 클릭 시 매핑된 매뉴얼 문서의 본문+이미지+출처를 그대로 보여준다(RAG 우회).

**Architecture:** 청크에 `doc_title`·`seq` 추가 → `GET /guide?doc=`가 그 문서 청크를 seq순으로 재조립해 반환 → 프런트가 클릭 시 호출·렌더(404면 RAG 폴백). 답변 라우팅 불변.

**Tech Stack:** Python 3.11, FastAPI, pytest, ChromaDB, vanilla JS. 테스트는 `.venv/bin/python -m pytest`.

---

## Task 1: 청크에 doc_title·seq 추가 (app_types + 인제스트)

**Files:** `app_types.py`, `ingest/chunk.py`, `tests/test_chunk.py`

- [ ] **Step 1: Write failing tests** (append to tests/test_chunk.py)
```python
def test_markdown_chunks_share_doc_title_and_increment_seq(tmp_path: Path):
    text = ("# 퀴즈 개요\n\n인트로\n\n![](img/a.png)\n\n"
            "## 섹션 A\n\n본문 A\n\n## 섹션 B\n\n본문 B\n")
    p = tmp_path / "퀴즈 개요 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert all(c.doc_title == "퀴즈 개요" for c in chunks)   # 페이지 제목 공유, 섹션 접미사 없음
    seqs = [c.seq for c in chunks]
    assert seqs == list(range(len(chunks)))                  # 0부터 증가


def test_csv_chunks_have_doc_title_and_seq(tmp_path: Path):
    p = tmp_path / "FAQ.csv"
    pd.DataFrame({"FAQ": ["q1", "q2"], "메뉴명": ["a", "b"]}).to_csv(p, index=False)
    chunks = chunk_csv_file(p, doc_set="faq")
    assert chunks[0].doc_title and chunks[1].seq == 1
```

- [ ] **Step 2: Run, verify FAIL**
`.venv/bin/python -m pytest tests/test_chunk.py -k "doc_title or seq" -v`  (TypeError: unexpected keyword)

- [ ] **Step 3: Add fields to Chunk** (app_types.py), after `section_id`:
```python
    section_id: str = ""
    doc_title: str = ""
    seq: int = 0
    section_path: tuple[str, ...] = ()
```

- [ ] **Step 4: Assign in chunk_markdown_file** (ingest/chunk.py) — replace the function's `_emit` and add a seq counter. Inside `chunk_markdown_file`, before `def _emit`, add `seq = [0]`. Replace the `Chunk(...)` construction inside `_emit` with:
```python
        out: list[Chunk] = []
        parts = _split_long(body)
        section_id = _hash_id(source, prefix)
        for j, part in enumerate(parts):
            suffix = "" if len(parts) == 1 else f" ({j + 1}/{len(parts)})"
            out.append(
                Chunk(
                    chunk_id=_hash_id(source, prefix, str(j)),
                    section_id=section_id,
                    doc_title=title,        # 페이지 제목(섹션 접미사 없음)
                    seq=seq[0],
                    text=part,
                    source=source,
                    doc_set=doc_set,
                    title=base_title + suffix,
                    section_path=tuple(section_path),
                    image_refs=tuple(extract_image_refs(part)),
                    notion_url=notion_url,
                )
            )
            seq[0] += 1
        return out
```
(`title` is the `_derive_title(path)` page title already computed in chunk_markdown_file — keep that line.)

- [ ] **Step 5: Assign in chunk_csv_file** (ingest/chunk.py) — add to its `Chunk(...)`:
```python
                chunk_id=_hash_id(source, str(i)),
                section_id=_hash_id(source, str(i)),
                doc_title=base_title,
                seq=i,
```

- [ ] **Step 6: Run, verify PASS**
`.venv/bin/python -m pytest tests/test_chunk.py -v`  (all pass)

- [ ] **Step 7: Commit**
```bash
git add app_types.py ingest/chunk.py tests/test_chunk.py
git commit -m "feat(chunk): doc_title·seq 필드 (문서 매핑·순서)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: doc_title·seq 저장·복원 (index)

**Files:** `index/vector_store.py`, `retrieval/search.py`, `tests/test_vector_store.py`, `tests/test_search.py`

- [ ] **Step 1: Write failing tests**
Append to tests/test_vector_store.py:
```python
def test_chunk_meta_includes_doc_title_and_seq():
    from app_types import Chunk
    c = Chunk(chunk_id="c1", text="t", source="s", doc_set="guide", title="T",
              doc_title="페이지", seq=3)
    meta = _chunk_meta(c)
    assert meta["doc_title"] == "페이지"
    assert meta["seq"] == 3
```
Append to tests/test_search.py:
```python
def test_chunk_from_meta_restores_doc_title_and_seq():
    c = _chunk_from_meta("c1", "doc", {"doc_title": "페이지", "seq": 5})
    assert c.doc_title == "페이지"
    assert c.seq == 5


def test_chunk_from_meta_seq_defaults_zero():
    c = _chunk_from_meta("c1", "d", {})
    assert c.seq == 0
```

- [ ] **Step 2: Run, verify FAIL**
`.venv/bin/python -m pytest tests/test_vector_store.py tests/test_search.py -k "doc_title or seq" -v`

- [ ] **Step 3: vector_store `_chunk_meta`** — add keys (inside the returned dict):
```python
        "section_id": c.section_id,
        "doc_title": c.doc_title,
        "seq": c.seq,
```

- [ ] **Step 4: search `_chunk_from_meta`** — add fields to the Chunk(...) it builds:
```python
        section_id=meta.get("section_id", "") or "",
        doc_title=meta.get("doc_title", "") or "",
        seq=int(meta.get("seq", 0) or 0),
```

- [ ] **Step 5: Run, verify PASS** + full suite
`.venv/bin/python -m pytest tests/test_vector_store.py tests/test_search.py -v`
`.venv/bin/python -m pytest -q`

- [ ] **Step 6: Commit**
```bash
git add index/vector_store.py retrieval/search.py tests/test_vector_store.py tests/test_search.py
git commit -m "feat(index): doc_title·seq 저장·복원

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 카탈로그 (label, doc) 구조 + 매핑

**Files:** `generation/catalog.py`, `tests/test_catalog.py`

- [ ] **Step 1: Write failing tests** — replace the existing structure tests in tests/test_catalog.py with:
```python
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


def test_catalog_docs_exist_in_manual(tmp_path):
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
```

- [ ] **Step 2: Run, verify FAIL**
`.venv/bin/python -m pytest tests/test_catalog.py -v`  (AttributeError: .label/.doc)

- [ ] **Step 3: Rewrite generation/catalog.py** — add `CatalogItem` and change items to it; keep CatalogCategory/catalog_as_dict:
```python
"""첫 진입 카탈로그 메뉴 데이터. 각 항목은 화면 라벨(label)과 표시할 매뉴얼 문서
제목(doc)을 갖는다. 클릭 시 /guide?doc=<doc> 로 그 문서를 그대로 보여준다.
doc 은 실제 매뉴얼 페이지 제목(_derive_title 결과)과 정확히 일치해야 한다(매핑
정합성 테스트가 가드). 매뉴얼이 바뀌면 이 파일을 수동 갱신한다."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogItem:
    label: str
    doc: str


@dataclass(frozen=True)
class CatalogCategory:
    emoji: str
    name: str
    items: tuple[CatalogItem, ...]


def _i(label: str, doc: str) -> CatalogItem:
    return CatalogItem(label, doc)


CATALOG: tuple[CatalogCategory, ...] = (
    CatalogCategory("🔑", "로그인·기본 화면", (
        _i("로그인은 어떻게 하나요?", "로그인 대시보드 유형 선택"),
        _i("대시보드 표시 유형은 어떻게 선택하나요?", "로그인 대시보드 유형 선택"),
        _i("과목 홈(온라인 강의실 첫 화면)은 어떻게 보나요?", "과목 홈 (과목 온라인 강의실 첫 화면)"),
        _i("대시보드에서 최근 활동·할 일은 어떻게 보나요?", "대시보드 이용하기 - 과목 최근 활동 할 일 보기"),
        _i("마이페이지에서 학기는 어떻게 선택하나요?", "마이페이지 - 학기 선택하기"),
        _i("캘린더는 어떻게 사용하나요?", "캘린더"),
        _i("사용 언어는 어떻게 변경하나요?", "사용 언어 변경하기"),
    )),
    CatalogCategory("🗂️", "과목 운영·세팅", (
        _i("과목 메뉴는 어떻게 세팅하나요?", "과목 메뉴 세팅하기"),
        _i("수업 계획서는 어떻게 입력하나요?", "수업 계획서"),
        _i("주차학습은 어떻게 구성하나요?", "주차학습 개요 및 구성"),
        _i("과목 공개/비공개는 어떻게 설정하나요?", "공개 비공개 설정"),
        _i("학습요소 일정(마감일·이용기간)을 일괄 수정하려면 어떻게 하나요?", "학습요소 일정 일괄 수정하기 (마감일 이용시작일 이용종료일)"),
        _i("학습 활동 현황은 어떻게 보나요?", "학습 활동 현황"),
    )),
    CatalogCategory("🎬", "학습 콘텐츠(동영상·화상강의)", (
        _i("MyCMS에서 동영상은 어떻게 업로드하나요?", "학습 요소 - MyCMS에서 동영상 업로드하기"),
        _i("새 콘텐츠로 동영상은 어떻게 업로드하나요?", "학습 요소 - 새 콘텐츠에서 동영상 업로드하기"),
        _i("화상강의(Zoom)는 어떻게 추가하나요?", "학습 요소 - 화상강의 추가하기"),
    )),
    CatalogCategory("📝", "과제·채점", (
        _i("과제는 어떻게 추가하나요?", "학습 활동 - 과제 추가하기"),
        _i("과제·평가는 어떻게 이루어지나요?", "과제 및 평가 개요"),
        _i("SpeedGrader로 과제는 어떻게 채점하나요?", "SpeedGrader로 과제 채점하기"),
        _i("특정 과제에 기본 점수를 일괄 부여하려면 어떻게 하나요?", "특정 과제에 기본 점수 일괄 부여하기"),
        _i("성적표에서 과제 제출물을 일괄 다운로드하려면 어떻게 하나요?", "성적표에서 과제 제출물 일괄 다운로드"),
    )),
    CatalogCategory("🧪", "퀴즈·시험·문제유형", (
        _i("퀴즈는 어떻게 출제하나요?", "학습 활동 - 퀴즈 추가하기"),
        _i("문제은행은 어떻게 관리하나요?", "문제은행 관리하기"),
        _i("문제 그룹으로 퀴즈를 무작위 출제하려면 어떻게 하나요?", "문제 그룹을 이용하여 퀴즈 무작위 출제하기"),
        _i("특정 학생에게 퀴즈 응시 시간·횟수를 추가 부여하려면 어떻게 하나요?", "퀴즈 응시 시도 횟수 시간을 추가 부여하기"),
        _i("SpeedGrader로 시험·퀴즈는 어떻게 채점하나요?", "SpeedGrader로 시험 퀴즈 채점하기"),
        _i("퀴즈 풀이 로그·통계는 어떻게 조회하나요?", "퀴즈 통계 조회하기"),
        _i("문제 유형에는 어떤 것들이 있나요?", "문제 유형"),
    )),
    CatalogCategory("🏅", "성적", (
        _i("성적 메뉴의 주요 기능은 무엇인가요?", "성적 메뉴 이용하기 - 주요 기능 개요"),
        _i("성적은 어떻게 입력·편집하나요?", "성적 입력 및 편집"),
        _i("성적 공개 정책(전체·과제별)은 어떻게 설정하나요?", "성적 정책 설정1 성적 공개 설정"),
        _i("성적 자동 재계산은 어떻게 설정하나요?", "성적 자동 재계산 설정"),
        _i("성적표 메뉴는 어떻게 보나요?", "성적표 메뉴 보기"),
        _i("성적표에서 학생에게 메시지는 어떻게 보내나요?", "성적표 상에서 학생들에게 메세지 보내기 (미제출자 점수 기준 미달 대상 등)"),
    )),
    CatalogCategory("✅", "출결", (
        _i("출결현황은 어떻게 조회·관리하나요?", "출결현황 조회 및 관리"),
        _i("출결현황을 정렬·검색·엑셀 다운로드하려면 어떻게 하나요?", "출결현황 정렬 변경 검색 엑셀다운로드"),
        _i("동영상 강의 출결 조건은 어떻게 설정하나요?", "출결 조건 - 동영상 강의"),
        _i("화상강의(Zoom) 출결은 어떻게 관리하나요?", "출결 관리 - 화상강의 (Zoom)"),
        _i("출결 상태를 수동으로 변경(학습 인정)하려면 어떻게 하나요?", "출결 상태 수동 변경(학습 인정 처리)"),
        _i("출결 체크가 가능한 학습 요소는 무엇인가요?", "출결 체크가 가능한 학습 요소"),
    )),
    CatalogCategory("💬", "토론·피어리뷰·루브릭", (
        _i("토론은 어떻게 생성하나요?", "토론 생성하기"),
        _i("그룹(팀 프로젝트) 토론은 어떻게 생성하나요?", "그룹(팀 프로젝트) 토론 생성하기"),
        _i("피어리뷰(동료 평가) 토론은 어떻게 이용하나요?", "피어 리뷰(동료 평가) 토론 이용하기"),
        _i("루브릭은 어떻게 추가·관리하나요?", "루브릭 추가하기"),
        _i("퀴즈·토론에 루브릭을 추가하려면 어떻게 하나요?", "퀴즈에 루브릭 추가하기"),
    )),
    CatalogCategory("👥", "팀프로젝트(그룹)", (
        _i("팀프로젝트(그룹)는 어떻게 운영하나요?", "팀프로젝트(그룹) 개요"),
        _i("그룹 세트를 만들고 멤버를 구성하려면 어떻게 하나요?", "그룹 세트 만들고 멤버 구성하기"),
        _i("팀(그룹) 리더는 어떻게 지정하나요?", "팀(그룹) 리더 지정하기"),
        _i("팀 프로젝트 과제는 어떻게 출제하나요?", "팀 프로젝트 과제 출제하기"),
        _i("그룹별 홈페이지(팀 페이지)는 어떻게 방문하나요?", "그룹별 홈페이지(팀 페이지) 방문하기"),
    )),
    CatalogCategory("📢", "게시판·공지·메시지·알림", (
        _i("게시판은 어떻게 생성·관리하나요?", "게시판 생성하기"),
        _i("게시글은 어떻게 작성하나요?", "게시글 작성하기"),
        _i("공지사항은 어떻게 작성하나요?", "공지사항 작성하기"),
        _i("공지사항 공개 시간은 어떻게 예약하나요?", "공지사항 공개 시간 예약하기"),
        _i("메시지(쪽지)는 어떻게 보내나요?", "메시지(쪽지) 보내기"),
        _i("수강생 알림(개인별·과목별)은 어떻게 설정하나요?", "알림 설정 (개인별 과목별)"),
    )),
)


def catalog_as_dict() -> dict:
    return {"categories": [
        {"emoji": c.emoji, "name": c.name,
         "items": [{"label": it.label, "doc": it.doc} for it in c.items]}
        for c in CATALOG
    ]}
```

- [ ] **Step 4: Run, verify PASS** (incl. mapping integrity test — if any doc is missing, fix that doc string to match the real `_derive_title`)
`.venv/bin/python -m pytest tests/test_catalog.py -v`

- [ ] **Step 5: Commit**
```bash
git add generation/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): 항목을 (label, doc) 구조로 + 매뉴얼 문서 매핑

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: build_guide 순수 함수

**Files:** 신규 `generation/guide.py`, 신규 `tests/test_guide.py`

- [ ] **Step 1: Write failing tests** (tests/test_guide.py)
```python
from app_types import Chunk
from generation.guide import build_guide


def _c(doc_title, seq, text, imgs=(), notion=""):
    return Chunk(chunk_id=f"{doc_title}{seq}", text=text, source="s", doc_set="guide",
                 title=doc_title, doc_title=doc_title, seq=seq,
                 image_refs=tuple(imgs), notion_url=notion)


def test_build_guide_orders_by_seq_and_collects():
    chunks = [
        _c("P", 2, "둘째", ["b.png"]),
        _c("P", 0, "첫째", ["a.png"], notion="http://n"),
        _c("Q", 0, "다른문서", ["x.png"]),
    ]
    g = build_guide(chunks, "P")
    assert g["title"] == "P"
    assert g["text"].index("첫째") < g["text"].index("둘째")
    assert g["images"] == ["a.png", "b.png"]
    assert g["source_url"] == "http://n"


def test_build_guide_returns_none_when_missing():
    assert build_guide([], "P") is None
    assert build_guide([_c("Q", 0, "x")], "P") is None
```

- [ ] **Step 2: Run, verify FAIL** (ModuleNotFoundError)
`.venv/bin/python -m pytest tests/test_guide.py -v`

- [ ] **Step 3: Create generation/guide.py**
```python
"""메뉴 클릭 시 보여줄 매뉴얼 문서를 청크에서 재조립한다(검색 우회).
같은 doc_title 청크를 seq 순으로 이어 붙이고, 이미지를 등장순 중복제거하며,
출처 URL 은 첫 notion_url 을 쓴다. 해당 문서가 없으면 None."""
from __future__ import annotations


def build_guide(chunks, doc_title: str) -> dict | None:
    matched = sorted(
        (c for c in chunks if c.doc_title == doc_title),
        key=lambda c: c.seq,
    )
    if not matched:
        return None
    text = "\n\n".join(c.text.strip() for c in matched if c.text.strip())
    images: list[str] = []
    for c in matched:
        for img in c.image_refs:
            if img and img not in images:
                images.append(img)
    source_url = next((c.notion_url for c in matched if c.notion_url), "")
    return {"title": doc_title, "text": text, "images": images, "source_url": source_url}
```

- [ ] **Step 4: Run, verify PASS**
`.venv/bin/python -m pytest tests/test_guide.py -v`

- [ ] **Step 5: Commit**
```bash
git add generation/guide.py tests/test_guide.py
git commit -m "feat(guide): build_guide — 문서 청크를 seq순 재조립

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: GET /guide 엔드포인트

**Files:** `backend.py`

- [ ] **Step 1: Add the endpoint** — in backend.py, add imports near the other generation imports:
```python
from generation.guide import build_guide
from retrieval.search import _chunk_from_meta
from index.vector_store import get_collection
```
Add the route after the `/catalog` route (module-level async function `guide`):
```python
@app.get("/guide")
async def guide(doc: str = Query(...)):
    if _state is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    coll = get_collection(_state.chroma)
    res = coll.get(where={"doc_title": doc}, include=["documents", "metadatas"])
    chunks = [
        _chunk_from_meta(cid, d, m)
        for cid, d, m in zip(res["ids"], res["documents"], res["metadatas"])
    ]
    result = build_guide(chunks, doc)
    if result is None:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    return result
```
(`Query` and `HTTPException` are already imported in backend.py — verify; if `Query` is missing, add it to the FastAPI import line.)

- [ ] **Step 2: Smoke the route logic via build_guide tests already covered.** Run full suite:
`.venv/bin/python -m pytest -q`  (green; /guide itself needs live state — verified in Task 6)

- [ ] **Step 3: Commit**
```bash
git add backend.py
git commit -m "feat(backend): GET /guide?doc= — 매뉴얼 문서 조립 반환

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 프런트 뷰어 + 재인덱싱 + 검증

**Files:** `static/index.html`

- [ ] **Step 1: Update catalog item buttons** — in `showCatalogMenu()` (static/index.html), the item rendering currently does `ib.textContent = it; ib.onclick = () => ask(it);`. Items are now objects `{label, doc}`. Change the item loop body to:
```javascript
      (c.items || []).forEach(it => {
        const ib = document.createElement("button");
        ib.className = "item-btn";
        ib.textContent = it.label;
        ib.onclick = () => showGuide(it.doc, it.label);
        detail.appendChild(ib);
      });
```

- [ ] **Step 2: Add showGuide function** — add right after `showCatalogMenu` (or after `ask`):
```javascript
async function showGuide(doc, label) {
  const log = $("#log");
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `<div class="q">${escape(label)}</div><div class="a"><span class="loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span></div><div class="imgs"></div><div class="src"></div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  let g;
  try {
    const r = await fetch("/guide?doc=" + encodeURIComponent(doc));
    if (!r.ok) { div.remove(); return ask(label); }   // 404 → RAG 폴백
    g = await r.json();
  } catch (e) { div.remove(); return ask(label); }
  const a = div.querySelector(".a");
  a.innerHTML = "";
  a.textContent = g.text || "";
  const imgs = div.querySelector(".imgs");
  (g.images || []).forEach(src => {
    const i = document.createElement("img");
    i.src = src; i.loading = "lazy"; i.alt = "";
    i.onerror = () => i.remove();
    i.onclick = () => openLightbox(src);
    imgs.appendChild(i);
  });
  if (g.source_url) {
    const srcEl = div.querySelector(".src");
    const h = document.createElement("h4");
    h.innerHTML = ICON_PAPERCLIP + " <span>관련 문서</span>";
    srcEl.appendChild(h);
    const ul = document.createElement("ul");
    const li = document.createElement("li");
    li.insertAdjacentHTML("beforeend", ICON_DOC);
    const link = document.createElement("a");
    link.href = g.source_url; link.target = "_blank"; link.rel = "noopener noreferrer";
    link.textContent = g.title || doc;
    li.appendChild(link); ul.appendChild(li); srcEl.appendChild(ul);
  }
  log.scrollTop = log.scrollHeight;
}
```

- [ ] **Step 3: JS syntax check**
`node --check <(sed -n '/<script>/,/<\/script>/p' static/index.html | sed '1d;$d') 2>&1 | head -5 || echo "skip"`

- [ ] **Step 4: Re-index** (doc_title·seq 반영)
`.venv/bin/python -m ingest.cli`  (완료 로그 확인)

- [ ] **Step 5: 서버 기동 + 라이브 검증**
서버: `.venv/bin/python -m uvicorn backend:app --host 0.0.0.0 --port 8080` (백그라운드), health 대기.
검증:
```bash
curl -s "http://localhost:8080/guide?doc=SpeedGrader로 과제 채점하기" --get --data-urlencode "doc=SpeedGrader로 과제 채점하기" | python3 -c "import sys,json; d=json.load(sys.stdin); print('text', len(d['text']), '| imgs', len(d['images']), '| src', bool(d['source_url']))"
curl -s -o /dev/null -w "missing→%{http_code}\n" "http://localhost:8080/guide?doc=없는문서"
```
Expected: SpeedGrader 문서 text 길고 imgs>0 src=True; 없는문서 → 404.
브라우저 http://localhost:8080 에서 카테고리 → 항목 클릭 시 본문+이미지+출처 표시 육안 확인.

- [ ] **Step 6: Commit**
```bash
git add static/index.html
git commit -m "feat(web): 메뉴 항목 클릭 시 가이드 문서 뷰어(/guide) 렌더

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 비고
- 재인덱싱 필요(doc_title·seq). 데이터 그대로, 색인만 재생성.
- 자유질문 RAG/QnA·메타 거절·이미지 수집은 그대로.
- 통합 항목은 대표 문서 1개. 매핑 정합성은 test_catalog_docs_exist_in_manual 가 가드.
