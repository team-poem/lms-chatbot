# FAQ 도움말·질문 가이드(과잉 거절 해소 2차) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 역량/가이드 문의는 카테고리+예시 질문으로 전체 안내하고, 범위 내 주제 선언은 해당 주제 예시로 좁혀 안내한다. 임베딩 게이트는 건드리지 않는다.

**Architecture:** retrieval 게이트 *이전*에 동작하는 결정적(정규식) 사전 분기를 2개 추가한다. 토픽 택소노미를 신규 `generation/suggestions.py`에 단일 출처로 두고, 전체 도움말·주제별 안내를 같은 데이터에서 렌더한다. 역량 문의는 social(짧은 인사)에서 떼어 help(리치 리스트업)로 승격한다.

**Tech Stack:** Python 3.11+, dataclasses, `re`, pytest (asyncio 마커 없음 → `asyncio.run()`으로 비동기 제너레이터 구동).

**스펙:** `docs/superpowers/specs/2026-06-02-faq-help-suggestions-design.md`

---

## File Structure

| 파일 | 역할 | 변경 |
|------|------|------|
| `generation/suggestions.py` | 토픽 택소노미 + `build_help_reply()` + `build_topic_reply()` + `match_topic()` | **신규** |
| `generation/guardrail.py` | `is_help_request()` 추가, `is_social_chitchat`에서 역량 패턴 제거 | 수정 |
| `generation/stream.py` | 라우팅 분기 2개 추가(게이트 로직 불변) | 수정 |
| `tests/test_suggestions.py` | suggestions 단위 테스트 | **신규** |
| `tests/test_social.py` | help/social 분리 반영 | 수정 |
| `tests/test_stream.py` | 라우팅 단락(short-circuit) 테스트 | 수정 |

**불변(변경 금지):** `ABS_EMBED_FLOOR`, 게이트 조건, `generation/persona.py`, `SOCIAL_REPLY`·`NO_GUIDE_MSG` 텍스트, `is_meta_question`.

---

## Task 1: suggestions.py — 토픽 택소노미 + `build_help_reply()`

**Files:**
- Create: `generation/suggestions.py`
- Test: `tests/test_suggestions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_suggestions.py`:

```python
from __future__ import annotations

from generation.suggestions import build_help_reply


def test_help_reply_lists_all_categories():
    reply = build_help_reply()
    for name in ("강의 운영", "과제·평가", "퀴즈·시험", "출결", "성적", "수강생·알림"):
        assert name in reply


def test_help_reply_contains_example_questions_in_quotes():
    reply = build_help_reply()
    # 6개 카테고리 × 2개 예시 × 양끝 따옴표 = 24개 이상
    assert reply.count('"') >= 24


def test_help_reply_has_invitation_footer():
    reply = build_help_reply()
    assert "질문" in reply  # 마무리 유도 문구
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_suggestions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'generation.suggestions'`

- [ ] **Step 3: Write minimal implementation**

Create `generation/suggestions.py`:

```python
"""역량/가이드 문의·범위 내 주제 선언에 대한 안내 응답.

retrieval 게이트 *이전*의 결정적 사전 분기에서 사용한다. 토픽 택소노미를 단일
출처(_TOPICS)로 두고, 전체 도움말(build_help_reply)과 주제별 안내(build_topic_reply)를
같은 데이터에서 렌더한다. FAQ 가 바뀌면 이 파일의 _TOPICS 만 고치면 된다.
"""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    emoji: str
    name: str
    keywords: tuple[str, ...]   # match_topic(주제 선언) 감지용
    examples: tuple[str, ...]   # 사용자에게 보여줄 예시 질문


_TOPICS: tuple[Topic, ...] = (
    Topic("📚", "강의 운영",
          ("강의 운영", "강의운영", "주차학습", "과목 복사", "과목복사", "수업계획서", "콘텐츠"),
          ("지난 학기 과목을 복사하려면 어떻게 하나요?", "주차학습에 강의를 어떻게 등록하나요?")),
    Topic("📝", "과제·평가",
          ("과제",),
          ("과제 점수가 학생에게 안 보여요", "과제 일괄 다운로드가 안 돼요")),
    Topic("🧪", "퀴즈·시험",
          ("퀴즈", "시험", "문제은행", "응시"),
          ("퀴즈가 자동으로 제출됐어요", "시험 후 특정 학생에게 재응시를 줄 수 있나요?")),
    Topic("✅", "출결",
          ("출석", "출결", "전자출결"),
          ("출석했는데 결석으로 처리됐어요", "전자출결은 어떻게 하나요?")),
    Topic("🏅", "성적",
          ("성적", "채점", "평가", "점수"),
          ("재채점 옵션이 보이지 않아요", "대면시험 점수를 LMS로 알려줄 수 있나요?")),
    Topic("👥", "수강생·알림",
          ("수강생", "수강신청", "알림", "공지"),
          ("수강신청했는데 과목에 학생이 없어요", "앱 푸시 알림이 안 와요")),
)


def _render_topic(t: Topic) -> str:
    lines = [f"{t.emoji} {t.name}"]
    lines += [f'  · "{ex}"' for ex in t.examples]
    return "\n".join(lines)


def build_help_reply() -> str:
    """역량/가이드 문의 응답: 전체 카테고리 + 예시 리스트업."""
    body = "\n".join(_render_topic(t) for t in _TOPICS)
    return (
        "안녕하세요! 아래 주제로 도와드릴 수 있어요. 예시처럼 편하게 질문해 주세요:\n\n"
        f"{body}\n\n"
        "원하는 주제나 비슷한 질문을 입력해 주세요."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_suggestions.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add generation/suggestions.py tests/test_suggestions.py
git commit -m "feat(suggestions): 토픽 택소노미 + 전체 도움말 리스트업" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `build_topic_reply()` — 주제별 안내

**Files:**
- Modify: `generation/suggestions.py`
- Test: `tests/test_suggestions.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_suggestions.py` (and add `build_topic_reply` to the import line):

```python
from generation.suggestions import build_help_reply, build_topic_reply


def test_topic_reply_scopes_to_topic():
    reply = build_topic_reply("강의 운영")
    assert "강의 운영" in reply
    assert "과목을 복사" in reply     # 강의 운영 예시 포함
    assert "출석" not in reply        # 다른 토픽 예시는 미포함
    assert "궁금" in reply            # 구체 질문 유도 문구


def test_topic_reply_unknown_falls_back_to_help():
    assert build_topic_reply("없는토픽") == build_help_reply()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_suggestions.py -k topic_reply -v`
Expected: FAIL — `ImportError: cannot import name 'build_topic_reply'`

- [ ] **Step 3: Write minimal implementation**

Append to `generation/suggestions.py` (after `build_help_reply`):

```python
def build_topic_reply(topic_name: str) -> str:
    """범위 내 주제 선언 응답: 해당 주제 예시 + 구체 질문 유도."""
    t = next((t for t in _TOPICS if t.name == topic_name), None)
    if t is None:                      # 방어적: 알 수 없는 토픽이면 전체 도움말로 폴백
        return build_help_reply()
    examples = "\n".join(f'  · "{ex}"' for ex in t.examples)
    return (
        f"{t.emoji} {t.name} 관련해서 이런 점들을 도와드릴 수 있어요:\n\n"
        f"{examples}\n\n"
        "구체적으로 어떤 점이 궁금하신가요? 위 예시처럼 질문해 주세요."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_suggestions.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add generation/suggestions.py tests/test_suggestions.py
git commit -m "feat(suggestions): 주제별 안내 build_topic_reply" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `match_topic()` — 보수적 주제 선언 감지

**Files:**
- Modify: `generation/suggestions.py`
- Test: `tests/test_suggestions.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_suggestions.py` (and add `match_topic` to the import line):

```python
from generation.suggestions import build_help_reply, build_topic_reply, match_topic


def test_match_topic_fires_on_declaration():
    assert match_topic("강의 운영 관련해서 문의하고 싶어요") == "강의 운영"
    assert match_topic("과제 관련 질문 있어요") == "과제·평가"
    assert match_topic("출결 쪽 궁금한 게 있는데요") == "출결"


def test_match_topic_silent_on_concrete_questions():
    # 구체 질문/문제는 토픽 키워드가 있어도 게이트로(None) 보낸다.
    assert match_topic("출석했는데 결석으로 처리됐어요") is None
    assert match_topic("과제 점수가 학생에게 안 보여요") is None
    assert match_topic("지난 학기 과목을 복사하려면 어떻게 하나요?") is None


def test_match_topic_silent_without_intent():
    # 의도 표현 없이 토픽 단어만으로는 발화하지 않는다.
    assert match_topic("강의 운영") is None
    assert match_topic("퀴즈") is None
    assert match_topic("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_suggestions.py -k match_topic -v`
Expected: FAIL — `ImportError: cannot import name 'match_topic'`

- [ ] **Step 3: Write minimal implementation**

Append to `generation/suggestions.py`:

```python
# 주제 선언 감지: 토픽 키워드 + 의도 표현이 있고, 구체 질문 신호가 없을 때만 발화.
_INTENT_RE = re.compile(r"문의|질문|여쭤|물어보|관련(?:해서|해|이)?|대해|궁금")
# 구체 질문/문제 신호가 있으면 '선언'이 아니라 '진짜 질문' → 게이트로 보낸다.
_CONCRETE_RE = re.compile(
    r"어떻게|어떡|방법|하나요|할까요|되나요|있나요|입니까|어디|언제|왜|얼마|몇|"
    r"가능한가|안\s*돼|안\s*되|안\s*보|오류|에러|실패|처리|떴|뜨"
)


def match_topic(query: str) -> str | None:
    """범위 내 주제 선언이면 토픽명을 반환, 아니면 None (보수적 발화)."""
    q = query.strip()
    if not q or _CONCRETE_RE.search(q):
        return None
    if not _INTENT_RE.search(q):
        return None
    for t in _TOPICS:
        if any(kw in q for kw in t.keywords):
            return t.name
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_suggestions.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add generation/suggestions.py tests/test_suggestions.py
git commit -m "feat(suggestions): 보수적 주제 선언 감지 match_topic" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: guardrail — `is_help_request()` 추가 + social 역량 분리

**Files:**
- Modify: `generation/guardrail.py`
- Modify: `tests/test_social.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_social.py`, change the import line to:

```python
from generation.guardrail import is_help_request, is_meta_question, is_social_chitchat
```

Replace the existing `test_detects_capability_questions` function (lines 19-22) with:

```python
def test_capability_questions_route_to_help_not_social():
    # 역량 문의는 이제 social(짧은 인사)이 아니라 help(리치 리스트업)로 간다.
    for q in ("뭐 할 수 있어?", "무엇을 도와줄 수 있나요?", "어떤 기능이 있나요"):
        assert is_help_request(q)
        assert not is_social_chitchat(q)


def test_help_request_detects_guide_inquiries():
    # 2026-06-02 제보 트랜스크립트의 거절된 입력들
    assert is_help_request("어떤걸 가이드 받을수잇죠?")
    assert is_help_request("아니 그래도 가이드 받을껄 보고싶은데여")
    assert is_help_request("어떤걸 도와주실수 있는데여?")


def test_help_request_ignores_real_questions_and_topic_declarations():
    assert not is_help_request("과제 제출은 어떻게 하나요?")
    assert not is_help_request("출석했는데 결석으로 처리됐어요")
    # 주제 선언은 help 가 아니라 topic 경로로 가야 한다.
    assert not is_help_request("강의 운영 관련 문의하고 싶어요")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_social.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_help_request'`

- [ ] **Step 3: Write minimal implementation**

In `generation/guardrail.py`, **remove** the capability block from social. Delete these lines:

```python
# 역량 문의("뭐 할 수 있어")는 길이와 무관하게 소셜로 처리.
_SOCIAL_CAPABILITY = (
    r"(?:뭐|무엇을?|뭘|어떤\s*걸?|무슨)\s*(?:할\s*수\s*있|도와|해\s*줄|도움)|"
    r"(?:무슨|어떤)\s*기능|기능이?\s*뭐|할\s*줄\s*아"
)
```

and delete this line near the `_SOCIAL_CAP_RE` definition:

```python
_SOCIAL_CAP_RE = re.compile(_SOCIAL_CAPABILITY, flags=re.IGNORECASE)
```

and in `is_social_chitchat`, delete these two lines:

```python
    if _SOCIAL_CAP_RE.search(q):  # 역량 문의는 길이/질문신호와 무관하게 소셜
        return True
```

so that `is_social_chitchat` becomes:

```python
def is_social_chitchat(query: str) -> bool:
    """선의의 소셜(인사/감사/작별)인지. 메타 질문은 제외한다."""
    q = query.strip()
    if not q or is_meta_question(q):
        return False
    if len(q) > _SOCIAL_MAX_LEN or _QUESTION_HINT.search(q):
        return False  # 길거나 실제 질문이 섞이면 일반 답변 경로로
    return any(r.search(q) for r in _SOCIAL_SHORT_RES)
```

Then **add** the help-request classifier. Append at the end of `generation/guardrail.py`:

```python
# 역량/가이드/도움 문의. social(짧은 인사)에서 분리해 리치 리스트업으로 안내한다.
# (이전 _SOCIAL_CAPABILITY 패턴을 흡수하고 "가이드 받을 수 있나"류를 확장.)
_HELP_PATTERNS = [
    # "뭐/뭘/무엇을/어떤 걸/무슨 ... 도와/할 수 있/해 줄/알려 줄"
    r"(?:뭐|뭘|무엇을?|어떤\s*걸?|무슨|어떠한)\s*.{0,5}?(?:도와|도움|할\s*수\s*있|해\s*줄|해\s*주|알려\s*줄|알려\s*주)",
    # "가이드/안내/도움말 ... 받을/보고 싶/볼 수/뭐 있/보여/알려/있나/있어/있죠/가능"
    r"(?:가이드|안내|도움말)\s*.{0,6}?(?:받을|보고\s*싶|볼\s*수|뭐\s*있|무엇|보여|알려|있나|있어|있죠|있을까|가능)",
    # "어떤/무슨/뭐 ... 가이드/안내/도움말"
    r"(?:어떤|무슨|뭐|뭘|무엇)\s*.{0,6}?(?:가이드|안내|도움말)",
    # 기능 묻기 / 할 줄 아
    r"(?:무슨|어떤)\s*기능|기능이?\s*뭐|할\s*줄\s*아",
    # "뭐/뭘/무엇/어떤 걸 ... 물어보면/여쭤"
    r"(?:뭐|뭘|무엇을?|어떤\s*걸?)\s*.{0,6}?(?:물어|여쭤)",
]
_HELP_RES = [re.compile(p, flags=re.IGNORECASE) for p in _HELP_PATTERNS]


def is_help_request(query: str) -> bool:
    """역량/가이드/도움 문의인지. 메타 질문은 제외한다."""
    q = query.strip()
    if not q or is_meta_question(q):
        return False
    return any(r.search(q) for r in _HELP_RES)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_social.py -v`
Expected: PASS (모든 테스트 통과 — greeting/thanks/farewell 은 여전히 social, 역량/가이드는 help)

- [ ] **Step 5: Commit**

```bash
git add generation/guardrail.py tests/test_social.py
git commit -m "feat(guardrail): 역량/가이드 문의를 help로 분리 (is_help_request)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: stream — 라우팅 분기 2개 연결

**Files:**
- Modify: `generation/stream.py`
- Test: `tests/test_stream.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stream.py`:

```python
import asyncio

from app_types import Retrieval
from generation import stream as stream_mod


def _finals(query):
    async def run():
        out = []
        async for ev in stream_mod.stream_response(None, query):
            if ev.type == "text_final":
                out.append(ev.text)
        return out
    return asyncio.run(run())


def test_help_request_short_circuits_before_retrieval(monkeypatch):
    def boom(state, q):
        raise AssertionError("retrieval must not run for help requests")
    monkeypatch.setattr(stream_mod, "hybrid_search", boom)
    finals = _finals("어떤걸 가이드 받을수잇죠?")
    assert finals and "도와드릴 수 있어요" in finals[0]


def test_topic_declaration_short_circuits_before_retrieval(monkeypatch):
    def boom(state, q):
        raise AssertionError("retrieval must not run for topic declarations")
    monkeypatch.setattr(stream_mod, "hybrid_search", boom)
    finals = _finals("강의 운영 관련해서 문의하고 싶어요")
    assert finals and "강의 운영" in finals[0]


def test_real_question_falls_through_to_gate(monkeypatch):
    # 임베딩이 낮으면 게이트가 거절(NO_GUIDE_MSG) → 라우팅이 게이트까지 도달했음을 증명.
    low = Retrieval(items=(), top_score=0.0, max_embed_sim=0.0)
    monkeypatch.setattr(stream_mod, "hybrid_search", lambda state, q: low)
    finals = _finals("오늘 점심 뭐 먹지?")
    assert finals and "확인이 어렵습니다" in finals[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stream.py -k "short_circuits or falls_through" -v`
Expected: FAIL — help/topic 입력이 아직 게이트로 흘러 `boom`이 호출되거나(AssertionError), 응답 문구 불일치.

- [ ] **Step 3: Write minimal implementation**

In `generation/stream.py`, change the import line (currently line 9):

```python
from generation.guardrail import META_REPLY, SOCIAL_REPLY, is_meta_question, is_social_chitchat
```

to:

```python
from generation.guardrail import (
    META_REPLY,
    SOCIAL_REPLY,
    is_help_request,
    is_meta_question,
    is_social_chitchat,
)
from generation.suggestions import build_help_reply, build_topic_reply, match_topic
```

Then in `stream_response`, insert the two new branches. After the existing `is_meta_question` block and the `is_social_chitchat` block, the routing must read:

```python
    if is_meta_question(query):
        yield ChatEvent(type="text", delta=META_REPLY)
        yield ChatEvent(type="text_final", text=META_REPLY)
        yield ChatEvent(type="done")
        return

    if is_help_request(query):
        reply = build_help_reply()
        yield ChatEvent(type="text", delta=reply)
        yield ChatEvent(type="text_final", text=reply)
        yield ChatEvent(type="done")
        return

    if is_social_chitchat(query):
        yield ChatEvent(type="text", delta=SOCIAL_REPLY)
        yield ChatEvent(type="text_final", text=SOCIAL_REPLY)
        yield ChatEvent(type="done")
        return

    topic = match_topic(query)
    if topic:
        reply = build_topic_reply(topic)
        yield ChatEvent(type="text", delta=reply)
        yield ChatEvent(type="text_final", text=reply)
        yield ChatEvent(type="done")
        return

    retrieval = hybrid_search(state, query)
```

(The `retrieval = hybrid_search(state, query)` line and everything after it — the gate and LLM generation — stay exactly as they are.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_stream.py -v`
Expected: PASS (기존 helper 테스트 + 신규 라우팅 3개 모두 통과)

- [ ] **Step 5: Commit**

```bash
git add generation/stream.py tests/test_stream.py
git commit -m "feat(stream): 역량 문의·주제 선언 라우팅 (게이트 앞 분기)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: 전체 회귀 + 종단 검증

**Files:** (없음 — 검증만)

- [ ] **Step 1: 전체 단위 테스트 그린 확인**

Run: `python3 -m pytest -q`
Expected: 전부 통과 (기존 67 + 신규 ≈ 80여 개, 0 failed). 실패 시 해당 태스크로 복귀.

- [ ] **Step 2: 제보 4입력 수동 라우팅 확인**

Run:
```bash
python3 -c "
from generation.guardrail import is_meta_question, is_social_chitchat, is_help_request
from generation.suggestions import match_topic
for q in ['안녕하세여','네 제가 강의 운영 관련해서 문의하고싶은데여','어떤걸 가이드 받을수잇죠 ?','아니 그래도 가이드 받을껄 보고싶은데여','어떤걸 도와주실수 있는데여 ?']:
    if is_meta_question(q): r='META'
    elif is_help_request(q): r='HELP(리스트업)'
    elif is_social_chitchat(q): r='SOCIAL(인사)'
    elif match_topic(q): r=f'TOPIC({match_topic(q)})'
    else: r='RAG→게이트'
    print(f'{r:<18} {q}')
"
```
Expected:
- `안녕하세여` → SOCIAL(인사)
- `…강의 운영 관련해서 문의하고싶은데여` → TOPIC(강의 운영)
- `어떤걸 가이드 받을수잇죠 ?` → HELP(리스트업)
- `…가이드 받을껄 보고싶은데여` → HELP(리스트업)
- `어떤걸 도와주실수 있는데여 ?` → HELP(리스트업)

(이전엔 1·3·4번이 RAG→게이트로 떨어져 거절됐다. 더 이상 거절되지 않으면 RC-A/RC-B 해결.)

- [ ] **Step 3: (사용자 환경) 변측성 QA 하니스 재실행**

거짓전제·환각 비재발 회귀 확인 — Ollama·인덱스가 필요하므로 사용자 머신에서:
```bash
# 컨테이너/서버 기동 후 (별도 환경)
# qa/devtools-qa-runner 의 lms-faq-verification 프로파일로 재검증
```
Expected: 직전 통과 상태(fail 0) 유지 + 제보 입력 개선. 이 단계는 모델·네트워크 의존이라 자동 테스트에서 제외(스펙 4절).

- [ ] **Step 4: (배포) 이미지 재빌드·재배포는 별도 단계**

코드 머지 후, 기존 절차대로 이미지 빌드 → `:latest` 푸시 → 맥미니 `docker compose pull && up -d`. 본 계획 범위 밖(배포는 별도 의사결정).

---

## 완료 기준 (Definition of Done)

- `python3 -m pytest -q` 전부 통과 (회귀 0).
- 제보 4입력 중 거절됐던 3건(강의운영 선언, 가이드 문의 2건)이 HELP/TOPIC으로 라우팅.
- `ABS_EMBED_FLOOR`·게이트 조건·페르소나·인사말·거절문구 **무변경**(diff로 확인).
- `match_topic`이 구체 질문("출석했는데 결석 처리됐어요" 등)을 가로채지 않음(테스트로 고정).
