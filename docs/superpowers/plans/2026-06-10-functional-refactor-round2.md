# 함수형 리팩터링 2라운드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 행동 보존을 전제로 악취 11개(S1~S11)를 8개 커밋으로 제거 — 튜닝 상수 중앙화, 중복 해소, Ollama 클라이언트 추출, stream 분해, 계층 복원, backend 정리, 프런트 모듈 분리, 문서 동기화.

**Architecture:** 스펙 `docs/superpowers/specs/2026-06-10-functional-refactor-round2-design.md` 의 커밋 플랜을 그대로 따른다. 새 잎 모듈 `tuning.py`(무의존)와 `generation/ollama.py`(httpx 래퍼), `static/css/app.css` + `static/js/{api,ui,main}.js`(ES 모듈)가 생긴다. 매 Task = 1 커밋, 커밋 전 `.venv/bin/pytest -q` 그린 필수.

**Tech Stack:** Python 3 (FastAPI, httpx, chromadb, rank-bm25, sentence-transformers), 바닐라 JS ES modules (빌드 없음), pytest, QA 러너(node + chrome-devtools-mcp, ollama 필요).

**중요 — 작업 위치:** git worktree 를 쓰지 않는다. 서버·QA 러너가 git 추적 밖의 `data/`(chroma 인덱스, raw export, bm25.pkl)에 런타임 의존하므로 워크트리에서는 검증이 불가능하다. 본 체크아웃에서 `refactor/functional-cleanup` 브랜치로 작업한다.

**행동 보존 계약 (모든 Task 공통):** HTTP API(경로·JSON·상태코드·SSE 포맷), 인덱스/DB 스키마, 게이트 수치·판정 순서, 폴백 문구, run.sh/Dockerfile 인터페이스, 화면 동작 — 전부 변경 금지. 작업 중 이 계약과 충돌이 의심되면 멈추고 보고한다.

---

## Task 0: 브랜치 생성 + QA 베이스라인 채집

**Files:** 없음 (git/실행 환경만)

- [ ] **Step 0-1: 작업 트리 확인 및 브랜치 생성**

```bash
cd /Users/amazon/lunch.cancelled/lms-chatbot
git status --short   # 예상: 'm qa/devtools-qa-runner' + 'work/...' untracked 만 (리팩터링과 무관, 건드리지 않음)
git checkout -b refactor/functional-cleanup
```

- [ ] **Step 0-2: pytest 사전 그린 확인**

```bash
.venv/bin/pytest -q
```
예상: 전체 통과 (`28 passed` 이상, 현재 테스트 수 기준). 실패가 있으면 **리팩터링 시작 전에 보고** — 기존 깨짐 위에서 시작하지 않는다.

- [ ] **Step 0-3: ollama 가용 확인**

```bash
curl -s http://localhost:11434/api/tags | head -c 300
```
예상: `{"models":[...gemma3:4b...]}` 포함. 실패 시: `ollama serve` 를 별도 프로세스로 띄우고 재시도. ollama 자체가 없으면 **사용자에게 보고하고 지시 대기** (베이스라인 없이 진행할지는 사용자 결정 — 검증 기준이 "QA 러너 회귀까지"로 합의돼 있음).

- [ ] **Step 0-4: 서버 기동 (백그라운드)**

```bash
.venv/bin/python -m uvicorn backend:app --host 0.0.0.0 --port 8080
# 백그라운드로 실행. RagState 로드 10~20초 대기 후:
curl -s http://localhost:8080/health
```
예상: `{"ok":true,"consent_version":"2026-05-26-v1","qna_board_url":"https://eclass1..."}`

- [ ] **Step 0-5: QA 베이스라인 실행 및 보존**

```bash
npm run qa:paraphrase        # → reports/faq-paraphrase (타임아웃 180s/케이스, 수 분 소요)
npm run qa:paraphrase:judge  # LLM judge 판정
npm run qa:adversarial       # → reports/faq-adversarial
npm run qa:adversarial:judge
cp -r reports/faq-paraphrase reports/baseline-faq-paraphrase
cp -r reports/faq-adversarial reports/baseline-faq-adversarial
```
예상: 각 리포트 디렉터리에 결과 json/md 생성. judge 요약(통과/실패 수)을 기록해 둔다 — Task 10 에서 비교 기준. `reports/` 는 gitignore 라 커밋되지 않음.

- [ ] **Step 0-6: 서버 종료**

베이스라인 후 uvicorn 프로세스를 종료한다 (이후 Task 들은 pytest 만 필요).

---

## Task 1: `tuning.py` 신설 — 품질 튜닝 상수 중앙화 (S1)

**Files:**
- Create: `tuning.py`
- Modify: `generation/stream.py`, `retrieval/search.py`, `retrieval/hybrid.py`, `retrieval/cli.py`, `generation/relevance.py`, `generation/faq.py`, `ingest/chunk.py`, `index/embed.py`
- Test: `tests/test_stream.py`, `tests/test_faq.py` (import 갱신)

- [ ] **Step 1-1: `tuning.py` 생성** (실측 주석을 원문 그대로 보존한다)

```python
"""품질 튜닝 노브 단일 관리.

검색·답변 게이트·LLM 옵션·FAQ 노출 등 "품질을 조정할 때 만지는 숫자"를 한
파일에 모은다. 배포 환경 설정(경로·호스트)은 config.py, 정규식·컬렉션명 같은
구현 디테일은 각 모듈 소유 — 여기엔 품질 노브만 둔다.

이 모듈은 무엇도 임포트하지 않는 잎(leaf) 모듈이다 (config 와 동일 원칙).
"""

# ── 검색 (retrieval) ────────────────────────────────────────────────
TOP_K = 5      # 하이브리드 결합 후 컨텍스트 후보 상한
EMBED_K = 20   # 임베딩 검색 후보 폭
BM25_K = 20    # BM25 검색 후보 폭
# 하이브리드 가중치 (AGENT.md 검색 정책: BM25_norm * 0.4 + embed_sim * 0.6)
W_BM25 = 0.4
W_EMBED = 0.6

# ── 답변 게이트 (generation/stream) ─────────────────────────────────
SCORE_THRESHOLD = 0.25
# 원시 임베딩 유사도 절대 바닥. 매뉴얼 밖 질문(다크모드·날씨 등)은 무관 문서가
# 정규화 점수론 높게 잡혀 환각을 유발한다. 실측 분리: 매뉴얼 내 질문 최저 ~0.55,
# 명백한 헛질문 ~0.50 이하 → 0.50. (과거 0.60은 실제 질문도 막아 폐기됨.)
ABS_EMBED_FLOOR = 0.50
# 강한 매칭 기준. 이 이상이면 검색이 확실히 맞춘 것이라 LLM 관련성 게이트를 건너뛰고
# 무조건 답한다 — gemma:4b 게이트가 정확히 매칭된 FAQ(임베딩 0.72+)조차 오판해 추천
# 질문을 막은 사례가 있었다. 실측: 진짜 FAQ ≥0.72, 헛질문 ≤0.57 → 0.65에서 분리.
# 게이트는 애매 구간(0.50~0.65, 예: '주차장' 0.57)에서만 작동시킨다.
ABS_EMBED_CONFIDENT = 0.65
RELEVANCE_FLOOR = 0.30
RELEVANCE_RATIO = 0.60
# 컨텍스트로 LLM에 넘기는 청크 수 상한. 1위(정답) 외에 의미적으로 유사하지만
# 다른 주제의 청크가 섞여 답변을 오염시키는 것을 막는다(#39). 1위는 항상 포함.
MAX_CONTEXT_CHUNKS = 5
# 답변에 동반할 이미지 상한 (1순위 문서의 전 섹션에서 seq 순으로 수집)
MAX_IMAGES = 5

# ── 매뉴얼 라우팅 ───────────────────────────────────────────────────
# CMS 직접 언급 신호. 자유 입력은 이 신호가 있을 때만 CMS 로 스코핑하고, 그 외엔
# LMS 로 하드 고정한다 — LMS 질문(대다수)에 CMS 문서가 섞이지 않게. 'CMS'/'Cloud
# Editor' 처럼 LMS 와 혼동될 일 없는 표현만 넣는다('콘텐츠'는 LMS 에서도 흔해 제외).
CMS_TRIGGERS = ("cms", "cloud editor", "클라우드 에디터")

# ── LLM 호출 옵션 ───────────────────────────────────────────────────
# 답변 생성 (generation/stream)
GEN_OPTIONS = {"num_ctx": 8192, "temperature": 0.2}
GEN_TIMEOUT_S = 180.0
# 관련성 게이트 (generation/relevance) — 이진 판정이라 temperature 0
RELEVANCE_OPTIONS = {"temperature": 0.0}
RELEVANCE_TIMEOUT_S = 30.0

# ── FAQ 첫 진입 제안 (generation/faq) ───────────────────────────────
# 첫 진입에 노출할 FAQ 질문 개수 범위(무작위).
FAQ_ENTRY_MIN = 5
FAQ_ENTRY_MAX = 7

# ── 인제스트 (ingest/chunk) ─────────────────────────────────────────
CHUNK_MAX_CHARS = 3000  # 임베더(BGE-M3, max_seq=1024)에 안전하게 들어가는 한국어 청크 상한
CHUNK_OVERLAP = 200     # 분할 시 청크간 겹침

# ── 인덱스 (index/embed) ────────────────────────────────────────────
EMBED_MAX_SEQ_LEN = 1024  # CPU 추론 안전선 (BGE-M3 spec은 8192이나 메모리 폭주 방지)
```

- [ ] **Step 1-2: `generation/stream.py` 상수 치환**

모듈 상단의 상수 정의 중 tuning 으로 옮긴 것들(`SCORE_THRESHOLD`, `ABS_EMBED_FLOOR`, `ABS_EMBED_CONFIDENT`, `RELEVANCE_FLOOR`, `RELEVANCE_RATIO`, `MAX_CONTEXT_CHUNKS`, `_CMS_TRIGGERS` — 각자의 설명 주석 포함)을 삭제하고 import 로 대체. **`_FALLBACK_MARK`(주석 포함)와 `_FAQ_LABEL_RE`/`_MD_IMG_RE` 정의는 남긴다** (Task 4에서 이동).

```python
from tuning import (
    ABS_EMBED_CONFIDENT,
    ABS_EMBED_FLOOR,
    CMS_TRIGGERS,
    GEN_OPTIONS,
    GEN_TIMEOUT_S,
    MAX_CONTEXT_CHUNKS,
    MAX_IMAGES,
    RELEVANCE_FLOOR,
    RELEVANCE_RATIO,
    SCORE_THRESHOLD,
)
```

본문 치환 3곳:
- `_route_manual`: `_CMS_TRIGGERS` → `CMS_TRIGGERS`
- `_doc_images(... limit: int = 5 ...)` → `limit: int = MAX_IMAGES`
- Ollama payload/타임아웃:

```python
    payload = {
        "model": state.ollama_model,
        "messages": messages,
        "stream": True,
        "options": GEN_OPTIONS,
    }

    raw_buf = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(GEN_TIMEOUT_S)) as client:
```

- [ ] **Step 1-3: `retrieval/search.py`, `retrieval/hybrid.py`, `retrieval/cli.py` 치환**

search.py — 상수 3줄 삭제 후:
```python
from tuning import BM25_K, EMBED_K, TOP_K
```
(`hybrid_search(state, query, *, k: int = TOP_K, manual=None)` 시그니처는 그대로.)

hybrid.py — 기본 가중치를 tuning 참조로:
```python
from tuning import W_BM25, W_EMBED


def combine_scores(
    bm25_scores: dict[str, float],
    embed_scores: dict[str, float],
    *,
    w_bm25: float = W_BM25,
    w_embed: float = W_EMBED,
    k: int = 5,
) -> list[tuple[str, float]]:
```
(`k: int = 5` 는 호출부(search)가 항상 명시 전달하므로 그대로 둔다.)

cli.py — argparse 기본값 정렬:
```python
from tuning import TOP_K
# ...
    parser.add_argument("--k", type=int, default=TOP_K)
```

- [ ] **Step 1-4: `generation/relevance.py` 치환**

```python
from tuning import RELEVANCE_OPTIONS, RELEVANCE_TIMEOUT_S
# ...
async def doc_answers_question(
    host: str, model: str, query: str, title: str, text: str, *,
    timeout: float = RELEVANCE_TIMEOUT_S,
) -> bool | None:
    # payload 의 "options": RELEVANCE_OPTIONS
```

- [ ] **Step 1-5: `generation/faq.py` 치환**

`ENTRY_MIN = 5` / `ENTRY_MAX = 7` 두 줄(주석 포함)을 삭제하고:
```python
from tuning import FAQ_ENTRY_MAX, FAQ_ENTRY_MIN
# ...
def sample_for_entry() -> list[str]:
    """첫 진입용: 5~7개 사이 무작위 개수만큼 뽑는다."""
    return pick(load_questions(), random.randint(FAQ_ENTRY_MIN, FAQ_ENTRY_MAX))
```

- [ ] **Step 1-6: `ingest/chunk.py`, `index/embed.py` 치환**

chunk.py — `_MAX_CHARS`/`_OVERLAP` 정의 2줄 삭제, `from tuning import CHUNK_MAX_CHARS, CHUNK_OVERLAP` 추가, `_split_long` 내 3개 참조와 docstring(63행), 주석(148행)의 명칭 갱신:
```python
def _split_long(text: str) -> list[str]:
    """문자 길이 CHUNK_MAX_CHARS 를 넘는 본문을 약간 겹침을 주며 분할."""
    if len(text) <= CHUNK_MAX_CHARS:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_MAX_CHARS, len(text))
        # 줄바꿈 경계에서 자르기
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start + CHUNK_MAX_CHARS // 2:
                end = nl
        parts.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return parts
```

embed.py — `_MAX_SEQ_LEN` 정의 삭제:
```python
from tuning import EMBED_MAX_SEQ_LEN
# ...
    model.max_seq_length = EMBED_MAX_SEQ_LEN
```

- [ ] **Step 1-7: 테스트 import 갱신**

tests/test_stream.py 상단:
```python
from generation.stream import (
    _faq_answer,
    _is_relevant,
    _qna_fallback_msg,
    _route_manual,
)
from tuning import (
    ABS_EMBED_FLOOR,
    MAX_CONTEXT_CHUNKS,
    RELEVANCE_FLOOR,
    RELEVANCE_RATIO,
)
```

tests/test_faq.py 상단 + 마지막 테스트:
```python
from generation.faq import parse_questions, pick
from tuning import FAQ_ENTRY_MAX, FAQ_ENTRY_MIN
# ...
def test_entry_range_is_sane():
    assert 1 <= FAQ_ENTRY_MIN <= FAQ_ENTRY_MAX
```

- [ ] **Step 1-8: 테스트 + 커밋**

```bash
.venv/bin/pytest -q   # 예상: 전체 PASS
git add tuning.py generation/stream.py retrieval/search.py retrieval/hybrid.py retrieval/cli.py generation/relevance.py generation/faq.py ingest/chunk.py index/embed.py tests/test_stream.py tests/test_faq.py
git commit -m "refactor(tuning): 품질 튜닝 상수를 tuning.py 로 중앙화

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: 중복 해소 — `derive_title` 공개 승격 + `strip_empty_parens` 공용화 (S2, S3)

**Files:**
- Modify: `ingest/preprocess.py`, `ingest/chunk.py`, `ingest/pipeline.py`, `generation/catalog.py`
- Test: `tests/test_preprocess.py` (신규 테스트 추가)

- [ ] **Step 2-1: 실패하는 테스트 작성** — tests/test_preprocess.py 끝에 추가:

```python
def test_strip_empty_parens_removes_and_pads():
    from ingest.preprocess import strip_empty_parens
    # (📄) 장식이 이모지 제거 후 남긴 빈 괄호 — 공백 하나로 치환된다
    assert strip_empty_parens("제목 ( ) 끝") == "제목 끝"
    assert strip_empty_parens("제목()") == "제목 "
    assert strip_empty_parens("그대로") == "그대로"
```

- [ ] **Step 2-2: 실패 확인**

```bash
.venv/bin/pytest tests/test_preprocess.py -q
```
예상: FAIL — `ImportError: cannot import name 'strip_empty_parens'`

- [ ] **Step 2-3: `ingest/preprocess.py` 에 공용 함수 추가** (`_MULTI_BLANK` 정의 아래):

```python
# 파일명·목차 라벨에서 장식 이모지가 제거되고 남는 빈 괄호 '()' 제거용.
# chunk(derive_title)와 generation/catalog(_clean_doc_label)가 공유한다.
_EMPTY_PARENS_RE = re.compile(r"\s*\(\s*\)\s*")


def strip_empty_parens(text: str) -> str:
    return _EMPTY_PARENS_RE.sub(" ", text)
```

- [ ] **Step 2-4: `ingest/chunk.py` 정리**

- 상단에 `from ingest.preprocess import strip_emoji, strip_empty_parens` 추가
- `_EMPTY_PARENS_RE = re.compile(...)` (82행) 삭제
- `_derive_title` → `derive_title` 로 rename, 함수 내부의 지연 import 제거:

```python
def derive_title(path: Path) -> str:
    name = path.stem
    parts = name.rsplit(" ", 1)
    if len(parts) == 2 and len(parts[1]) >= 16:
        name = parts[0]
    # 파일명에 있던 (📄) 같은 장식 이모지가 preprocess 단계에서 사라지고
    # () 빈 괄호만 남는 경우가 흔함 — 제거하고 공백 정리.
    name = strip_emoji(name)
    name = strip_empty_parens(name)
    return name.strip()
```

- 내부 호출 2곳 갱신: `chunk_markdown_file` 의 `title = derive_title(path)`, `chunk_csv_file` 의 `base_title = f"FAQ — {derive_title(path)}"`

- [ ] **Step 2-5: 사용처 갱신**

ingest/pipeline.py 12행 import 와 49행:
```python
from ingest.chunk import (chunk_csv_file, chunk_markdown_file, derive_title,
                          is_contentful)
# ...
    sibling = md_path.parent / derive_title(md_path)
```

generation/catalog.py:
- 상단 import 를 `from ingest.preprocess import strip_emoji, strip_empty_parens` 로 확장하고 `from ingest.chunk import derive_title` 추가
- `_EMPTY_PARENS_RE = re.compile(...)` (34행) 삭제, `_clean_doc_label` 에서 `s = strip_empty_parens(s)` 로 치환
- `_find_manual_tocs`/`build_catalog` 안의 `from ingest.chunk import _derive_title` 지연 import 2곳 삭제, 호출은 `derive_title(...)` 로

- [ ] **Step 2-6: 테스트 + 커밋**

```bash
.venv/bin/pytest -q   # 예상: 전체 PASS (test_catalog·test_chunk·test_pipeline 포함)
git add ingest/preprocess.py ingest/chunk.py ingest/pipeline.py generation/catalog.py tests/test_preprocess.py
git commit -m "refactor(ingest): derive_title 공개 승격 + strip_empty_parens 공용화

generation/catalog 의 private cross-import(지연 import 2곳)와
_EMPTY_PARENS_RE 정규식 중복(chunk/catalog)을 해소한다.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: `generation/ollama.py` 추출 — Ollama HTTP 중복 제거 (S4)

**Files:**
- Create: `generation/ollama.py`
- Modify: `generation/stream.py`, `generation/relevance.py`

순수 I/O 래퍼라 신규 단위 테스트는 추가하지 않는다 (httpx mock 의존 추가는 YAGNI — 기존 test_relevance 의 build_prompt/parse_verdict 순수 함수 테스트 + Task 10 QA 회귀가 검증). pytest 그린은 import 무결성을 확인한다.

- [ ] **Step 3-1: `generation/ollama.py` 생성**

```python
"""Ollama /api/chat HTTP 클라이언트 — 스트리밍(chat_stream)·단발(chat).

stream.py(답변 생성)와 relevance.py(관련성 게이트)가 같은 엔드포인트를 각자
httpx 로 호출하던 중복을 모은다. 예외 처리는 호출부 정책에 맡긴다 — 생성은
전파(스트림 중단이 곧 실패), 게이트는 잡아서 None(답을 막지 않음).
"""
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx


async def chat_stream(
    host: str, model: str, messages: list[dict], *, options: dict, timeout: float
) -> AsyncIterator[str]:
    """스트리밍 chat. 토큰 델타(비어 있지 않은 것만)를 그대로 흘린다."""
    payload = {"model": model, "messages": messages, "stream": True, "options": options}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        async with client.stream("POST", f"{host}/api/chat", json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                delta = obj.get("message", {}).get("content", "")
                if delta:
                    yield delta
                if obj.get("done"):
                    break


async def chat(
    host: str, model: str, messages: list[dict], *, options: dict, timeout: float
) -> str:
    """단발 chat. 응답 본문 텍스트만 반환. HTTP 오류는 예외로 전파."""
    payload = {"model": model, "messages": messages, "stream": False, "options": options}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        resp = await client.post(f"{host}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
```

- [ ] **Step 3-2: `generation/stream.py` 호출부 교체**

import 정리: `import json`, `import httpx` 삭제(이 둘은 Ollama 호출에만 쓰였음), `from generation.ollama import chat_stream` 추가, `GEN_OPTIONS`/`GEN_TIMEOUT_S` import 유지.

기존 블록(payload 정의 ~ `async with httpx...` 루프 전체)을 다음으로 교체:

```python
    messages = build_prompt(
        query,
        [{"title": it.chunk.title, "text": it.chunk.text} for it in relevant],
    )

    raw_buf = ""
    async for delta in chat_stream(
        state.ollama_host,
        state.ollama_model,
        messages,
        options=GEN_OPTIONS,
        timeout=GEN_TIMEOUT_S,
    ):
        raw_buf += delta
        yield ChatEvent(type="text", delta=streaming_clean(delta))
```

(원래 코드의 `if delta:` 필터는 chat_stream 내부로 들어갔고, `url` 변수는 사라진다. 동작 동일.)

- [ ] **Step 3-3: `generation/relevance.py` 호출부 교체**

`import httpx` 삭제, `from generation import ollama` 추가:

```python
async def doc_answers_question(
    host: str, model: str, query: str, title: str, text: str, *,
    timeout: float = RELEVANCE_TIMEOUT_S,
) -> bool | None:
    """1위 문서가 질문에 답하는가. LLM 호출/파싱 실패 시 None(통과 — 답을 막지 않음)."""
    messages = [{"role": "user", "content": build_prompt(query, title, text)}]
    try:
        reply = await ollama.chat(
            host, model, messages, options=RELEVANCE_OPTIONS, timeout=timeout
        )
    except Exception:
        return None
    return parse_verdict(reply)
```

- [ ] **Step 3-4: 테스트 + 커밋**

```bash
.venv/bin/pytest -q   # 예상: 전체 PASS
git add generation/ollama.py generation/stream.py generation/relevance.py
git commit -m "refactor(generation): Ollama HTTP 클라이언트 추출 (chat/chat_stream)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: `stream.py` 분해 — 폴백 이벤트·FAQ 답변·폴백 문구 분리 (S5, S6)

**Files:**
- Modify: `generation/stream.py`, `generation/faq.py`, `generation/persona.py`
- Test: `tests/test_stream.py` (fallback_events 신규 + import 갱신), `tests/test_faq.py` (faq_answer 테스트 이주), Create: `tests/test_persona.py`

- [ ] **Step 4-1: 실패하는 테스트 작성** — tests/test_stream.py 에 추가:

```python
from generation.stream import fallback_events  # import 블록에 추가


def test_fallback_events_triplet():
    evts = fallback_events("안내문", score=0.42)
    assert [e.type for e in evts] == ["text", "text_final", "done"]
    assert evts[0].delta == "안내문"
    assert evts[1].text == "안내문"
    assert evts[2].score == 0.42


def test_fallback_events_default_score_zero():
    assert fallback_events("x")[2].score == 0.0
```

- [ ] **Step 4-2: 실패 확인**

```bash
.venv/bin/pytest tests/test_stream.py -q
```
예상: FAIL — `ImportError: cannot import name 'fallback_events'`

- [ ] **Step 4-3: `generation/persona.py` 에 폴백 문구 이동** (파일 끝에 추가)

```python
# 폴백 답변(매뉴얼 밖) 식별 표지 — 게이트·생성(규칙 5 문구) 양쪽 폴백에 공통으로
# 들어간다. 답변에 이 문구가 있으면 이미지·출처를 붙이지 않는다.
FALLBACK_MARK = "확인되지 않는 질문입니다"


def qna_fallback_msg(qna_contact: str = "") -> str:
    """매뉴얼(준비된 답변)에서 근거를 못 찾은 질문에 대한 안내. 위 PERSONA_SYSTEM
    규칙 5의 문장과 동일하게 맞춘다(게이트·생성 양쪽 폴백이 같은 문구 — 같은 파일에
    둬서 동기화를 배치로 보장). 'e-Class QnA 게시판' 문구는 프론트가 게시판 URL
    하이퍼링크로 렌더하므로 여기엔 URL을 넣지 않는다."""
    contact = f"{qna_contact} 또는 " if qna_contact else ""
    return (
        "준비된 매뉴얼 답변에서 확인되지 않는 질문입니다. "
        f"{contact}e-Class QnA 게시판으로 문의 부탁드립니다."
    )
```

- [ ] **Step 4-4: `generation/faq.py` 에 FAQ 답변 추출 이동** (`import re` 추가, parse_questions 위에 배치)

```python
_FAQ_LABEL_RE = re.compile(r"\*{0,2}\s*답변\s*\*{0,2}\s*[:：]\s*")
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def faq_answer(text: str) -> str:
    """FAQ 문서 본문에서 '답변' 텍스트만 추출한다. FAQ 는 사람이 작성한 정답이라
    gemma 로 재생성하면 질문 되풀이·원인 누락 등 손실이 생겨, 원문을 그대로 쓴다.
    제목('# 질문') 줄·'답변 :' 라벨·이미지 마크다운(이미지는 별도 영역)을 제거한다."""
    body = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    body = _MD_IMG_RE.sub("", body)
    body = _FAQ_LABEL_RE.sub("", body, count=1)
    return re.sub(r"\n{3,}", "\n\n", body).strip()
```

- [ ] **Step 4-5: `generation/stream.py` 재구성**

삭제: `_FAQ_LABEL_RE`, `_MD_IMG_RE`, `_faq_answer`, `_qna_fallback_msg`, `_FALLBACK_MARK`, `import re`.

import 추가/갱신:
```python
from generation.faq import faq_answer
from generation.persona import FALLBACK_MARK, build_prompt, qna_fallback_msg
```

신설 (모듈 함수, `_route_manual` 아래):
```python
def fallback_events(msg: str, *, score: float = 0.0) -> tuple[ChatEvent, ...]:
    """폴백 안내를 SSE 3-이벤트(text/text_final/done)로 만든다. 게이트 셋(메타
    질문·임베딩 바닥·관련성)이 같은 형태로 종료하던 중복을 모은 순수 함수."""
    return (
        ChatEvent(type="text", delta=msg),
        ChatEvent(type="text_final", text=msg),
        ChatEvent(type="done", score=score),
    )
```

`stream_response` 안의 3개 폴백 블록 교체 (각각 기존 yield 3줄 + return):

```python
    if is_meta_question(query):
        # 챗봇 자체/범위 밖 질문도 매뉴얼 밖 질문과 동일하게 QnA 안내로 통일한다.
        for evt in fallback_events(qna_fallback_msg(state.qna_contact)):
            yield evt
        return
```

```python
    if retrieval.max_embed_sim < ABS_EMBED_FLOOR or top_score < SCORE_THRESHOLD:
        for evt in fallback_events(qna_fallback_msg(state.qna_contact), score=top_score):
            yield evt
        return
```

```python
    if retrieval.max_embed_sim < ABS_EMBED_CONFIDENT and await doc_answers_question(
        state.ollama_host, state.ollama_model, query, primary.title, primary.text
    ) is False:
        for evt in fallback_events(qna_fallback_msg(state.qna_contact), score=top_score):
            yield evt
        return
```

(주의: 첫 번째 메타 질문 폴백의 기존 `ChatEvent(type="done")` 는 score 기본값 0.0 — `fallback_events(msg)` 기본값과 동일하다.)

본문 치환: `answer = _faq_answer(primary.text)` → `answer = faq_answer(primary.text)`, `if _FALLBACK_MARK in answer:` → `if FALLBACK_MARK in answer:`

- [ ] **Step 4-6: 테스트 이주**

tests/test_stream.py — import 블록을 다음으로, `test_faq_answer_*` 2개와 `test_qna_fallback_*` 2개 테스트를 **삭제**(아래 파일들로 이주):
```python
from generation.stream import _is_relevant, _route_manual, fallback_events
from tuning import (
    ABS_EMBED_FLOOR,
    MAX_CONTEXT_CHUNKS,
    RELEVANCE_FLOOR,
    RELEVANCE_RATIO,
)
```

tests/test_faq.py — import 에 `faq_answer` 추가하고 끝에 이주 (본문은 기존 test_stream 의 것과 동일, 함수명만 갱신):
```python
from generation.faq import faq_answer, parse_questions, pick


def test_faq_answer_extracts_answer_only():
    text = "# 블루프린트 동기화가 안돼요?\n\n **답변** : 연결된 주차 삭제 시 동기화가 안 됩니다. 복원하세요.\n"
    assert faq_answer(text) == "연결된 주차 삭제 시 동기화가 안 됩니다. 복원하세요."


def test_faq_answer_strips_image_and_keeps_link_phrase():
    text = ("# 문의는 어디에?\n\n **답변** : 문의는 Q&A 게시판으로 남겨주세요.\n\n"
            "- 메인 페이지 : Q&A 바로가기\n\n![image.png](/assets/x.png)\n")
    out = faq_answer(text)
    assert "![" not in out
    assert "Q&A 바로가기" in out
    assert out.startswith("문의는 Q&A 게시판으로 남겨주세요.")
```

Create tests/test_persona.py:
```python
from generation.persona import FALLBACK_MARK, qna_fallback_msg


def test_qna_fallback_includes_contact_and_board_phrase():
    msg = qna_fallback_msg("교육혁신처 051-320-0000")
    assert "교육혁신처 051-320-0000" in msg
    assert "e-Class QnA 게시판" in msg   # 프론트가 하이퍼링크로 거는 문구
    assert "문의 부탁드립니다" in msg


def test_qna_fallback_without_contact():
    # 기본(연락처 없음): QnA 게시판만 안내, 전화번호 일절 없음.
    msg = qna_fallback_msg("")
    assert msg == "준비된 매뉴얼 답변에서 확인되지 않는 질문입니다. e-Class QnA 게시판으로 문의 부탁드립니다."
    assert "051" not in msg and "☎" not in msg and "또는" not in msg


def test_fallback_mark_is_substring_of_fallback_msg():
    # 식별 표지는 규칙 5 문구의 부분 문자열이어야 폴백 감지가 동작한다.
    assert FALLBACK_MARK in qna_fallback_msg("")
```

- [ ] **Step 4-7: 테스트 + 커밋**

```bash
.venv/bin/pytest -q   # 예상: 전체 PASS (신규 포함)
git add generation/stream.py generation/faq.py generation/persona.py tests/test_stream.py tests/test_faq.py tests/test_persona.py
git commit -m "refactor(generation): stream.py 분해 — 폴백 이벤트·FAQ 답변·폴백 문구 분리

폴백 3-이벤트 yield 3회 중복 → fallback_events 순수 함수.
faq_answer 는 FAQ 도메인(faq.py)으로, qna_fallback_msg/FALLBACK_MARK 는
규칙 5 문구와 같은 파일(persona.py)로 — 동기화를 배치로 보장.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: 이미지 조회 계층 복원 — generation → retrieval (S7)

**Files:**
- Modify: `retrieval/search.py`, `generation/stream.py`

chroma 클라이언트가 필요한 조회 함수라 신규 단위 테스트는 추가하지 않는다 (Task 9 서버 스모크의 이미지 노출 확인 + Task 10 QA 가 검증).

- [ ] **Step 5-1: `retrieval/search.py` 에 `doc_image_refs` 추가** (파일 끝)

```python
def doc_image_refs(state: RagState, doc_title: str, *, manual: str = "") -> tuple[str, ...]:
    """문서(doc_title)의 모든 섹션 image_refs 를 seq 순으로 모은다(중복 제거).
    manual 지정 시 동명 문서가 다른 매뉴얼에 있어도 섞이지 않게 함께 필터한다.
    조회 실패/빈 doc_title 이면 빈 튜플 — 컨텍스트 청크 이미지로의 폴백은 호출부
    (generation) 책임."""
    refs: list[str] = []
    try:
        if doc_title:
            where = {"doc_title": doc_title}
            if manual:
                where = {"$and": [{"doc_title": doc_title}, {"manual": manual}]}
            res = get_collection(state.chroma).get(where=where, include=["metadatas"])
            metas = list(res.get("metadatas") or [])
            metas.sort(key=lambda m: int(m.get("seq", 0) or 0))
            for m in metas:
                for img in (m.get("image_refs") or "").split(","):
                    if img and img not in refs:
                        refs.append(img)
    except Exception:
        return ()
    return tuple(refs)
```

(try 범위를 원본(`stream._doc_images`)과 동일하게 본문 전체로 유지 — 메타데이터 이상값으로 sort 가 던져도 폴백 경로로 빠지는 기존 동작 보존.)

- [ ] **Step 5-2: `generation/stream.py` 의 `_doc_images` 축소**

`from index.vector_store import get_collection` import 삭제, `from retrieval.search import doc_image_refs, hybrid_search` 로 갱신.

```python
def _doc_images(
    state: RagState, doc_title: str, fallback_items, limit: int = MAX_IMAGES,
    *, manual: str = "",
) -> list[str]:
    """1순위 문서의 전 섹션 이미지(retrieval 조회, seq 순·중복 제거)를 모은다.
    컨텍스트 청크에만 의존할 때 생기는 누락을 막는다. 조회 실패/빈 결과면
    컨텍스트 청크(fallback_items)의 이미지로 대체한다."""
    refs = list(doc_image_refs(state, doc_title, manual=manual))
    if not refs:
        for it in fallback_items:
            for img in it.chunk.image_refs:
                if img and img not in refs:
                    refs.append(img)
    return refs[:limit]
```

- [ ] **Step 5-3: 테스트 + 커밋**

```bash
.venv/bin/pytest -q   # 예상: 전체 PASS
git add retrieval/search.py generation/stream.py
git commit -m "refactor(retrieval): 문서 이미지 조회를 retrieval 계층으로 이동

generation 이 chroma 컬렉션을 직접 조회하던 유일한 계층 위반(AGENT.md
디렉터리 맵: retrieval/ 는 '인덱스에서 검색만') 해소.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 6: backend.py 정리 — import 부수효과 제거 + SSE 직렬화 단순화 (S8, S9)

**Files:**
- Modify: `backend.py`
- Test: Create `tests/test_sse.py`

- [ ] **Step 6-1: 직렬화 고정(characterization) 테스트 작성** — tests/test_sse.py:

```python
"""SSE 직렬화 고정 테스트. backend._serialize_sse 의 출력 JSON 을 바이트 수준으로
고정한다 — asdict 단순화(리팩터링) 전후로 포맷이 변하지 않음을 보장."""
from app_types import ChatEvent, Source
from backend import _serialize_sse


def test_serialize_text_event():
    line = _serialize_sse(ChatEvent(type="text", delta="안녕"))
    assert line == (
        'data: {"type": "text", "delta": "안녕", "text": "", "images": [], '
        '"sources": [], "score": 0.0, "turn_id": null}\n\n'
    )


def test_serialize_done_event_with_nested_dataclass_and_tuples():
    evt = ChatEvent(
        type="done",
        images=("/assets/a.png",),
        sources=(Source(title="출결 관리", url="https://www.notion.so/x"),),
        score=0.5,
    )
    assert _serialize_sse(evt) == (
        'data: {"type": "done", "delta": "", "text": "", '
        '"images": ["/assets/a.png"], '
        '"sources": [{"title": "출결 관리", "url": "https://www.notion.so/x"}], '
        '"score": 0.5, "turn_id": null}\n\n'
    )


def test_serialize_plain_dict_passthrough():
    assert _serialize_sse({"type": "x"}) == 'data: {"type": "x"}\n\n'
```

- [ ] **Step 6-2: 기존 구현으로 그린 확인** (고정 테스트는 리팩터링 전에 통과해야 의미가 있다)

```bash
.venv/bin/pytest tests/test_sse.py -q
```
예상: PASS (3 passed). 실패하면 기대 문자열을 **현재 구현 출력에 맞춰** 고친 뒤 진행 (구현을 고치는 게 아니라 테스트가 현재 동작을 정확히 박제해야 함).

- [ ] **Step 6-3: backend.py 수정**

상단 (모듈 레벨 부수효과 축소 — `config = load_config()` 와 mount 는 앱 구성에 필요해 유지):

```python
from fastapi import FastAPI, Header, HTTPException, Query, Request
# ...
config = load_config()


def _serialize_sse(evt: ChatEvent | dict) -> str:
    """ChatEvent | dict → SSE 라인. asdict 가 중첩 dataclass·tuple 을 재귀
    변환하고 json.dumps 가 tuple 을 배열로 직렬화한다 (tests/test_sse.py 로 고정)."""
    payload = asdict(evt) if is_dataclass(evt) else evt
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_schema(config.logs_db_path)
    print("[startup] RagState 사전 로드 시작 (BGE-M3, 약 10~20초)...", flush=True)
    t0 = time.time()
    app.state.rag = await asyncio.to_thread(load_rag_state, config)
    print(f"[startup] RagState 준비 완료 ({time.time() - t0:.1f}s)", flush=True)
    yield
```

삭제: `store.init_schema(config.logs_db_path)` (모듈 레벨), `_state: RagState | None = None`, `_build_state_sync`, 기존 `_serialize_sse` 본문. import 정리: `from rag.state import RagState, load_rag_state` 유지 (`RagState` 는 `_chat_sse` 타입 힌트에 사용).

`/chat` 핸들러와 `_chat_sse`:

```python
@app.post("/chat")
async def chat(body: ChatBody, request: Request):
    if not store.get_session(config.logs_db_path, body.session_id):
        raise HTTPException(status_code=403, detail="동의 후 사용 가능합니다")
    state = getattr(request.app.state, "rag", None)
    if state is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    return StreamingResponse(_chat_sse(state, body), media_type="text/event-stream")


async def _chat_sse(state: RagState, body: ChatBody):
    started = time.time()
    final_text = ""
    sources: tuple[Source, ...] = ()
    score = 0.0
    text_parts: list[str] = []

    async for evt in stream_response(state, body.query, manual=body.manual):
        if evt.type == "text":
            text_parts.append(evt.delta)
        elif evt.type == "text_final":
            final_text = evt.text
        elif evt.type == "done":
            sources = evt.sources
            score = evt.score
        yield _serialize_sse(evt)

    latency_ms = int((time.time() - started) * 1000)
    full = final_text if final_text else "".join(text_parts)
    turn_id = store.add_turn(
        config.logs_db_path,
        session_id=body.session_id,
        query=body.query,
        response=full,
        retrieved_sources=list(sources),
        retrieved_score=score,
        latency_ms=latency_ms,
    )
    yield _serialize_sse(ChatEvent(type="turn_id", turn_id=turn_id))
```

(나머지 핸들러는 전부 그대로 — config 모듈 전역을 계속 사용.)

- [ ] **Step 6-4: 테스트 + 커밋**

```bash
.venv/bin/pytest -q   # 예상: 전체 PASS — test_sse 3개가 리팩터링 후에도 동일하게 통과
git add backend.py tests/test_sse.py
git commit -m "refactor(backend): import 부수효과 제거 + SSE 직렬화 단순화

init_schema·RagState 로드를 lifespan 으로 (mutable 전역 _state 제거,
app.state.rag 사용). _serialize_sse 는 asdict 재귀 변환으로 — 출력 포맷은
tests/test_sse.py 로 바이트 고정.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 7: 프런트 분리 — index.html → css/app.css + js/{api,ui,main}.js (S10)

**Files:**
- Create: `static/css/app.css`, `static/js/api.js`, `static/js/ui.js`, `static/js/main.js`
- Modify: `static/index.html`

원칙: **함수 이동 + 모듈 경계가 강제하는 최소 매개변수화만** (전역 `session`/`QNA_BOARD_URL` → main 의 상태로, ui 의 통신은 콜백 주입). 로직·문구·클래스명 변경 금지. CSS 는 무수정 복사.

- [ ] **Step 7-1: CSS 추출 (수정 없이 그대로)**

```bash
mkdir -p static/css static/js
sed -n '11,170p' static/index.html > static/css/app.css
# 검증: <style> 태그가 들어가지 않았는지, 첫 줄이 '  /* ===== Ai-X-Lab' 인지 확인
head -2 static/css/app.css
tail -2 static/css/app.css   # 마지막 줄: .site-footer .copy { ... }
```

- [ ] **Step 7-2: `static/js/api.js` 생성** (컨트롤러 — fetch·SSE 파싱만, DOM 접근 없음)

```js
// 서버 통신 계층: fetch 와 SSE 파싱만 담당한다. DOM 을 만지지 않는다.

export async function fetchHealth() {
  try {
    const r = await fetch("/health");
    return await r.json();
  } catch (e) { return {}; }
}

export async function postConsent(userLabel) {
  const r = await fetch("/consent", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({user_label: userLabel})});
  return r.json();
}

export function postChat(body) {
  return fetch("/chat", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body)});
}

// /chat 응답 본문(SSE)을 이벤트 객체 단위로 흘리는 async generator.
export async function* sseEvents(resp) {
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream: true});
    const lines = buf.split("\n\n");
    buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      yield JSON.parse(line.slice(6));
    }
  }
}

export async function fetchFaqQuestions() {
  try {
    const r = await fetch("/faq");
    if (r.ok) return (await r.json()).questions || [];
  } catch (e) {}
  return [];
}

export async function fetchCatalog() {
  try {
    const r = await fetch("/catalog");
    return r.ok ? ((await r.json()).manuals || []) : [];
  } catch (e) { return []; }
}

export function postFeedback(turnId, rating) {
  return fetch("/feedback", {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({turn_id: turnId, rating}),
  });
}

export function postPurge(sessionId) {
  return fetch("/purge", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({session_id: sessionId})});
}
```

- [ ] **Step 7-3: `static/js/ui.js` 생성** (프레젠테이션 — DOM 생성·렌더만, 통신은 콜백 주입)

```js
// 프레젠테이션 계층: DOM 생성·렌더만 담당한다. 서버 통신 없음(콜백 주입).

export const $ = (s) => document.querySelector(s);

export function escapeHtml(s) { return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

// 답변 텍스트를 렌더한다(평문). 단 게시판 문구('e-Class QnA 게시판', 'Q&A 바로가기'
// 등)는 게시판 하이퍼링크로 건다 — 안내 시 게시판으로 바로 이동할 수 있게.
const QNA_LINK_PHRASES = ["e-Class QnA 게시판", "Q&A 바로가기", "Q&A 게시판"];
export function setAnswerText(el, text, qnaBoardUrl) {
  let html = escapeHtml(text);
  if (qnaBoardUrl) {
    QNA_LINK_PHRASES.forEach(phrase => {
      const a = `<a href="${escapeHtml(qnaBoardUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(phrase)}</a>`;
      html = html.split(escapeHtml(phrase)).join(a);
    });
  }
  el.innerHTML = html;
}

const ICON_PAPERCLIP = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 1 1-8.49-8.49l8.57-8.57A4 4 0 1 1 17.93 8.8L9.41 17.32a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>';
const ICON_DOC = '<svg width="14" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z"/></svg>';
const ICON_THUMBS_UP = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H7V10l4.66-9.32a.5.5 0 0 1 .66-.22l1.06.53a2 2 0 0 1 1.02 2.4L15 5.88Z"/></svg>';
const ICON_THUMBS_DOWN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H17v12l-4.66 9.32a.5.5 0 0 1-.66.22l-1.06-.53a2 2 0 0 1-1.02-2.4L9 18.12Z"/></svg>';

// ── 입력/모달 게이트 ─────────────────────────────────────────────
export function setChatEnabled(enabled) {
  $("#q").disabled = !enabled;
  $("#form button[type=submit]").disabled = !enabled;
}

export function showConsentModal(show) {
  $("#modal").style.display = show ? "flex" : "none";
}

export function setUserLabel(label) { $("#user-label").textContent = label; }

export function focusComposer() { $("#q").focus(); }

export function renderDenied() {
  document.body.innerHTML = "<div style='padding:40px;text-align:center'>동의하지 않으시면 챗봇을 사용하실 수 없습니다.</div>";
}

// ── 대화 턴 ──────────────────────────────────────────────────────
export function appendUserBubble(text) {
  const log = $("#log");
  if (log.querySelector(".empty")) log.innerHTML = "";
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `<div class="q">${escapeHtml(text)}</div>`;
  log.appendChild(div);
}

// 질문 말풍선 + 로딩 점 3개 + 빈 답변/이미지/출처/피드백 영역을 가진 턴 스켈레톤.
export function appendTurnSkeleton(query) {
  const log = $("#log");
  if (log.querySelector(".empty")) log.innerHTML = "";
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `<div class="q">${escapeHtml(query)}</div><div class="a"><span class="loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span></div><div class="imgs"></div><div class="src"></div><div class="fb"></div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  let loadingActive = true;
  const removeLoading = () => {
    if (!loadingActive) return;
    loadingActive = false;
    const a = div.querySelector(".a");
    const l = a.querySelector(".loading");
    if (l) { a.removeChild(l); }
  };
  return {div, removeLoading};
}

export function setAnswerPlain(turnDiv, text) {
  turnDiv.querySelector(".a").textContent = text;
}

export function appendAnswerDelta(turnDiv, delta) {
  turnDiv.querySelector(".a").textContent += delta;
  const log = $("#log");
  log.scrollTop = log.scrollHeight;
}

export function renderImages(turnDiv, images) {
  const imgs = turnDiv.querySelector(".imgs");
  images.forEach(src => {
    const i = document.createElement("img");
    i.src = src;
    i.loading = "lazy";
    i.alt = "";
    // 자산이 없는 경로(404)는 X 박스 대신 자리 제거
    i.onerror = () => i.remove();
    i.onclick = () => openLightbox(src);
    imgs.appendChild(i);
  });
}

export function renderSources(turnDiv, sources) {
  const srcEl = turnDiv.querySelector(".src");
  srcEl.innerHTML = "";
  const h = document.createElement("h4");
  h.innerHTML = ICON_PAPERCLIP + " <span>관련 문서</span>";
  srcEl.appendChild(h);
  const ul = document.createElement("ul");
  sources.forEach(s => {
    const title = typeof s === "string" ? s : (s.title || "");
    const url = typeof s === "object" ? (s.url || "") : "";
    const li = document.createElement("li");
    li.insertAdjacentHTML("beforeend", ICON_DOC);
    if (url) {
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = title;
      li.appendChild(a);
    } else {
      const span = document.createElement("span");
      span.textContent = title;
      li.appendChild(span);
      li.classList.add("no-link");
    }
    ul.appendChild(li);
  });
  srcEl.appendChild(ul);
}

// onRate(turnId, rating) -> Promise — 통신은 호출부(main)가 주입한다.
export function renderFeedback(turnDiv, turnId, onRate) {
  const fb = turnDiv.querySelector(".fb");
  fb.innerHTML = "";
  const q = document.createElement("span");
  q.className = "q";
  q.textContent = "이 응답이 도움이 되었습니까?";
  fb.appendChild(q);
  // "예"(긍정)를 먼저 배치
  [["예", 3, ICON_THUMBS_UP, "yes"], ["아니오", 1, ICON_THUMBS_DOWN, "no"]].forEach(([text, rating, icon, cls]) => {
    const b = document.createElement("button");
    b.className = cls;
    b.innerHTML = icon + " <span>" + text + "</span>";
    b.onclick = () => onRate(turnId, rating).then(() => {
      fb.innerHTML = '<span class="thanks">피드백 감사합니다.</span>';
    });
    fb.appendChild(b);
  });
}

// ── 라이트박스 ───────────────────────────────────────────────────
export function openLightbox(src) {
  const lb = document.getElementById("lightbox");
  document.getElementById("lightbox-img").src = src;
  lb.classList.add("open");
}

export function closeLightbox() {
  document.getElementById("lightbox").classList.remove("open");
  document.getElementById("lightbox-img").src = "";
}

export function initLightbox() {
  document.getElementById("lightbox").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeLightbox();
  });
}

// ── FAQ 칩 / 가이드 네비게이션(3뎁스) ───────────────────────────
export function makeChip(label, cls, onClick, withArrow) {
  const b = document.createElement("button");
  b.className = cls;
  b.type = "button";
  if (withArrow) b.innerHTML = escapeHtml(label) + ' <span class="arrow">›</span>';
  else b.textContent = label;
  b.onclick = onClick;
  return b;
}

export function faqRowOf(questions, onAsk) {
  const row = document.createElement("div");
  row.className = "faq-row";
  questions.forEach(q => row.appendChild(makeChip(q, "faq-chip", () => onAsk(q))));
  return row;
}

// 1뎁스: 매뉴얼별 대분류 칩 섹션(엘리먼트 반환, 데이터 없으면 null).
// onPickCategory(manualName, cat) — 2뎁스 전개는 호출부가 결정.
export function buildCatalogSection(manuals, introText, onPickCategory) {
  if (!manuals.length) return null;
  const sec = document.createElement("div");
  sec.className = "cat-section";
  const intro = document.createElement("p");
  intro.className = "cat-intro";
  intro.textContent = introText;
  sec.appendChild(intro);
  manuals.forEach(m => {
    const block = document.createElement("div");
    block.className = "manual-block";
    const label = document.createElement("span");
    label.className = "manual-label";
    label.textContent = m.title;
    block.appendChild(label);
    const grid = document.createElement("div");
    grid.className = "chip-grid";
    m.categories.forEach(cat =>
      grid.appendChild(makeChip(cat.name, "cat-chip", () => onPickCategory(m.name, cat), true)));
    block.appendChild(grid);
    sec.appendChild(block);
  });
  return sec;
}

// 2뎁스: 선택한 대분류의 하위 문서 칩 블록을 로그에 덧붙인다.
// onAskDoc(docTitle) — 매뉴얼 스코프 결정은 호출부(main) 책임.
export function appendCategoryBlock(cat, onAskDoc) {
  const log = $("#log");
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const intro = document.createElement("p");
  intro.className = "faq-intro";
  intro.textContent = "‘" + cat.name + "’ 관련 안내입니다. 궁금한 항목을 선택해 주세요.";
  wrap.appendChild(intro);
  const row = document.createElement("div");
  row.className = "faq-row";
  cat.docs.forEach(doc => row.appendChild(makeChip(doc, "faq-chip", () => onAskDoc(doc))));
  wrap.appendChild(row);
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

// 첫 진입 화면: 인트로 + 랜덤 FAQ 칩 + (있으면) 가이드 대분류 섹션. 로그를 비우고 채운다.
export function renderEntry(questions, catalogSectionEl, onAsk) {
  const log = $("#log");
  log.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const intro = document.createElement("p");
  intro.className = "faq-intro";
  intro.textContent = "저는 동서대학교 LMS 교수자 가이드를 담당하고 있습니다. 아래와 같은 질문을 주시면 빠르게 답변해 드립니다.";
  wrap.appendChild(intro);
  if (questions.length) wrap.appendChild(faqRowOf(questions, onAsk));
  if (catalogSectionEl) wrap.appendChild(catalogSectionEl);
  log.appendChild(wrap);
}

// "다른 질문 보여줘": 새 랜덤 FAQ 칩 블록을 덧붙인다(대화 유지).
export function appendRerollBlock(questions, onAsk) {
  const log = $("#log");
  const wrap = document.createElement("div");
  wrap.className = "faq";
  const intro = document.createElement("p");
  intro.className = "faq-intro";
  intro.textContent = "다른 추천 질문입니다. 궁금한 것을 선택해 주세요.";
  wrap.appendChild(intro);
  if (questions.length) wrap.appendChild(faqRowOf(questions, onAsk));
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}

// 가이드 언급 시: 안내 가능한 대분류 목록(또는 실패 문구)을 덧붙인다.
export function appendCatalogListBlock(catalogSectionEl) {
  const log = $("#log");
  const wrap = document.createElement("div");
  wrap.className = "faq";
  if (catalogSectionEl) {
    wrap.appendChild(catalogSectionEl);
  } else {
    const p = document.createElement("p");
    p.className = "faq-intro";
    p.textContent = "안내 가능한 가이드 목록을 불러오지 못했습니다.";
    wrap.appendChild(p);
  }
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
}
```

- [ ] **Step 7-4: `static/js/main.js` 생성** (엔트리 — 상태·이벤트 배선·api↔ui 연결)

```js
// 엔트리: 세션 상태(localStorage)·이벤트 바인딩을 소유하고 api(통신)와 ui(렌더)를 잇는다.
import * as api from "./api.js";
import * as ui from "./ui.js";

let session = null;
// 폴백 답변의 'e-Class QnA 게시판' 문구를 하이퍼링크로 걸 때 쓸 게시판 URL(로드 시 1회 조회).
let qnaBoardUrl = "";
api.fetchHealth().then(d => { qnaBoardUrl = d.qna_board_url || ""; });

let catalogCache = null;
async function loadCatalog() {
  if (catalogCache) return catalogCache;
  catalogCache = await api.fetchCatalog();
  return catalogCache;
}

// 2뎁스 전개: CMS 문서는 manual='CMS' 스코프로 보내 LMS 검색에 섞이지 않게
// 한다(LMS 는 자동 라우팅이라 스코프 생략).
function onPickCategory(manualName, cat) {
  const scope = manualName === "LMS" ? undefined : manualName;
  ui.appendCategoryBlock(cat, doc => ask(doc, scope));
}

async function consent(userLabel) {
  const d = await api.postConsent(userLabel);
  session = d.session_id;
  localStorage.setItem("lms_session", session);
  localStorage.setItem("lms_consent", d.consent_version);
  if (userLabel) {
    localStorage.setItem("lms_label", userLabel);
    ui.setUserLabel(userLabel);
  }
  ui.showConsentModal(false);
  ui.setChatEnabled(true);
  ui.focusComposer();
  showFaqSuggestions();
}

async function ask(query, manual) {
  const {div, removeLoading} = ui.appendTurnSkeleton(query);

  const body = {session_id: session, query};
  // 가이드 네비에서 CMS 문서를 누른 경우만 manual='CMS' 로 스코프 전송. LMS/자유
  // 입력은 생략 → 서버가 직접 언급 라우팅(기본 LMS)으로 처리.
  if (manual) body.manual = manual;
  const resp = await api.postChat(body);
  // 세션이 서버에 없으면(컨테이너 재시작·DB 리셋으로 캐시 세션이 만료) 403.
  // 옛 세션을 비우고 동의 모달을 다시 띄워 재동의 → 새 세션을 받게 한다.
  if (resp.status === 403) {
    removeLoading();
    ui.setAnswerPlain(div, "세션이 만료되었습니다. 다시 동의해 주시면 이어서 도와드릴게요.");
    localStorage.removeItem("lms_session");
    localStorage.removeItem("lms_consent");
    session = null;
    ui.showConsentModal(true);
    ui.setChatEnabled(false);
    return;
  }
  if (!resp.ok || !resp.body) {
    removeLoading();
    ui.setAnswerPlain(div, "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
    return;
  }
  for await (const evt of api.sseEvents(resp)) {
    if (evt.type === "text") {
      removeLoading();
      ui.appendAnswerDelta(div, evt.delta);
    } else if (evt.type === "text_final") {
      removeLoading();
      ui.setAnswerText(div.querySelector(".a"), evt.text, qnaBoardUrl);
    } else if (evt.type === "done") {
      removeLoading();
      ui.renderImages(div, evt.images);
      if (evt.sources?.length) ui.renderSources(div, evt.sources);
    } else if (evt.type === "turn_id") {
      ui.renderFeedback(div, evt.turn_id, (tid, rating) => api.postFeedback(tid, rating));
    }
  }
}

// 첫 진입 화면: 랜덤 FAQ 칩 + 가이드 대분류 네비.
async function showFaqSuggestions() {
  const questions = await api.fetchFaqQuestions();
  const sec = ui.buildCatalogSection(
    await loadCatalog(),
    "이외에도 아래 주제들을 안내해 드릴 수 있습니다. 주제를 선택하면 세부 항목을 보여드립니다.",
    onPickCategory);
  if (!questions.length && !sec) return;
  ui.renderEntry(questions, sec, ask);
}

async function appendRerollSuggestions(userText) {
  ui.appendUserBubble(userText);
  const questions = await api.fetchFaqQuestions();
  ui.appendRerollBlock(questions, ask);
}

async function appendCatalogList(userText) {
  ui.appendUserBubble(userText);
  const sec = ui.buildCatalogSection(
    await loadCatalog(),
    "아래와 같은 가이드를 안내해 드릴 수 있습니다. 주제를 선택해 주세요.",
    onPickCategory);
  ui.appendCatalogListBlock(sec);
}

// "다른/또 추천 질문 보여줘" → 랜덤 FAQ 리롤. "가이드/매뉴얼 뭐 있어" → 대분류 목록.
const RE_REROLL = /(다른|또|새|다시)\s*(추천\s*)?질문|질문\s*(다시|더|또)/;
const RE_GUIDE = /(가이드|매뉴얼|메뉴얼)\s*(목록|리스트|종류|항목|뭐|무엇|어떤|있|보여|안내)|(뭐|무슨|어떤|무엇)\s*(가이드|매뉴얼|메뉴얼)|^\s*(가이드|매뉴얼|메뉴얼)\s*$/;

ui.$("#form").addEventListener("submit", e => {
  e.preventDefault();
  const q = ui.$("#q").value.trim();
  if (!q) return;
  ui.$("#q").value = "";
  if (RE_REROLL.test(q)) { appendRerollSuggestions(q); return; }
  if (RE_GUIDE.test(q)) { appendCatalogList(q); return; }
  ask(q);
});

ui.$("#agree").addEventListener("click", e => { e.preventDefault(); consent(null); });
ui.$("#deny").addEventListener("click", e => { e.preventDefault(); ui.renderDenied(); });
ui.$("#purge").addEventListener("click", async e => {
  e.preventDefault();
  if (!session) return;
  if (!confirm("이 세션의 대화 기록을 모두 삭제하고 동의를 철회합니다. 진행할까요?")) return;
  await api.postPurge(session);
  localStorage.removeItem("lms_session");
  localStorage.removeItem("lms_consent");
  localStorage.removeItem("lms_label");
  location.reload();
});

ui.initLightbox();

const saved = localStorage.getItem("lms_session");
const savedConsent = localStorage.getItem("lms_consent");
if (saved && savedConsent) {
  session = saved;
  ui.showConsentModal(false);
  ui.setChatEnabled(true);
  const lbl = localStorage.getItem("lms_label");
  if (lbl) ui.setUserLabel(lbl);
  showFaqSuggestions();
}
```

- [ ] **Step 7-5: `static/index.html` 교체** — 전체를 다음 내용으로 (마크업 본문은 기존과 동일, style/script 만 외부화):

```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LMS 챗봇</title>
<!-- 테마 폰트: Pretendard (Ai-X-Lab 디자인 테마) -->
<link rel="stylesheet" as="style" crossorigin
      href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<link rel="stylesheet" href="/static/css/app.css">
</head>
<body>
<div class="topbar"></div>
<div class="wrap">
  <div class="top">
    <h1><img src="https://eclass1.dongseo.ac.kr/customs/main/xnds_header_logo.png" alt="동서대학교 e-Class LMS 챗봇"></h1>
    <span class="label" id="user-label"></span>
  </div>
  <div class="log" id="log"><p class="empty">질문을 입력하시면 가이드 내용을 바탕으로 답변드리겠습니다.</p></div>
  <form class="input" id="form">
    <input id="q" placeholder="질문을 입력하십시오" autocomplete="off" disabled>
    <button class="primary" type="submit" disabled>전송</button>
  </form>
  <footer class="site-footer">
    <p class="links">
      <a href="/privacy" target="_blank">개인정보처리방침</a>
      &nbsp;·&nbsp;
      <a href="#" id="purge">대화 기록 삭제 및 동의 철회</a>
    </p>
    <p class="copy">동서대학교 교육혁신처 · COPYRIGHT © 2026 DONGSEO UNIVERSITY. ALL RIGHTS RESERVED.</p>
  </footer>
</div>

<div id="lightbox"><img id="lightbox-img" alt=""><span class="hint">아무 곳이나 클릭하거나 ESC 키를 눌러 닫기</span></div>

<div class="modal-bg" id="modal">
  <div class="modal">
    <h2>개인정보 수집 및 이용 동의</h2>
    <section><h3>수집 항목</h3><p>질의 본문, 응답 본문, 응답 시각, 피드백 점수와 코멘트</p></section>
    <section><h3>수집 목적</h3><p>가이드북 업데이트 우선순위 도출 및 챗봇 응답 품질 모니터링</p></section>
    <section><h3>보유 기간</h3><p>수집일로부터 6개월. 동의 철회 시 즉시 삭제</p></section>
    <section><h3>동의 철회 방법</h3><p>화면 하단의 "대화 기록 삭제 및 동의 철회" 링크를 누르면 즉시 삭제됩니다</p></section>
    <div class="accent">본 대화 내용은 모델 학습에 사용되지 않습니다.</div>
    <div class="accent">외부 제3자에게 제공되지 않습니다 (모든 처리는 로컬에서 이루어집니다).</div>
    <p style="font-size:12px;color:#57606a;margin:8px 0 0">보호책임자: 김강민 · 문의: 동서대학교 교육혁신처 교수학습개발센터 · <a href="/privacy" target="_blank">처리방침 전문</a></p>
    <div class="actions">
      <button id="deny">동의 안 함</button>
      <button class="primary" id="agree">동의하고 시작</button>
    </div>
  </div>
</div>
<script type="module" src="/static/js/main.js"></script>
</body>
</html>
```

- [ ] **Step 7-6: 서빙 + 브라우저 검증**

```bash
.venv/bin/pytest -q     # 백엔드 무영향 확인
.venv/bin/python -m uvicorn backend:app --port 8080   # 백그라운드, /health 200 대기
curl -sI http://localhost:8080/static/css/app.css | head -1   # HTTP/1.1 200
curl -sI http://localhost:8080/static/js/main.js | head -1    # HTTP/1.1 200
```

브라우저(또는 playwright)로 http://localhost:8080 전 플로우 확인 체크리스트:
1. 동의 모달 표시 → "동의하고 시작" → 모달 닫힘 + 입력 활성 + FAQ 칩/가이드 대분류 노출
2. FAQ 칩 클릭 → 질문 말풍선 + 로딩 점 → 스트리밍/직출력 답변
3. 답변에 이미지·관련 문서 노출 (이미지 클릭 → 라이트박스, ESC 닫힘)
4. 피드백 "예" 클릭 → "피드백 감사합니다."
5. "다른 질문 보여줘" 입력 → 리롤 블록. "가이드 뭐 있어" → 대분류 목록
6. 대분류 칩 → 하위 문서 칩 → 클릭 시 질문 전송 (CMS 문서가 있으면 CMS 칩에서 답변이 CMS 문서로)
7. 새로고침 → 모달 없이 바로 사용 가능(세션 복원). "대화 기록 삭제 및 동의 철회" → confirm → 리로드 후 모달 재등장
8. 콘솔에 JS 에러 0건

- [ ] **Step 7-7: 커밋**

```bash
git add static/index.html static/css/app.css static/js/api.js static/js/ui.js static/js/main.js
git commit -m "refactor(web): index.html 모놀리스를 css + ES 모듈(api/ui/main)로 분리

api.js(통신)·ui.js(DOM 렌더)·main.js(상태·배선) — 빌드 스텝 없는 브라우저
네이티브 모듈. 마크업·스타일·동작 동일.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 8: 문서 동기화 — AGENT.md 현행화 (S11)

**Files:**
- Modify: `AGENT.md` (README.md 는 확인 결과 구조 서술이 없어 무변경)

- [ ] **Step 8-1: AGENT.md 수정** — 다음 4곳:

(1) 검색 정책 섹션 — 상수 출처와 게이트 현행화. 기존:
```
- 하이브리드 점수: `BM25_norm * 0.4 + embed_sim * 0.6`. top-5 가 LLM 컨텍스트로 들어감.
- 임계값(현재 0.25, 정성 평가 후 조정): 1위 점수가 미만이면 LLM 호출 안 함.
```
교체:
```
- 하이브리드 점수: `BM25_norm * 0.4 + embed_sim * 0.6`. 점수 1위 문서의 청크만 최대 5개가 LLM 컨텍스트로 들어감 (1 질문 : 1 문서).
- 검색·게이트·LLM 옵션의 모든 수치는 `tuning.py` 에서 단일 관리 (실측 근거 주석 포함).
- 게이트 순서: 메타 질문 가드 → 임베딩 절대 바닥(ABS_EMBED_FLOOR)·정규화 임계(SCORE_THRESHOLD) → 애매 구간(< ABS_EMBED_CONFIDENT)만 LLM 관련성 게이트 → FAQ 문서면 원문 직출력, 가이드 문서면 LLM 생성.
```

(2) 이미지 동반 정책 섹션 — 기존 3줄 전체 교체:
```
- 응답은 SSE 이벤트 스트림: `text`(델타) → `text_final`(정제 전문) → `done`(images, sources, score) → `turn_id`.
- 이미지: 답변에 쓴 1순위 문서의 전 섹션 `image_refs` 를 seq 순으로 최대 5장(`tuning.MAX_IMAGES`). 조회 실패 시 컨텍스트 청크 이미지로 폴백. 폴백 답변에는 이미지·출처를 붙이지 않음.
- 출처: 1 질문 : 1 문서 — 문서 단위 제목·노션 링크 한 건만 노출 ('FAQ —' 접두 문서는 제외).
```

(3) 개발 워크플로 섹션 — `generation/pipeline.py` 참조 수정. 기존:
```
- 모델 교체: `.env` 의 `OLLAMA_MODEL` 변경. `generation/pipeline.py` 코드 수정 불필요.
```
교체:
```
- 모델 교체: `.env` 의 `OLLAMA_MODEL` 변경. 코드 수정 불필요 (`generation/stream.py` 는 RagState 경유로만 모델명을 받음).
- 품질 튜닝(임계값·가중치·LLM 옵션): `tuning.py` 만 수정.
```

(4) 디렉터리 맵 섹션 — 전체 교체:
```
- `config.py` 배포 환경 설정 (env 단일 진입점, AppConfig)
- `tuning.py` 품질 튜닝 노브 단일 관리 (임계값·가중치·LLM 옵션)
- `app_types.py` 횡단 데이터 타입 (Chunk, Retrieval, ChatEvent …)
- `ingest/` 정제된 청크까지. 임베딩은 하지 않음
- `index/` 임베딩 + BM25 인덱스 빌드/저장
- `retrieval/` 인덱스에서 검색만 (hybrid_search, doc_image_refs)
- `generation/` 검색 결과 + LLM 결합 + 후처리 (ollama.py 가 HTTP 클라이언트)
- `rag/` RagState 정의·로드 (서버가 기동 시 1회)
- `db/` SQLite 스키마와 DAO
- `qa/` QA 러너 (devtools-qa-runner 서브모듈) + 프로파일
- `backend.py` FastAPI 얇은 wrapper
- `static/` index.html(마크업) + css/app.css + js/{api,ui,main}.js (통신/렌더/배선)
- `docs/` spec, plans, privacy
- `tests/` 순수 함수 위주 pytest
```

- [ ] **Step 8-2: 테스트 + 커밋**

```bash
.venv/bin/pytest -q   # 문서만 변경 — 그린 확인은 형식적
git add AGENT.md
git commit -m "docs(agent): AGENT.md 현행화 — tuning.py·게이트 순서·이미지 정책·디렉터리 맵

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 9: 통합 스모크 (커밋 없음 — 검증만)

- [ ] **Step 9-1: 전체 테스트 + 서버 기동**

```bash
.venv/bin/pytest -q                  # 전체 PASS
.venv/bin/python -m uvicorn backend:app --port 8080   # 백그라운드
```

- [ ] **Step 9-2: 엔드포인트 스모크**

```bash
curl -s http://localhost:8080/health          # ok:true + consent_version + qna_board_url
curl -s http://localhost:8080/faq             # questions 5~7개
curl -s "http://localhost:8080/faq?n=3"       # questions 3개
curl -s http://localhost:8080/catalog | head -c 400   # manuals[].categories[].docs
.venv/bin/python -m retrieval.cli "퀴즈 출제하는 방법"   # top-5 점수·제목 출력
```

- [ ] **Step 9-3: 채팅 1턴 E2E** (ollama 필요)

```bash
SID=$(curl -s -X POST http://localhost:8080/consent -H 'content-type: application/json' -d '{}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])')
curl -sN -X POST http://localhost:8080/chat -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"query\":\"퀴즈 출제하는 방법\"}" | head -40
```
예상: `data: {"type": "text", ...}` 스트림 → `text_final` → `done`(images/sources) → `turn_id`. 폴백 확인: query 를 "오늘 날씨 어때" 로 바꾸면 QnA 안내 문구 + done(score) 만.

---

## Task 10: QA 러너 회귀 — 베이스라인 비교 (커밋 없음 — 검증만)

- [ ] **Step 10-1: 동일 프로파일 재실행** (서버·ollama 기동 상태에서)

```bash
npm run qa:paraphrase && npm run qa:paraphrase:judge
npm run qa:adversarial && npm run qa:adversarial:judge
```

- [ ] **Step 10-2: 전/후 비교**

`reports/baseline-faq-paraphrase` vs `reports/faq-paraphrase`, `reports/baseline-faq-adversarial` vs `reports/faq-adversarial` 의 judge 요약(통과/실패 건수·실패 케이스 목록)을 비교한다.

판정 기준:
- FAQ 직출력 경로(결정적): 답변 본문이 베이스라인과 동일해야 함 — 다르면 **회귀, 원인 커밋을 bisect**
- LLM 생성 경로: temperature 0.2 비결정성 감안, judge 판정(통과/실패) 수준에서 베이스라인과 동등 이상이어야 함. 1~2건 차이는 같은 케이스 3회 재실행으로 흔들림 여부 확인
- adversarial(가드레일): 차단율 베이스라인과 동일해야 함 (가드레일 코드는 무변경 — 다르면 회귀)

- [ ] **Step 10-3: 결과 보고**

전/후 비교 표(프로파일별 통과/실패)와 결론을 사용자에게 보고. 회귀 발견 시 해당 커밋 특정 → 수정 → Task 9~10 재실행.

---

## 완료 후

superpowers:finishing-a-development-branch 스킬로 마무리 (머지/PR/보류 — 사용자 선택). 스펙 문서의 상태 라인을 "구현 완료"로 갱신하는 것도 잊지 말 것.

## 계획 자체의 검증 노트 (작성 시 확인 완료)

- 이동 심볼의 전체 사용처 grep 완료: `_derive_title`(pipeline.py:12,49 / catalog.py:156,172), `ENTRY_MIN/MAX`(test_faq), stream 상수 4종(test_stream), `_faq_answer`/`_qna_fallback_msg`(test_stream) — 본 계획의 갱신 목록과 일치
- 순환 import 없음: tuning(잎) ← 모두, persona ← stream, faq ← stream (faq 는 stream 을 import 하지 않음), preprocess ← chunk/catalog
- `asdict` 직렬화 동등성: 현 수동 변환과 키 순서(필드 순서)·tuple→배열 변환 동일 — test_sse 로 바이트 고정
- 프런트: 인라인 `onclick` 마크업 없음(전수 확인) — ES 모듈 전환 안전. `<script>` 가 body 끝 → `type="module"`(defer)와 실행 시점 동등
- index.html 의 `escape()` → `escapeHtml()` rename 은 모듈 내부 일관 적용 (전역 충돌 아님, 가독성 목적)
- Task 2에서 catalog 가 ingest.chunk 를 모듈 상단 import → pandas 로드가 첫 /catalog 호출 시점에서 서버 기동 시점으로 당겨짐. RagState 로드(10~20초)에 비해 무시 가능하고 외부 동작 동일
