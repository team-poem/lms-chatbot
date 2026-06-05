# 매뉴얼 전용 답변 + QnA 폴백 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 말투·표현 강건성 라우팅을 제거하고, 매뉴얼에 근거가 있는 질문만 답하며 그 외에는 QnA 게시판으로 안내한다.

**Architecture:** 라우팅을 "메타 거절 → 검색 게이트 → (근거 있으면) 생성 / (없으면) QnA 안내"로 단순화한다. QnA 링크는 설정값(QNA_BOARD_URL)으로 주입하고, RagState가 운반한다. 인사·범위·역량·구어체 처리 코드는 제거한다(기능은 백업본에 보존).

**Tech Stack:** Python 3.11, pytest. 테스트는 `.venv/bin/python -m pytest` 로 실행(시스템 python3엔 pandas/httpx 없음).

---

## 파일 구조

- `config.py` — `QNA_BOARD_URL` 설정 추가
- `rag/state.py` — `RagState.qna_board_url` 추가 (config에서 주입)
- `generation/stream.py` — 라우팅 단순화, `_qna_fallback_msg` 헬퍼, `NO_GUIDE_MSG`·social/help/scope/topic 분기 제거
- `generation/guardrail.py` — social/scope/help 술어·정규식·`SOCIAL_REPLY` 제거 (메타 유지)
- `generation/suggestions.py` — 파일 삭제 (stream.py 외 사용처 없음)
- `docker-compose.yml` — `QNA_BOARD_URL` 환경변수 전달
- 테스트: `tests/test_config.py`(신규), `tests/test_stream.py`(수정), `tests/test_suggestions.py`·`tests/test_social.py`(삭제)

---

## Task 1: QNA_BOARD_URL 설정과 RagState 운반

**Files:**
- Modify: `config.py` (AppConfig, load_config)
- Modify: `rag/state.py` (RagState, load_rag_state)
- Modify: `docker-compose.yml` (environment)
- Test: `tests/test_config.py` (신규)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
from rag.state import RagState
from config import load_config


def test_qna_board_url_from_env(monkeypatch):
    monkeypatch.setenv("QNA_BOARD_URL", "https://qna.example.edu/board")
    assert load_config().qna_board_url == "https://qna.example.edu/board"


def test_qna_board_url_defaults_empty(monkeypatch):
    monkeypatch.delenv("QNA_BOARD_URL", raising=False)
    # .env 에 QNA_BOARD_URL 이 없다는 전제(현재 레포 상태). load_dotenv 는 기존 env 를
    # 덮어쓰지 않으므로 미설정이면 빈 문자열.
    assert load_config().qna_board_url == ""


def test_ragstate_carries_qna_url():
    st = RagState(
        embedder=None, chroma=None, bm25=None,
        ollama_host="h", ollama_model="m", qna_board_url="u",
    )
    assert st.qna_board_url == "u"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'qna_board_url'` (AppConfig/RagState).

- [ ] **Step 3: Add field to AppConfig and read env**

In `config.py`, add a field to `AppConfig` after `admin_token`:

```python
@dataclass(frozen=True)
class AppConfig:
    ollama_host: str
    ollama_model: str
    embed_model: str
    chroma_dir: Path
    bm25_path: Path
    logs_db_path: Path
    assets_dir: Path
    raw_dir: Path
    port: int
    admin_token: str | None = None
    qna_board_url: str = ""
```

In `load_config()`, add the env read inside the `AppConfig(...)` call (after the admin_token line):

```python
        admin_token=os.environ.get("ADMIN_TOKEN") or None,
        # 매뉴얼에 근거 없는 질문을 안내할 QnA 게시판 URL. 비우면 링크 없이 안내.
        qna_board_url=os.environ.get("QNA_BOARD_URL", ""),
    )
```

- [ ] **Step 4: Add field to RagState and pass it through**

In `rag/state.py`, add a field to `RagState` (with default for safe construction):

```python
@dataclass(frozen=True)
class RagState:
    embedder: SentenceTransformer
    chroma: object  # chromadb.api.ClientAPI — 외부 타입 직접 노출 회피
    bm25: BM25Pack
    ollama_host: str
    ollama_model: str
    qna_board_url: str = ""
```

In `load_rag_state`, pass it from config:

```python
def load_rag_state(config: AppConfig) -> RagState:
    return RagState(
        embedder=load_embedder(config.embed_model),
        chroma=get_chroma_client(config.chroma_dir),
        bm25=load_bm25(config.bm25_path),
        ollama_host=config.ollama_host,
        ollama_model=config.ollama_model,
        qna_board_url=config.qna_board_url,
    )
```

- [ ] **Step 5: Wire docker-compose env**

In `docker-compose.yml`, under `environment:`, add after the `ADMIN_TOKEN` line:

```yaml
      ADMIN_TOKEN: ${ADMIN_TOKEN:-}
      # 매뉴얼에 근거 없는 질문 안내용 QnA 게시판 URL
      QNA_BOARD_URL: ${QNA_BOARD_URL:-}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (3 tests)

Also run full suite (should still pass — nothing else changed yet):
Run: `.venv/bin/python -m pytest -q`

- [ ] **Step 7: Commit**

```bash
git add config.py rag/state.py docker-compose.yml tests/test_config.py
git commit -m "feat(config): QNA_BOARD_URL 설정과 RagState 운반

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 라우팅 단순화 + QnA 폴백 (stream.py)

**Files:**
- Modify: `generation/stream.py` (imports, NO_GUIDE_MSG→QnA helper, stream_response 라우팅)
- Test: `tests/test_stream.py`

- [ ] **Step 1: Update the tests first (TDD)**

In `tests/test_stream.py`:

(a) Add the QnA helper import and pure-function tests. Add near the top imports block (the file already imports from generation.stream):

```python
from generation.stream import _qna_fallback_msg


def test_qna_fallback_msg_with_url():
    msg = _qna_fallback_msg("https://qna.test/board")
    assert "QnA 게시판" in msg
    assert "https://qna.test/board" in msg


def test_qna_fallback_msg_without_url():
    msg = _qna_fallback_msg("")
    assert "QnA 게시판" in msg
    assert "http" not in msg  # 링크 없이 안내
```

(b) Replace the `_finals` helper so it accepts a state (default None for meta-only paths):

```python
def _finals(query, state=None):
    async def run():
        out = []
        async for ev in stream_mod.stream_response(state, query):
            if ev.type == "text_final":
                out.append(ev.text)
        return out
    return asyncio.run(run())
```

(c) DELETE these now-obsolete tests entirely (they test removed routing):
- `test_help_request_short_circuits_before_retrieval`
- `test_topic_declaration_short_circuits_before_retrieval`
- `test_scope_question_short_circuits_to_social`
- `test_low_grounding_in_scope_topic_falls_back_to_topic_guide`

(d) REPLACE `test_real_question_falls_through_to_gate` with a QnA-fallback routing test:

```python
def test_low_grounding_routes_to_qna(monkeypatch):
    # 근거 미달(매뉴얼에 없음)이면 답을 만들지 않고 QnA 게시판으로 안내한다.
    from types import SimpleNamespace
    low = Retrieval(items=(), top_score=0.0, max_embed_sim=0.0)
    monkeypatch.setattr(stream_mod, "hybrid_search", lambda state, q: low)
    state = SimpleNamespace(qna_board_url="https://qna.test/board")
    finals = _finals("오늘 점심 뭐 먹지?", state)
    assert finals and "QnA 게시판" in finals[0]
    assert "https://qna.test/board" in finals[0]


def test_meta_question_still_refused(monkeypatch):
    # 메타 질문은 검색 전에 거절(유지).
    def boom(state, q):
        raise AssertionError("retrieval must not run for meta questions")
    monkeypatch.setattr(stream_mod, "hybrid_search", boom)
    finals = _finals("어떤 모델을 사용하나요?")
    assert finals and "LMS 사용법 안내만 제공" in finals[0]
```

- [ ] **Step 2: Run the updated tests to verify the new ones fail**

Run: `.venv/bin/python -m pytest tests/test_stream.py -k "qna or low_grounding_routes or meta_question_still" -v`
Expected: FAIL — `_qna_fallback_msg` not importable; routing not yet changed.

- [ ] **Step 3: Simplify stream.py imports**

In `generation/stream.py`, replace the guardrail+suggestions import block (currently importing META_REPLY, SOCIAL_REPLY, is_help_request, is_meta_question, is_scope_question, is_social_chitchat, and the whole suggestions import) with just:

```python
from generation.guardrail import META_REPLY, is_meta_question
```

(Delete the entire `from generation.suggestions import (...)` block.)

- [ ] **Step 4: Replace NO_GUIDE_MSG with the QnA helper**

In `generation/stream.py`, delete the `NO_GUIDE_MSG = (...)` constant and add the helper in its place:

```python
def _qna_fallback_msg(qna_board_url: str) -> str:
    """매뉴얼에서 근거를 못 찾은 질문에 대한 안내. URL 이 있으면 링크를 덧붙인다."""
    base = "해당 내용은 매뉴얼에서 확인되지 않습니다. 자세한 문의는 QnA 게시판을 이용해 주세요"
    return f"{base}: {qna_board_url}" if qna_board_url else f"{base}."
```

- [ ] **Step 5: Rewrite the routing in stream_response**

In `generation/stream.py`, replace everything from the start of `stream_response` down to the end of the grounding-gate block (the meta branch, the help branch, the social/scope branch, the match_topic branch, and the `if retrieval.max_embed_sim < ... :` block with topic_for_fallback) with this:

```python
async def stream_response(state: RagState, query: str) -> AsyncIterator[ChatEvent]:
    if is_meta_question(query):
        yield ChatEvent(type="text", delta=META_REPLY)
        yield ChatEvent(type="text_final", text=META_REPLY)
        yield ChatEvent(type="done")
        return

    retrieval = hybrid_search(state, query)
    top_score = retrieval.top_score
    # 매뉴얼에 근거가 없으면(off-topic·거짓 전제·짧거나 모호한 질문 포함) 답을 만들지
    # 않고 QnA 게시판으로 안내한다. 절대 임베딩 유사도 + (정규화)점수 중 하나라도 바닥
    # 미달이면 폴백. 인사·범위·역량 입력도 여기로 떨어진다(말투 대응은 목표가 아님).
    if retrieval.max_embed_sim < ABS_EMBED_FLOOR or top_score < SCORE_THRESHOLD:
        msg = _qna_fallback_msg(state.qna_board_url)
        yield ChatEvent(type="text", delta=msg)
        yield ChatEvent(type="text_final", text=msg)
        yield ChatEvent(type="done", score=top_score)
        return
```

(Everything AFTER this — the `# 컨텍스트:` block building `relevant`, `build_prompt`, the generation loop, `_section_images`, sources, and the final `done` yield — stays exactly as-is.)

- [ ] **Step 6: Run the stream tests and full suite**

Run: `.venv/bin/python -m pytest tests/test_stream.py -v`
Expected: PASS (the new QnA/meta tests pass; deleted tests are gone).

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. (tests/test_social.py and tests/test_suggestions.py still pass here because guardrail/suggestions code is removed in Task 3.)

- [ ] **Step 7: Commit**

```bash
git add generation/stream.py tests/test_stream.py
git commit -m "feat(stream): 매뉴얼 근거 없으면 QnA 안내, 말투 라우팅 제거

메타 거절 → 검색 게이트 → (근거 있음) 생성 / (없음) QnA 게시판 안내로 단순화.
인사·범위·역량·구어체 분기와 topic 폴백 제거. 이미지 섹션 격리는 유지.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 죽은 코드 제거 (guardrail / suggestions / 테스트)

**Files:**
- Modify: `generation/guardrail.py` (social/scope/help 제거, 메타 유지)
- Delete: `generation/suggestions.py`
- Delete: `tests/test_suggestions.py`, `tests/test_social.py`

- [ ] **Step 1: Confirm no remaining importers (safety check)**

Run:
```bash
grep -rln "is_social_chitchat\|is_scope_question\|is_help_request\|SOCIAL_REPLY\|generation.suggestions\|generation import suggestions\|build_help_reply\|build_topic_reply\|match_topic\|topic_for_fallback" --include="*.py" . | grep -v "/.venv/"
```
Expected: only `generation/guardrail.py`, `generation/suggestions.py`, `tests/test_social.py`, `tests/test_suggestions.py` (all of which this task removes/edits). If any other .py file appears, STOP and report — a consumer was missed.

- [ ] **Step 2: Remove dead predicates from guardrail.py**

In `generation/guardrail.py`, delete everything from the `SOCIAL_REPLY = (...)` definition (the block beginning with the comment "인사·감사·작별·역량 문의 같은 선의의 소셜 입력") through the end of the file (i.e., remove `SOCIAL_REPLY`, `_SOCIAL_SHORT`, `_SOCIAL_SHORT_RES`, `_QUESTION_HINT`, `_SOCIAL_MAX_LEN`, `is_social_chitchat`, `_HELP_PATTERNS`, `_HELP_RES`, `is_help_request`, `_SCOPE_SUBJECT`, `_SCOPE_ABOUT`, `_SCOPE_CONCRETE`, `is_scope_question`).

Keep everything above it: the module docstring, `META_REPLY`, `_META_PATTERNS`, `_META_RES`, and `is_meta_question`. The file should end right after the `is_meta_question` function (return False).

- [ ] **Step 3: Delete the suggestions module and its test**

Run:
```bash
git rm generation/suggestions.py tests/test_suggestions.py
```

- [ ] **Step 4: Delete the social/scope/help test file**

`tests/test_social.py` tests only the removed predicates (social/scope/help). Meta-question coverage already lives in `tests/test_guardrail.py` (7 tests covering model/identity/prompt-extraction/usage). Remove the file:

```bash
git rm tests/test_social.py
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, with the import-error risk gone. Confirm no test references a removed symbol (collection succeeds).

- [ ] **Step 6: Commit**

```bash
git add generation/guardrail.py
git commit -m "refactor(guardrail): 말투·범위·역량 술어와 토픽 택소노미 제거

매뉴얼 전용 + QnA 폴백 방향에 따라 social/scope/help 술어, SOCIAL_REPLY,
suggestions 모듈, 관련 테스트 삭제. 메타 거절은 유지(test_guardrail 로 커버).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 검증 (전체 테스트 + 라이브 스모크)

**Files:** 없음(검증 전용)

- [ ] **Step 1: 전체 테스트 통과 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 전부 PASS. test_social/test_suggestions 가 사라지고 test_config 가 추가된 상태.

- [ ] **Step 2: 서버 기동**

Run(백그라운드): `QNA_BOARD_URL="https://lms.dongseo.ac.kr/qna" .venv/bin/python -m uvicorn backend:app --host 0.0.0.0 --port 8080`
대기: `until curl -fsS http://localhost:8080/health >/dev/null 2>&1; do sleep 1; done`

- [ ] **Step 3: 라이브 스모크 (3가지 경로)**

Run:
```bash
python3 - <<'PY'
import json, urllib.request
BASE="http://localhost:8080"
sid=json.load(urllib.request.urlopen(urllib.request.Request(
    BASE+"/consent", data=json.dumps({"user_label":"smoke"}).encode(),
    headers={"Content-Type":"application/json"})))["session_id"]
def ask(q):
    req=urllib.request.Request(BASE+"/chat",
        data=json.dumps({"session_id":sid,"query":q}).encode(),
        headers={"Content-Type":"application/json"})
    t=None
    for raw in urllib.request.urlopen(req, timeout=200):
        line=raw.decode("utf-8","replace").strip()
        if line.startswith("data:"):
            e=json.loads(line[5:].strip())
            if e.get("type")=="text_final": t=e.get("text")
    return t
print("매뉴얼 답변:", (ask("전자출결은 어떻게 하나요?") or "")[:60])
print("비답변(오프토픽):", ask("오늘 점심 뭐 먹지?"))
print("메타:", ask("어떤 모델 쓰나요?"))
PY
```
Expected:
- 매뉴얼 질문 → 실제 절차 답변
- 오프토픽 → "QnA 게시판" 안내 + 링크(https://lms.dongseo.ac.kr/qna)
- 메타 → "LMS 사용법 안내만 제공" 거절

- [ ] **Step 4: 서버 종료**

Run: `lsof -ti:8080 | xargs kill 2>/dev/null`

- [ ] **Step 5: 마무리 보고**

세 경로(매뉴얼 답변 / QnA 폴백 / 메타 거절)가 의도대로 동작함을 요약. 회귀 발견 시 systematic-debugging 으로 분리.

---

## 비고

- QA 하니스 재설계(기존 social/scope/paraphrase/conversation 프로파일 대체)는 이 계획 범위 밖. 별도 spec/plan 으로 진행한다.
- 기존 말투 강건성 기능은 백업본(lms-chatbot-backup-2026-06-05)과 태그 `backup-2026-06-05-before-pivot` 에 보존돼 있다.
