# 함수형 리팩터링 2라운드 설계 — 악취 제거·상수 중앙화·계층 복원

- 작성일: 2026-06-10
- 상태: 구현 완료 (refactor/functional-cleanup, 커밋 8개, QA 전/후 회귀 0건 — 답변 66건 바이트 일치)
- 선행 문서: `2026-05-27-functional-refactor-design.md` — 1라운드가 세운 스타일 헌법(frozen dataclass, 모듈 함수, wrapper 클래스 금지, 부수효과는 가장자리, env는 config.py 1회)을 본 문서는 그대로 계승하고, 그 위에서 이후 5주간 기능 추가로 쌓인 악취를 푼다.

## 1. 동기

1라운드(5/27) 이후 가이드 네비게이션·FAQ 직출력·매뉴얼 스코핑·관련성 게이트 등 기능이 빠르게 붙으면서:

- `generation/stream.py`(239줄)가 오케스트레이터 + 라우팅 + FAQ 답변 추출 + 폴백 문구 + 이미지 수집 + Ollama HTTP 클라이언트를 전부 떠안음
- 품질 튜닝 상수가 6개 파일에 산재 — 품질 조정 시 어디를 만져야 하는지 한눈에 안 보임
- generation 계층이 chroma 컬렉션을 직접 조회(계층 위반), private 함수 cross-import, 정규식 중복 발생
- `static/index.html`(598줄)에 CSS 161줄 + JS 382줄 인라인 — 통신·렌더·상태가 한 덩어리

## 2. 비목표 (Non-goals)

- 외부 동작 변경 없음 — 4장 행동 보존 계약 참조
- 성능 최적화·새 기능 아님
- 루트 평면 모듈(backend.py, config.py, app_types.py)의 src/ 패키지화 안 함 (Docker·run.sh·pytest 전부 영향 — MVP 단계에 과함, YAGNI)
- `.ralph/`, `.pi/`, `work/` 추적 해제 안 함 (사용자 결정: 작업 기록으로 유지). `.gitignore`는 현 상태 유지 (점검 결과 양호)
- 루트의 ignore된 아티팩트(zip/tgz/png) 디스크 정리 안 함

## 3. 확정된 결정 사항

| 항목 | 결정 |
|------|------|
| 프런트 분리 | CSS 분리 + JS를 역할별 ES 모듈 3개(api/ui/main)로. 빌드 스텝 없음 |
| 튜닝 상수 | 새 루트 모듈 `tuning.py` 단일 관리. 실측 근거 주석 보존 |
| 추적 파일 정리 | 모두 유지 |
| 검증 기준 | pytest + 서버 스모크 + **QA 러너 전/후 회귀 비교** |
| 진행 방식 | 악취 단위 인크리멘털 — 1악취 1커밋(8개), 매 커밋 pytest 그린 |
| 브랜치 | `refactor/functional-cleanup` (fix/faq-answer-quality HEAD 기준) |

## 4. 행동 보존 계약

다음은 리팩터링 전후 바이트 단위로 동일해야 한다:

1. HTTP API: 엔드포인트 경로·요청/응답 JSON 형태·상태 코드·SSE 이벤트 포맷
2. 인덱스·DB 스키마: chroma 메타데이터, bm25.pkl, chat_logs.db — **재인덱싱 불필요** (스키마 변경 시 재인덱싱 필수라는 운영 제약 때문에라도 건드리지 않음)
3. 답변 품질 로직: 임계값 수치, 게이트 판정 순서(메타 가드 → 임베딩 바닥 → 관련성 게이트 → FAQ 직출력/생성), 폴백 문구
4. 실행 인터페이스: `run.sh`, Dockerfile, docker-compose.yml, `python -m ingest.cli`, `python -m retrieval.cli`
5. 프런트 사용자 경험: 화면·동작 동일 (파일 구조만 변경)

## 5. 악취 인벤토리

| # | 악취 | 위치 |
|---|------|------|
| S1 | 튜닝 상수 산재 (임계값 6종, top-k 3종, 가중치, LLM 옵션, FAQ 개수, 청크 상한, 시퀀스 상한, 이미지 상한, CMS 트리거) | stream.py, search.py, hybrid.py, faq.py, chunk.py, embed.py, relevance.py |
| S2 | private cross-import: `catalog._find_manual_tocs`/`build_catalog`가 `ingest.chunk._derive_title`을 함수 내부에서 2회 import | catalog.py:156,172 |
| S3 | 정규식 중복: `_EMPTY_PARENS_RE` 동일 패턴 2곳 | chunk.py:82, catalog.py:34 |
| S4 | Ollama HTTP 호출 중복: 스트리밍 chat(stream.py:200-212)과 단발 chat(relevance.py:34-46)이 각자 httpx 코드 보유 | stream.py, relevance.py |
| S5 | 폴백 3-이벤트 yield(text/text_final/done) 패턴 3회 중복 | stream.py:117-122, 131-136, 166-170 |
| S6 | FAQ 답변 추출·폴백 문구가 오케스트레이터에 거주 | stream.py `_faq_answer`, `_qna_fallback_msg`, `_FALLBACK_MARK` |
| S7 | 계층 위반: generation이 chroma 컬렉션 직접 조회 (AGENT.md 디렉터리 맵상 "retrieval/ 검색만"의 영역) | stream.py `_doc_images` |
| S8 | backend.py import 시점 부수효과: `load_config()` + `store.init_schema()` 실행, mutable 전역 `_state` + `global` 문 | backend.py:24-26, 45-47 |
| S9 | `_serialize_sse` 수동 dataclass 변환 — `asdict()` 재귀 변환으로 충분 | backend.py:29-42 |
| S10 | 프레젠테이션 모놀리스: CSS(10-171)+마크업(172-213)+JS(214-596) 단일 파일, JS 안에서 통신·렌더·상태 혼재 | static/index.html |
| S11 | 문서 드리프트: AGENT.md가 존재하지 않는 `generation/pipeline.py` 참조, 이미지 정책 서술이 구현(1순위 문서 전 섹션 seq순)과 불일치, 디렉터리 맵에 rag/·qa/ 누락 | AGENT.md:29,33-35,47,51-59 |

## 6. 커밋 플랜

각 커밋: 변경 → `.venv/bin/pytest -q` 그린 → 커밋. 테스트의 import 경로 갱신은 해당 커밋에 포함.

### 커밋 1 — `tuning.py` 신설 (S1)

루트에 `tuning.py` 생성. 평면 모듈 상수 + 도메인 섹션 주석 (frozen dataclass 불필요 — 모듈 자체가 단일 네임스페이스). **각 상수에 붙은 실측 근거 주석을 그대로 옮긴다.**

| 섹션 | 상수 | 출처 |
|------|------|------|
| 검색 | `TOP_K=5`, `EMBED_K=20`, `BM25_K=20` | retrieval/search.py |
| 검색 | `W_BM25=0.4`, `W_EMBED=0.6` | retrieval/hybrid.py 기본 인자 |
| 답변 게이트 | `SCORE_THRESHOLD=0.25`, `ABS_EMBED_FLOOR=0.50`, `ABS_EMBED_CONFIDENT=0.65`, `RELEVANCE_FLOOR=0.30`, `RELEVANCE_RATIO=0.60`, `MAX_CONTEXT_CHUNKS=5` | generation/stream.py |
| 답변 | `MAX_IMAGES=5` | stream.py `_doc_images` limit 기본값 |
| 라우팅 | `CMS_TRIGGERS=("cms", "cloud editor", "클라우드 에디터")` | stream.py `_CMS_TRIGGERS` |
| LLM | `GEN_OPTIONS={"num_ctx": 8192, "temperature": 0.2}`, `GEN_TIMEOUT_S=180.0` | stream.py 하드코딩 |
| LLM | `RELEVANCE_OPTIONS={"temperature": 0.0}`, `RELEVANCE_TIMEOUT_S=30.0` | relevance.py 하드코딩 |
| FAQ | `FAQ_ENTRY_MIN=5`, `FAQ_ENTRY_MAX=7` | generation/faq.py |
| 인제스트 | `CHUNK_MAX_CHARS=3000`, `CHUNK_OVERLAP=200` | ingest/chunk.py |
| 인덱스 | `EMBED_MAX_SEQ_LEN=1024` | index/embed.py |

제외(구현 디테일 — 현 위치 유지): 정규식 전부, `_FALLBACK_MARK`(커밋 4에서 persona로), 컬렉션명 `_COLLECTION`, FAQ CSV 컬럼명/글롭, `CONSENT_VERSION`(품질 노브 아닌 정책 버전 — backend 유지).

함수 기본 인자(`hybrid_search(k=TOP_K)` 등)는 tuning 상수를 참조하도록 변경하되 시그니처 형태는 유지.

### 커밋 2 — 중복 해소 (S2, S3)

- `ingest/chunk.py`: `_derive_title` → `derive_title` public 승격 (+ 기존 내부 사용처 갱신)
- `generation/catalog.py`: 함수 내부 import 2곳 → 모듈 상단 `from ingest.chunk import derive_title` (순환 의존 없음 확인됨)
- `_EMPTY_PARENS_RE` 단일화: `ingest/preprocess.py`에 공용 함수 `strip_empty_parens(text) -> str` 신설 (preprocess는 텍스트 정리 모듈이고 catalog가 이미 `strip_emoji`를 import 중 — 자연스러운 거주지, 순환 없음). chunk.py·catalog.py의 중복 정규식 제거 후 이 함수 사용

### 커밋 3 — `generation/ollama.py` 추출 (S4)

```python
async def chat_stream(host, model, messages, *, options, timeout) -> AsyncIterator[str]
    # stream.py의 httpx 스트리밍 루프 (라인 파싱·done 처리 포함)
async def chat(host, model, messages, *, options, timeout) -> str
    # relevance.py의 단발 호출
```

예외 정책은 호출부에 남긴다: relevance는 기존대로 try/except로 None 반환(답을 막지 않음), stream은 기존대로 전파.

### 커밋 4 — `stream.py` 분해 (S5, S6)

- `fallback_events(msg, score=0.0) -> tuple[ChatEvent, ...]` 순수 함수 신설 → 3곳의 중복 yield를 `for evt in fallback_events(...)` 로
- `_faq_answer` → `generation/faq.py`의 `faq_answer()` (FAQ 도메인 응집)
- `_qna_fallback_msg` + `_FALLBACK_MARK` → `generation/persona.py` (규칙 5 문구와 같은 파일에서 동기 관리 — 문구가 시스템 프롬프트와 일치해야 하는 제약을 파일 배치로 표현)
- `_route_manual`은 stream에 잔류 (3줄 오케스트레이션 로직, 트리거 데이터는 커밋 1에서 tuning으로 이동됨)

### 커밋 5 — 이미지 조회 계층 복원 (S7)

- `retrieval/search.py`에 `doc_image_refs(state, doc_title, *, manual="") -> tuple[str, ...]` 신설: chroma where 조회 + seq 정렬 + 중복 제거 (stream.py `_doc_images`의 조회 절반)
- stream.py에는 폴백(컨텍스트 청크 이미지)과 상한 적용만 남김
- generation에서 `index.vector_store` 직접 import 제거

### 커밋 6 — backend.py 정리 (S8, S9)

- `store.init_schema()`·RagState 로드를 lifespan으로 이동, 전역 `_state`/`global` 문 제거 → `app.state.rag` 사용 (핸들러는 `request.app.state` 경유)
- `config = load_config()`는 모듈 레벨 1회 유지 (앱 구성(mount)에 필요 — 1라운드 헌법 "env는 config.py 1회"와 일치)
- `_serialize_sse` → `json.dumps(asdict(evt), ensure_ascii=False)` 단순화. asdict는 중첩 dataclass(Source)를 재귀 변환하고 json.dumps가 tuple을 배열로 직렬화 — 출력 JSON 동일함을 테스트로 확인
- "import만으로 DB 스키마 생성"에 의존하는 테스트·스크립트가 있으면 함께 갱신 (plan에서 전수 확인)

### 커밋 7 — 프런트 분리 (S10)

```
static/index.html   마크업 + <link rel="stylesheet"> + <script type="module" src="/static/js/main.js">
static/css/app.css  기존 <style> 내용 그대로 (수정 없음)
static/js/api.js    서버 통신·SSE 파싱 (컨트롤러): health/consent/chat/feedback/faq/catalog/purge
static/js/ui.js     DOM 렌더 (프레젠테이션): 턴 렌더·QnA 링크 치환·이미지·출처·라이트박스·칩·네비
static/js/main.js   엔트리: 세션 상태(localStorage)·이벤트 바인딩·동의 모달 플로우
```

- 인라인 `onclick` 등 전역 의존 핸들러는 ES 모듈 스코프에서 깨지므로 `addEventListener`로 통일 (plan에서 마크업 전수 확인)
- 함수 이동만, 로직 수정 없음. CSS는 무수정 복사
- 검증: 브라우저 실화면 — 동의 → FAQ 칩 → 질문/스트리밍 → 이미지/출처 → 피드백 → 가이드 네비 → 라이트박스

### 커밋 8 — 문서 동기화 (S11)

- AGENT.md: `generation/pipeline.py` → `generation/stream.py`, 이미지 동반 정책 서술 현행화, 디렉터리 맵에 `tuning.py`·`rag/`·`qa/`·static 구조 반영, 검색 정책의 상수 출처를 tuning.py로 표기
- README.md: 변경 불필요 예상 (빠른 시작·문서 링크만 있고 모듈 구조 서술 없음) — 확인만 수행

## 7. 검증 전략

1. **사전 베이스라인** (리팩터링 시작 전, 현 HEAD에서): 서버 + ollama 기동 → QA 러너 `qa:paraphrase`, `qa:adversarial` 실행 → 결과를 `reports/`에 보존. ollama 가용 여부를 이 시점에 확인
2. **매 커밋**: `.venv/bin/pytest -q` 그린 (시스템 python 아닌 .venv — pandas/httpx)
3. **커밋 6 후**: 서버 기동 스모크 — `/health`, `/faq`, `/catalog`, `/guide`, `retrieval.cli` 검색 1건
4. **커밋 7 후**: 브라우저 실화면 전 플로우 확인
5. **최종**: QA 러너 동일 프로파일 재실행 → 베이스라인과 판정 비교. FAQ 직출력 경로는 결정적이라 직접 비교 가능, LLM 생성 경로(temperature 0.2)·FAQ 무작위 샘플링은 비결정성 감안해 judge 판정 수준에서 비교

## 8. 위험·완화

| 위험 | 완화 |
|------|------|
| tuning.py import 방향 — ingest/index가 루트 모듈을 임포트 | tuning은 무엇도 임포트하지 않는 잎 모듈 (1라운드 config와 동일 원칙) — 순환 불가능 |
| backend lifespan 이동으로 초기화 타이밍 변화 | uvicorn 실행 경로에선 lifespan이 요청 수신 전 완료 — 외부 관찰 동작 동일. import 부수효과에 의존하던 테스트만 명시 갱신 |
| ES 모듈 전환 시 전역 함수 참조 깨짐 | 인라인 핸들러 전수 grep 후 addEventListener 통일. 모듈은 defer라 실행 타이밍은 기존(body 끝 인라인)과 동등 |
| asdict 단순화로 SSE JSON 미세 변화 | 변환 전후 각 이벤트 타입의 직렬화 결과를 단위 테스트로 고정 |
| QA 비교의 비결정성 | FAQ 직출력(결정적) 위주로 엄격 비교, 생성 경로는 judge 판정으로 |

## 9. 범위 외 후속 후보 (이번에 안 함)

- `index.html`의 escape() 등 공용 JS 유틸 추가 분리 — 3모듈로 충분하면 중단 (YAGNI)
- tuning 상수의 env 오버라이드 — 필요해질 때 config.py와 통합 검토
- 신규 테스트 확충 (이번엔 기존 테스트 이전 + asdict 동등성 테스트만)
