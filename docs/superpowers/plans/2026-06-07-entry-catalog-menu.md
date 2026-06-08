# 첫 진입 카탈로그 메뉴 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대화창 첫 진입 시 매뉴얼 기반 카테고리 메뉴를 보여주고, 카테고리→항목 드릴다운으로 고른 질문이 기존 답변 경로로 처리되게 한다.

**Architecture:** 큐레이션 카탈로그(`generation/catalog.py`) → `GET /catalog`(JSON) → 프런트가 첫 진입에 메뉴 렌더·드릴다운. 답변 라우팅(메타/RAG/QnA)은 불변. 항목 클릭 = 그 텍스트를 기존 `ask()`로 전송.

**Tech Stack:** Python 3.11, FastAPI, pytest, vanilla JS. 테스트는 `.venv/bin/python -m pytest`.

---

## 파일 구조

- 신규 `generation/catalog.py` — 카탈로그 데이터 + `catalog_as_dict()`
- 신규 `tests/test_catalog.py` — 카탈로그 구조 + 엔드포인트 핸들러 테스트
- 수정 `backend.py` — `GET /catalog`
- 수정 `static/index.html` — 첫 진입 메뉴 CSS + `showCatalogMenu()` + 두 진입점 연결

---

## Task 1: 카탈로그 데이터 모듈

**Files:** 신규 `generation/catalog.py`, 신규 `tests/test_catalog.py`

- [ ] **Step 1: Write the failing test**

`tests/test_catalog.py`:
```python
from generation.catalog import CATALOG, catalog_as_dict


def test_catalog_has_categories_with_items():
    assert len(CATALOG) >= 5
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
```

- [ ] **Step 2: Run it, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: generation.catalog`.

- [ ] **Step 3: Create generation/catalog.py**

```python
"""첫 진입 카탈로그 메뉴 데이터. 96개 교수자 매뉴얼 문서에서 큐레이션한
카테고리·항목. 항목 문자열은 화면 라벨이자 클릭 시 그대로 전송되는 질문이다.
매뉴얼이 크게 바뀌면 이 파일을 수동 갱신한다(자동 생성은 후속 과제)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogCategory:
    emoji: str
    name: str
    items: tuple[str, ...]


CATALOG: tuple[CatalogCategory, ...] = (
    CatalogCategory("🔑", "로그인·기본 화면", (
        "로그인 / 대시보드 유형 선택",
        "과목 홈(온라인 강의실 첫 화면) 보기",
        "대시보드에서 최근 활동·할 일 보기",
        "마이페이지 / 학기 선택",
        "캘린더 사용하기",
        "사용 언어 변경하기",
    )),
    CatalogCategory("🗂️", "과목 운영·세팅", (
        "과목 메뉴 세팅하기",
        "수업 계획서 입력하기",
        "주차학습 개요 및 구성",
        "공개 / 비공개 설정",
        "학습요소 일정 일괄 수정하기(마감일·이용기간)",
        "학습 활동 현황 보기",
    )),
    CatalogCategory("🎬", "학습 콘텐츠(동영상·화상강의)", (
        "MyCMS에서 동영상 업로드하기",
        "새 콘텐츠에서 동영상 업로드하기",
        "화상강의(Zoom) 추가하기",
    )),
    CatalogCategory("📝", "과제·채점", (
        "과제 추가하기",
        "과제 및 평가 개요",
        "SpeedGrader로 과제 채점하기",
        "특정 과제에 기본 점수 일괄 부여하기",
        "성적표에서 과제 제출물 일괄 다운로드",
    )),
    CatalogCategory("🧪", "퀴즈·시험·문제유형", (
        "퀴즈 추가하기 / 퀴즈 개요",
        "문제은행 관리하기",
        "문제 그룹으로 퀴즈 무작위 출제하기",
        "퀴즈 응시 시도 횟수·시간 추가 부여하기",
        "SpeedGrader로 시험·퀴즈 채점하기",
        "퀴즈 풀이 로그·통계 조회하기",
        "문제 유형 종류(객관식·빈칸·짝짓기·참거짓·작문 등)",
    )),
    CatalogCategory("🏅", "성적", (
        "성적 메뉴 주요 기능 개요",
        "성적 입력 및 편집",
        "성적 공개 정책 설정(전체·과제별)",
        "성적 자동 재계산 설정",
        "성적표 메뉴 보기",
        "성적표에서 학생에게 메시지 보내기",
    )),
    CatalogCategory("✅", "출결", (
        "출결현황 조회 및 관리",
        "출결현황 정렬·검색·엑셀 다운로드",
        "동영상 강의 출결 조건",
        "화상강의(Zoom) 출결 관리",
        "출결 상태 수동 변경(학습 인정 처리)",
        "출결 체크가 가능한 학습 요소",
    )),
    CatalogCategory("💬", "토론·피어리뷰·루브릭", (
        "토론 생성하기",
        "그룹(팀 프로젝트) 토론 생성하기",
        "피어리뷰(동료 평가) 토론 이용하기",
        "루브릭 추가·관리하기",
        "퀴즈·토론에 루브릭 추가하기",
    )),
    CatalogCategory("👥", "팀프로젝트(그룹)", (
        "팀프로젝트(그룹) 개요",
        "그룹 세트 만들고 멤버 구성하기",
        "팀(그룹) 리더 지정하기",
        "팀 프로젝트 과제 출제하기",
        "그룹별 홈페이지(팀 페이지) 방문하기",
    )),
    CatalogCategory("📢", "게시판·공지·메시지·알림", (
        "게시판 생성·관리하기",
        "게시글 작성하기",
        "공지사항 작성하기",
        "공지사항 공개 시간 예약하기",
        "메시지(쪽지) 보내기 / 메시지함 사용하기",
        "수강생 알림 설정(개인별·과목별)",
    )),
)


def catalog_as_dict() -> dict:
    return {"categories": [
        {"emoji": c.emoji, "name": c.name, "items": list(c.items)}
        for c in CATALOG
    ]}
```

- [ ] **Step 4: Run it, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -v`  → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add generation/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): 첫 진입 메뉴용 큐레이션 카탈로그 데이터

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: GET /catalog 엔드포인트

**Files:** 수정 `backend.py`, 수정 `tests/test_catalog.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_catalog.py`:
```python
import asyncio
from backend import catalog as catalog_route


def test_catalog_endpoint_returns_categories():
    result = asyncio.run(catalog_route())
    assert "categories" in result
    assert result["categories"]
    assert result["categories"][0]["name"]
```

- [ ] **Step 2: Run it, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_catalog.py::test_catalog_endpoint_returns_categories -v`
Expected: FAIL — `ImportError: cannot import name 'catalog' from 'backend'`.

- [ ] **Step 3: Add the endpoint to backend.py**

Add the import near the other generation imports (with `from generation.stream import stream_response`):
```python
from generation.catalog import catalog_as_dict
```
Add the route just after the existing `@app.get("/health")` handler block (a module-level async function named `catalog` so the test can import it):
```python
@app.get("/catalog")
async def catalog():
    return catalog_as_dict()
```

- [ ] **Step 4: Run it, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -v`  → 3 passed.
Full suite: `.venv/bin/python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add backend.py tests/test_catalog.py
git commit -m "feat(backend): GET /catalog 엔드포인트

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 첫 진입 메뉴 (프런트)

**Files:** 수정 `static/index.html`

- [ ] **Step 1: Add CSS**

In `static/index.html`, insert these rules immediately before the closing `</style>` (right after the `.empty { ... }` rule at the end of the style block):
```css
  .catalog .cat-intro { color: #57606a; font-size: 13px; margin: 0 0 12px; }
  .catalog .cat-row { display: flex; flex-wrap: wrap; gap: 8px; }
  .catalog .cat-btn { background: #f6f8fa; }
  .catalog .cat-btn.active { background: #0969da; color: #fff; border-color: #0969da; }
  .catalog .cat-detail { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
  .catalog .item-btn { text-align: left; background: #fff; }
  .catalog .item-btn:hover { background: #f6f8fa; border-color: #afb8c1; }
```

- [ ] **Step 2: Add the showCatalogMenu function**

In the `<script>`, add this function immediately after the `escape(...)` function definition (the one-liner `function escape(s){...}`):
```javascript
async function showCatalogMenu() {
  const log = $("#log");
  let data;
  try {
    const r = await fetch("/catalog");
    if (!r.ok) return;            // 실패 시 기존 안내 문구 유지(graceful degradation)
    data = await r.json();
  } catch (e) { return; }
  if (!data.categories || !data.categories.length) return;
  log.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "catalog";
  const intro = document.createElement("p");
  intro.className = "cat-intro";
  intro.textContent = "무엇을 도와드릴까요? 아래에서 골라 보세요. (직접 입력도 가능합니다)";
  wrap.appendChild(intro);
  const catRow = document.createElement("div");
  catRow.className = "cat-row";
  const detail = document.createElement("div");
  detail.className = "cat-detail";
  data.categories.forEach(c => {
    const b = document.createElement("button");
    b.className = "cat-btn";
    b.textContent = (c.emoji ? c.emoji + " " : "") + c.name;
    b.onclick = () => {
      catRow.querySelectorAll(".cat-btn").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      detail.innerHTML = "";
      (c.items || []).forEach(it => {
        const ib = document.createElement("button");
        ib.className = "item-btn";
        ib.textContent = it;
        ib.onclick = () => ask(it);
        detail.appendChild(ib);
      });
    };
    catRow.appendChild(b);
  });
  wrap.appendChild(catRow);
  wrap.appendChild(detail);
  log.appendChild(wrap);
}
```

- [ ] **Step 3: Call it after consent (first-time entry)**

In `consent(userLabel)`, after the `$("#q").focus();` line (the last line before the function closes), add:
```javascript
  showCatalogMenu();
```

- [ ] **Step 4: Call it for returning visitors (saved session)**

In the bottom init block `if (saved && savedConsent) { ... }`, after the `if (lbl) $("#user-label").textContent = lbl;` line (inside the block), add:
```javascript
  showCatalogMenu();
```

- [ ] **Step 5: Manual sanity check (no unit test for static HTML)**

Confirm there are no JS syntax errors by serving and loading the page in Task 4 (live smoke). Do not add a test framework for the static page.

- [ ] **Step 6: Commit**

```bash
git add static/index.html
git commit -m "feat(web): 첫 진입 카탈로그 메뉴(카테고리→항목 드릴다운)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 검증 (전체 테스트 + 라이브 스모크)

**Files:** 없음(검증 전용)

- [ ] **Step 1: 전체 테스트**

Run: `.venv/bin/python -m pytest -q`  → 전부 PASS (test_catalog 3개 포함).

- [ ] **Step 2: 서버 기동**

Run(백그라운드): `QNA_BOARD_URL="https://lms.dongseo.ac.kr/qna" .venv/bin/python -m uvicorn backend:app --host 0.0.0.0 --port 8080`
대기: `until curl -fsS http://localhost:8080/health >/dev/null 2>&1; do sleep 1; done`

- [ ] **Step 3: /catalog 응답 확인**

Run: `curl -s http://localhost:8080/catalog | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['categories']),'categories'); print(d['categories'][0]['name'], '→', d['categories'][0]['items'][0])"`
Expected: `10 categories` 와 첫 카테고리·첫 항목 출력.

- [ ] **Step 4: 브라우저 육안 확인 (사용자)**

http://localhost:8080 접속 → 동의 후 첫 화면에 카테고리 버튼이 보이는지, 카테고리 클릭 시 항목이 펼쳐지는지, 항목 클릭 시 매뉴얼 답변이 나오는지 확인. (정적 페이지라 자동 테스트 대상 아님 — 육안 확인.)

- [ ] **Step 5: 서버 종료 / 마무리**

Run: `lsof -ti:8080 | xargs kill 2>/dev/null`
첫 진입 메뉴 동작을 요약 보고.

---

## 비고

- 답변 라우팅·QnA 폴백·이미지 격리는 이전 작업 그대로.
- 카탈로그는 정적 큐레이션 — 매뉴얼 변경 시 `generation/catalog.py` 수동 갱신.
- QA 하니스 재설계는 여전히 별도 과제.
