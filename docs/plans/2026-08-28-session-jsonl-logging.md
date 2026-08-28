# 세션별 JSONL 대화 로그

작성: 2026-08-28 · 대상: `apps/lms-chatbot-model-change`

## 목표

대화 기록을 세션 하나당 파일 하나(`data/logs/sessions/<session_id>.jsonl`)로
append 하여, 서비스 사용성 평가를 위한 원장을 만든다. SQLite 는 지금처럼
서비스 동작(세션 검증·피드백·관리자 조회)에 계속 쓰고, JSONL 은 분석용
사본이다.

## 현재 상태

이미 있는 것:

- `db/schema.py` — `sessions` / `turns` / `feedback` 3개 테이블
- `db/store.py` — `new_session` · `add_turn` · `add_feedback` · `purge_session`
- `/admin/logs` — 턴을 최신순 평면 리스트로 JSON·CSV 반환 (세션 묶음 없음)
- `docker-compose.yml` 이 `./data/logs` 를 읽기·쓰기 볼륨으로 이미 마운트
- `.gitignore` 에 `data/logs/` 포함

없는 것: 디스크에 남는 세션 단위 대화 기록, 그리고 어떤 모델·어떤 매뉴얼
스코프로 답했는지에 대한 기록.

핵심 관찰: 기록이 만들어지는 지점이 `db/store.py` 세 함수뿐이고 `backend.py`
는 전부 그리로 흐른다. 그래서 JSONL 쓰기를 store 안에 넣으면 호출부를
건드릴 필요가 거의 없다.

## 설계

### 파일 배치

```
data/logs/
  chat_logs.db              # 기존, 서비스 동작용 소스 오브 트루스
  sessions/
    3f2a…e1.jsonl           # 세션 1개 = 파일 1개
```

경로는 `config.logs_db_path.parent / "sessions"` 에서 파생한다. 새 환경변수를
만들지 않는다 — 볼륨 마운트가 이미 `data/logs` 를 통째로 잡고 있다.

### 레코드 형식

한 줄에 JSON 오브젝트 하나. `type` 으로 구분한다.

```jsonc
{"type":"session_start","ts":"2026-08-28T01:02:03+00:00","session_id":"3f2a…","consent_version":"v1","user_label":null}
{"type":"turn","ts":"…","session_id":"3f2a…","turn_id":41,"query":"…","response":"…",
 "sources":[{"title":"…","url":"…"}],"score":0.72,"latency_ms":812,
 "model":"gemini-2.5-flash","manual":"LMS","pinned":false}
{"type":"feedback","ts":"…","session_id":"3f2a…","turn_id":41,"rating":3,"comment":null}
```

`model` / `manual` / `pinned` 는 지금 DB 에 없는 필드다. 모델 교체 프로젝트라
어떤 모델이 답했는지가 평가의 축이고, 매뉴얼 스코프(LMS/CMS)와 핀 답변 여부는
사용성 판단에 직접 쓰인다. 세 필드 모두 `add_turn` 의 기본값 `None` 키워드로
받아 기존 호출·테스트를 깨지 않는다. DB 스키마는 건드리지 않는다 —
마이그레이션 비용 대비 얻는 게 없다.

### 개인정보 경계

IP·User-Agent·기기 식별자는 남기지 않는다. `docs/privacy.md` 1항이 수집 항목을
질의·응답·표시명·피드백·운영 메타데이터로 한정하고 8항에서 접속 IP 미수집을
명시하고 있어서, 여기서 늘리면 방침 위반이다. "다 쌓는다" 는 대화 내용과 운영
메타데이터를 빠짐없이 쌓는다는 뜻으로 해석한다.

## 단계

### Phase 1 — JSONL 라이터

`db/jsonl.py` 신규 (약 30줄):

- `append(logs_dir, session_id, record: dict) -> None`
  — `sessions/` 디렉터리 생성, `<session_id>.jsonl` 에 한 줄 append,
    `json.dumps(..., ensure_ascii=False)`.
- `session_path(logs_dir, session_id) -> Path`
- 직렬화 실패·디스크 오류는 잡아서 stderr 로 흘리고 삼킨다. SQLite 가 소스 오브
  트루스이므로 분석용 사본 때문에 채팅 응답이 죽으면 안 된다.
- `session_id` 는 `uuid4().hex` 라 경로 조작 위험이 없지만, 파일명으로 쓰기 전에
  hex 문자만 남기는 한 줄 검증을 둔다(외부 입력이 그대로 들어오는 경로다).

동시성: 단일 프로세스 FastAPI 이고 한 줄 append 는 POSIX 에서 원자적으로
취급 가능한 크기다. 다중 워커로 가면 세션이 워커에 고정되지 않아 인터리브가
생길 수 있으므로 `ponytail:` 주석으로 한계와 업그레이드 경로(워커별 파일 or
파일 락)를 남긴다.

### Phase 2 — store 배선

`db/store.py` 만 수정한다:

- `new_session` → `session_start` 레코드
- `add_turn` → `turn` 레코드, `model` / `manual` / `pinned` 키워드 추가
- `add_feedback` → `feedback` 레코드. 지금 `add_feedback` 은 `turn_id` 만 받고
  `session_id` 를 모르므로, `turns` 에서 한 번 조회해 세션을 찾는다.
- `purge_session` → DB 삭제 + JSONL 파일 삭제. 방침 6항의 삭제 요청에 파일이
  남으면 안 된다.

`backend.py` 는 `_chat_sse` 의 `store.add_turn` 호출에 세 필드를 넘기는 것만
바꾼다. `pinned` 는 이미 지역 변수로 있고, `manual` 은 `body.manual`,
`model` 은 `config.gemini_model` 이다.

### Phase 3 — 방침 문서 동기화

`docs/privacy.md`:

- 7항: 저장 위치를 "로컬 SQLite 파일" → "로컬 SQLite 파일과 세션별 JSONL 파일"
- 1항: 운영 메타데이터 예시에 응답 모델·문서 스코프 추가

### Phase 4 — 검증

`tests/test_store.py` 에 추가:

- `add_turn` 후 `sessions/<sid>.jsonl` 에 turn 레코드 한 줄이 생긴다
- 같은 세션에 두 번 쓰면 두 줄이 된다(append 확인)
- `purge_session` 후 파일이 사라진다
- JSONL 쓰기가 실패해도(디렉터리를 파일로 막아두고) `add_turn` 은 turn_id 를
  정상 반환한다

기존 스위트 전체 재실행.

## 안 하는 것

- **세션 묶음 export 엔드포인트** — 파일이 곧 세션이라 `cat`/`scp` 로 끝난다.
  원격에서 브라우저로 봐야 할 일이 생기면 그때 추가한다.
- **DB 스키마 변경** — `model`/`manual`/`pinned` 는 JSONL 에만 남긴다.
- **6개월 자동 삭제 잡** — 방침 3항이 요구하지만 DB 쪽에도 원래 없던 기능이라
  이 작업의 범위 밖이다. JSONL 이 같은 구멍을 하나 더 만드는 것은 사실이므로
  별도 항목으로 남긴다(파일 mtime 기준 정리는 `find -mtime +180 -delete` 한 줄).
- **로그 로테이션·압축** — 세션당 수 KB 규모다.
