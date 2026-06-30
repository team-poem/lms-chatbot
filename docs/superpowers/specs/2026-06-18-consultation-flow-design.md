# 선택형 상담 플로우 전환 설계

작성일: 2026-06-18

## 배경

현재 챗봇은 FAQ 칩·카탈로그 항목을 눌러도 "노드"가 아니라 "질문 텍스트"를 `/chat`으로 보내고, 서버가 그 텍스트를 `hybrid_search`로 **다시 검색**한 뒤(`generation/stream.py:74-75`) 매칭된 문서가 FAQ면 원문 직출력(`stream.py:119-130`), 가이드면 LLM(gemma) 생성(`stream.py:132-173`)으로 답한다.

즉 버튼 클릭조차 "텍스트 → 재검색 → 게이트 → (FAQ 직출력 | LLM 생성)"을 거치므로, 같은 버튼이라도 검색 순위·말투·모델 상태에 따라 답이 흔들린다. 답변률이 입력 표현과 모델 성능에 종속되는 구조 자체를 줄이는 것이 목표다.

참고 UI: 예비군 챗봇(KT-AICC). 첫 화면 환영 카드 → "자주하는 질문" 카테고리 → 버튼 선택 → 선택 질문이 사용자 말풍선 → 서버가 확정 답변 카드 → 답변 아래 바로가기/뒤로/관련 칩. 자연어를 LLM에 던지는 게 아니라 노드 식별자를 보내 확정 답변 카드를 받는 구조다.

## 목표

- 첫 화면을 선택형 상담 메뉴(환영 카드 + 카테고리 + 추천 FAQ + 빠른 링크) 중심으로 구성한다.
- 노드(상담 단위)를 클릭하면 `node_id`를 보내 **항상 연결된 확정 답변 카드**를 받는다. 재검색·게이트·LLM을 이 경로에서 들어낸다.
- 확정 답변: FAQ는 사람이 쓴 원문(`faq_answer`), 가이드는 정제된 문서 원문 직출력. **둘 다 LLM 미경유.**
- 답변 카드 아래에 관련 노드/뒤로가기/바로가기 링크를 렌더한다.
- 자유 입력창은 "관련 질문 찾기" 보조로 축소 — 노드 검색으로 가장 가까운 노드를 버튼으로 추천만 한다(자유 생성 없음).
- 기존 RAG/LLM(`/chat`)은 Phase 1에서 **파괴하지 않고 보존**한다.

## 비목표

- 모델 교체가 아니다(`OLLAMA_MODEL` 변경 같은 작업과 무관).
- Phase 1에서 LLM/RAG 경로를 제거하지 않는다. 제거 여부는 Phase 3에서 로그·커버리지를 보고 결정한다(현재 미정).
- 노드 트리를 손으로 처음부터 쓰지 않는다. 기존 FAQ CSV·카탈로그 TOC·인덱스에서 자동 도출하고, 큐레이션은 오버레이로만 덧입힌다(코드/값 하드코딩 금지 철학 유지).
- 입력 의도·말투 감지는 하지 않는다. 자유 입력은 노드 검색 매칭일 뿐이다.

## 아키텍처

두 경로를 분리한다.

```
[선택형 확정 경로 — LLM 없음]                 [레거시 RAG 경로 — 보존, Phase 3에서 처분 결정]
버튼/노드 클릭                                자유 입력(미매칭) 또는 명시적 폴백
  → node_id                                    → 기존 /chat (RAG → FAQ 직출력 | LLM 생성)
  → GET /answer/{id}
  → 확정 답변 카드 + 관련/뒤로/바로가기
```

- **노드 = 상담 단위**: FAQ 1건 또는 가이드 문서 1건 = 노드 1개. 안정 ID 보유.
- 노드 레지스트리는 서버 기동 시 1회 구성해 `app.state.nodes`에 캐시한다(`app.state.rag`와 동일 패턴, `backend.py:34-41`).
- 확정 답변 카드의 본질(`문서 → {답변, 이미지, 출처}`)은 이미 `stream.py:119-130`의 FAQ 직출력 분기가 증명한다. 이를 **재검색·게이트 앞단 없이** `node_id`로 직접 부르는 빌더로 일반화한다.

## 데이터 모델 — 자동 도출 + 큐레이션 오버레이

```
build_catalog()   ─┐  (카테고리·문서 순서 = 메뉴 골격)
load_questions()  ─┤→ 스켈레톤(카테고리·노드·parent·자동 related)
chroma 전수 열거   ─┘  (doc_set/text/images/notion_url = 답변 페이로드)
                        + data/nodes.overlay.json (links·related·parent·answer override)
                        = 노드 레지스트리
```

`app_types.py`에 추가:

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

### ID 규칙

`id = f"{manual.lower()}-{doc_set}-{sha1(doc_title)[:8]}"` (예: `lms-guide-1a2b3c4d`). 결정적·URL 안전·doc_title이 안정인 한 재빌드해도 동일. 카테고리(=parent) id는 `f"{manual.lower()}-cat-{sha1(category)[:8]}"`, FAQ 합성 카테고리는 `lms-faq-root`(답변 노드가 아니므로 별도 스킴). 화면에는 label만 노출되므로 ID 가독성은 큐레이션용. 빌드 시 `{id: {manual, doc_set, label}}` 매니페스트를 함께 출력해 큐레이터가 오버레이를 작성한다. doc_title이 바뀌면 ID도 바뀌므로 오버레이 항목을 갱신해야 한다(문서화).

### 노드 도출

- **가이드 노드**: `build_catalog()`의 (manual, category, doc_title)을 골격으로, chroma에서 같은 doc_title의 청크를 seq순으로 결합해 본문을 만든다. 조인 키는 이모지·공백을 정규화한 doc_title. 카탈로그에 있으나 인덱스에서 못 찾은 항목은 건너뛰고 로그(graceful). category가 parent.
- **FAQ 노드**: chroma의 `doc_set == "faq"` 청크를 doc_title로 묶어 노드화. FAQ CSV는 인덱싱되지 않으므로(`ingest/pipeline.py:80`) 실제 인덱스의 FAQ는 답변 .md 문서뿐이고 doc_title도 깔끔한 질문 제목이다 — `"FAQ —"` 접두는 CSV 전용(`chunk.py:166`)이라 실제로는 안 나타나며 제거는 방어적. `faq_answer`가 빈 답변이면(껍데기) 건너뛴다. 합성 카테고리 "자주 묻는 질문"(`lms-faq-root`)을 parent로 둔다. 첫 화면 `recommended`는 FAQ 노드에서 직접 무작위 N개(기존 5~7개 관례) 샘플 — CSV↔노드 조인을 피하고 추천 칩이 항상 답변을 갖게 한다.
- **자동 related**: 같은 카테고리 내 형제 노드를 기본 related로 채운다. 오버레이가 있으면 우선.

### 확정 답변 페이로드

- FAQ: `faq_answer(결합 본문)` 그대로(`generation/faq.py:25`).
- 가이드: 정제된 문서 원문 직출력(인덱스에 이미 전처리됨 — 결합만, LLM 영구 미경유).
- 이미지: `doc_image_refs(state, doc_title, manual)` 그대로(`retrieval/search.py:55`).
- 출처: `notion_url` 1건(`Source`). `"FAQ —"` 접두 문서는 출처 생략(기존 규칙 유지).
- 오버레이에 `answer`가 있으면 본문을 우선 대체한다.

### 오버레이 파일

`data/nodes.overlay.json` — id 기준 `{links, related, parent, answer}` 덧입힘·우선. 비어 있어도 동작(graceful). `faq.py`/`catalog.py`의 "데이터 없으면 생략" 철학과 동일.

## API (모두 평문 JSON — 확정 답변은 스트리밍 불필요)

| 메서드 | 경로 | 응답 | 비고 |
|---|---|---|---|
| GET | `/entry` | `{welcome, categories:[{id,label,nodes:[NodeRef]}], recommended:[NodeRef], quick_links:[NodeLink]}` | 첫 화면. 인증 불필요 |
| GET | `/answer/{id}` | `AnswerCard` (미존재 404) | **재검색·게이트·LLM 없음** |
| GET | `/search?q=` | `{candidates:[{id,label}]}` | `hybrid_search` 재사용 → 노드 매핑, 생성 없음 |

- `/entry`·`/answer/{id}`·`/search`는 모두 공개 읽기 전용(세션 불필요 — `/catalog`와 동일). **Phase 1은 선택 로깅을 하지 않는다**(데이터 수집 없음 → 동의 불필요). 프런트는 기존 동의 UI를 유지하되, 선택 로깅과 `turns.node_id` 컬럼은 Phase 2에서 추가한다.
- `/answer/{id}`: 순수 함수 `card_of(node)`에 위임하는 얇은 wrapper. 미존재 id는 404.
- `/search`: `hybrid_search(state, query)` 결과의 각 청크를 (manual, doc_title)→id로 매핑·중복 제거·상위 N(기본 5). 게이트·생성 없음. 0건이면 프런트가 QnA 게시판 안내(`qna_fallback_msg` 재사용).
- 기존 `/faq`·`/catalog`·`/chat` 유지. SSE 배관(`backend.py:27-31`, `api.js:sseEvents`)은 레거시 `/chat`에만 남긴다.

## 프런트 동작

- `static/js/api.js`: `fetchEntry()`·`fetchAnswer(id)`·`searchNodes(query)` 추가.
- `static/js/ui.js`: `renderEntryMenu(entry, handlers)`(환영 카드 + 카테고리 칩 + 추천 FAQ + 빠른 링크), `renderAnswerCard(card, handlers)`(사용자 말풍선=질문 / 좌측 카드=본문·이미지·바로가기 + 관련 칩 + 뒤로가기 + 출처). 기존 `makeChip`·`renderImages`·`renderSources` 재사용.
- `static/js/main.js`: 노드 플로우 컨트롤러 + 뒤로가기 스택. 관련 칩→`select(id)`, 자유 입력 submit→`searchNodes`→후보 칩.
- `static/index.html`: 고정 헤더·환영 영역 컨테이너, 입력 placeholder "관련 질문 찾기".
- `static/css/app.css`: 카드/관련/뒤로/바로가기/모바일 상담 레이아웃. 기존 칩 스타일 재사용.
- **롤아웃(플래그 병존)**: Phase 1은 새 플로우를 `?mode=consult`로 진입(레거시 UI가 기본). 라이브 MVP 안전 검증 후 Phase 2에서 기본값 전환.
- `/entry` fetch 실패 시 기존 안내 문구 유지(graceful degradation).

## LLM 유지 / 우회

**유지·재사용 (확정 답변의 근거)**
- `generation/faq.py:faq_answer` (FAQ 확정 본문 추출), `load_questions`/`sample_*` (추천)
- `generation/catalog.py:build_catalog` (메뉴 골격)
- `retrieval/search.py:doc_image_refs` (카드 이미지), `hybrid_search` (단 "관련 질문 찾기" 매칭 전용)
- `db/store` 동의·턴·피드백 로깅, `rag/state.py:RagState`/chroma (노드 전수 열거 + 검색)

**노드 경로에서 우회 (확정 경로에서 호출 안 함 / 레거시 `/chat`에만 잔존)**
- `generation/stream.py:132-173`의 `chat_stream`+`build_prompt` (LLM 생성), `generation/persona.py`
- `generation/relevance.py:doc_answers_question` (LLM 관련성 게이트)
- `stream.py:79·109`의 임베딩·점수 게이트 (재검색 신뢰도 판정 — 노드 ID가 권위라 불필요)
- `generation/guardrail.py:is_meta_question`, `generation/ollama.py`
- `generation/filters.py` (가이드 원문엔 경량 정제만 선택 적용)

→ Phase 1에서 삭제하지 않고 미사용 상태로 보존. 제거 여부는 Phase 3.

## 단계별 전환 계획

**Phase 0 — 노드 모델·레지스트리 (순수 로직, 동작 무변경)**
`app_types`에 타입 추가 → `generation/nodes.py`(스켈레톤·오버레이·`answer_card`·`find_related`) → `retrieval/search.py`에 본문 결합 헬퍼 → `data/nodes.overlay.json`(빈) → `tests/test_nodes.py`. API/UI/기존 동작 무변경.

**Phase 1 — 선택형 API + UI 추가 (비파괴, additive)**
백엔드: startup 레지스트리 캐시 + 공개 `/entry`·`/answer/{id}`·`/search`. `/faq`·`/catalog`·`/chat` 그대로. 프런트: 노드 플로우(`?mode=consult` 병존), 자유 입력→노드 추천, 미매칭→QnA 안내. 선택 로깅은 하지 않음(Phase 2로).

**Phase 2 — 선택형을 주 경로로 승격 + 큐레이션**
기본 UI를 노드 플로우로 전환, 로그 기반 `nodes.overlay.json` 큐레이션(바로가기·related·answer override), (선택) `turns`에 `node_id` 컬럼 idempotent 추가 + 관리자 내보내기 반영.

**Phase 3 — LLM/RAG 처분 결정 (보류)**
커버리지·로그 기반 결정: `/chat` 영구 폴백 유지 또는 LLM 경로 제거(`ollama`/`persona`/`relevance`/stream LLM 분기). 노드 검색이 BM25만으로 충분하면 BGE-M3·chroma·ollama 의존 제거 → 이미지 경량화·기동 단축. Dockerfile/requirements 정리. Phase 1·2는 이 결정에 의존하지 않는다.

## 테스트

- `tests/test_nodes.py`(신규): **모든 노드 로직을 순수 함수로 테스트** — `_node_id` 결정성, `group_docs`(seq 결합·이미지 중복 제거·notion_url), `build_nodes`(가이드/FAQ 도출·인덱스 미존재 건너뜀·빈 FAQ 제외), `fill_auto_related`(형제), `load_overlay`/`apply_overlay`(override·미존재 id 무시), `entry_payload` 구조, `card_of`, `find_related`(중복 제거·limit). 가짜 `Chunk`/카탈로그 입력(기존 `test_catalog.py`·`test_faq.py` 스타일).
- 엔드포인트는 위 순수 함수에 위임하는 얇은 wrapper(`return entry_payload(...)` 등)라 별도 단위테스트를 두지 않는다 — 기존 `tests/`에 `test_backend.py`가 없는 관례와 동일. 라이브 스모크 + `qa/` 러너로 검증.
- 프런트는 라이브 스모크(첫 진입 메뉴 → 노드 클릭 → 확정 카드 → 관련/뒤로/바로가기). `qa/` DevTools 러너 프로파일 추가 후보.

## 영향 범위 (파일)

**백엔드**
- 신규: `generation/nodes.py`, `data/nodes.overlay.json`, `tests/test_nodes.py`
- 수정: `app_types.py`(NodeLink/NodeRef/AnswerCard), `backend.py`(/entry·/answer/{id}·/search·startup 레지스트리 캐시), `retrieval/search.py`(본문 결합 헬퍼), `config.py`(overlay 경로 진입점)
- Phase 2: `db/schema.py`·`db/store.py`(선택 `node_id` 컬럼)

**프런트**
- 수정: `static/js/api.js`(fetchEntry/fetchAnswer/searchNodes), `static/js/ui.js`(renderEntryMenu/renderAnswerCard/관련·뒤로 칩), `static/js/main.js`(노드 플로우·뒤로 스택·자유입력 검색), `static/index.html`(헤더·환영·placeholder), `static/css/app.css`(카드·관련·뒤로·바로가기·모바일)

**유지(미수정)**: `generation/faq.py`, `generation/catalog.py`, `rag/state.py`, `db/store.py`(Phase 1), `generation/stream.py`·`persona.py`·`relevance.py`·`ollama.py`·`guardrail.py`·`filters.py`(레거시 `/chat` 전용으로 잔존)

## 리스크 / 결정 보류

- **가이드 원문 길이**: 문서 단위 카드가 길 수 있음. Phase 1은 문서 단위, 후속에 섹션 단위 노드/접기 고려(섹션 청킹 인프라 기존 존재).
- **조인 키**: 카탈로그 TOC label ↔ chroma doc_title 불일치 가능. 정규화 후 매칭, 미매칭 건너뜀+로그.
- **ID 안정성**: doc_title 변경 시 ID 변동 → 오버레이 갱신 필요(문서화).
- **최종 상태(#4)**: LLM/RAG 영구 폐기 여부 미정. Phase 3에서 결정.

## 비고

- 답변 정책(인덱싱된 가이드 근거만), 동의·로깅·이미지 격리는 기존 그대로(`AGENT.md` 신뢰 경계 유지).
- 노드 자동 도출은 `faq.py`/`catalog.py`의 "데이터 기반, 원본 바뀌면 재인덱싱으로 반영" 원칙을 잇는다. 큐레이션 오버레이만 사람이 관리.
