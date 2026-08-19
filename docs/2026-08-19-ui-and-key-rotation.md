# 2026-08-19 작업 기록 — 대기 표시·동의 모달·QnA 링크·키 로테이션

이 문서는 2026-08-19에 한 작업 다섯 건의 문제와 해결을 기록한다. 각 항목은
**증상 → 원인 → 변경 → 검증** 순서다. 결과물은 PR 두 개다.

| PR | 브랜치 | 범위 |
|---|---|---|
| [#17](https://github.com/team-poem/lms-chatbot/pull/17) | `feat/consult-loading-indicator` | UI 4건 |
| [#18](https://github.com/team-poem/lms-chatbot/pull/18) | `feat/gemini-key-rotation` | Gemini API 키 로테이션 |

가장 먼저 읽을 것은 1항이다. 나머지 항목의 배포 시점을 결정한다.

## 1. 배포본은 저장소와 다른 계보다

### 증상

라이브에서 다음 넷이 보고됐다.

1. 깨진 이미지가 크게 뜬다
2. 채팅 입력창 반응형이 깨진다
3. 로딩 인디케이터가 없다
4. 개인정보 동의 화면이 뜬다

### 원인

라이브 배포본은 이 저장소의 `main`이 아니다. 커밋
[`2885300`](https://github.com/team-poem/lms-chatbot/commit/2885300)에 이미 기록돼
있다 — 라이브는 `/entry`·`/search`가 404이며, **PR #15 이전 코드베이스에 7월
개인정보 패치만 얹은 별개 계보**다. `consent_version`도 갈라져 있었다(라이브
`2026-07-16-v2` / 저장소 `2026-05-26-v1`).

그래서 8월 작업이 라이브에 하나도 반영돼 있지 않다. 여기에는 임베드 세로 레이아웃
수정([`7b8a8a9`](https://github.com/team-poem/lms-chatbot/commit/7b8a8a9)),
선택형 상담 플로우(PR #15), 대기 표시가 모두 포함된다.

### 확인 결과

로컬 최신에서 1·2번은 재현되지 않았다.

- 로고(`eclass1.dongseo.ac.kr/customs/main/xnds_header_logo.png`)는 HTTP 200이고
  `static/css/app.css`의 `.top h1 img { height: 28px }`로 크기가 묶여 있다
- 답변 이미지는 `static/js/ui.js`의 `renderImages`가 `onerror`로 404 이미지를
  제거한다 — 깨진 이미지 자리가 남지 않는다
- 뷰포트 500px에서 가로 스크롤이 없고, 입력창 405px·전송 버튼 54px로 배치된다

3번은 코드에 있으나 배포된 적이 없고, 4번만 실제로 고칠 것이 있었다(3항).

### 해야 할 일

PR #17을 `main`에 병합한다. 병합 시
[`dd57fc4`](https://github.com/team-poem/lms-chatbot/commit/dd57fc4)의 자동 빌드가
Docker Hub에 이미지를 올린다. 맥미니에서 이미지를 받아 재기동하면 라이브 계보가
저장소와 합쳐진다. 배포 절차는 [맥미니 배포 가이드](deploy-mini.md)를 따른다.

## 2. 대기 표시를 단계 문구 시머로 교체

### 증상

선택형 상담 모드(`?mode=consult`)에서 노드를 눌러도, 자유 입력을 보내도 응답이 올
때까지 화면에 아무 변화가 없다.

### 원인

대기 표시(점 3개, `lms-bounce`)가 레거시 RAG 경로인 `ask()`에만 붙어 있었다.
상담 모드의 두 경로 `selectNode()`·`consultSearch()`는 지나지 않는다.

점 3개 자체도 "무언가 돌고 있다"까지만 알린다. 어느 단계에서 기다리는지는 호출부만
안다.

### 변경

대기 문구를 호출부가 넘기고, 그 문구를 그대로 보여준다.

| 경로 | 문구 |
|---|---|
| `POST /chat` | 가이드를 찾는 중 |
| `GET /search` | 관련 항목을 찾는 중 |
| `GET /answer/{id}` | 안내를 불러오는 중 |

`selectNode()`는 `cardCache`가 있으면 즉답이므로 표시하지 않는다.

모션은 `ddukddak-hub`의 `ShiningText`를 옮겼다(원본: 21st.dev
`@preetsuthar17/shining-text`). 밝은 띠가 글자 위를 훑는 그라디언트를
`background-clip: text`로 글자 모양으로 잘라낸다. 외부 라이브러리를 쓰지 않는다.

```css
.loading {
  background-image: linear-gradient(110deg, var(--text-muted) 35%, var(--border) 50%, var(--text-muted) 65%);
  background-size: 200% 100%;
  background-clip: text;
  color: transparent;
  animation: shining-text 2.2s linear infinite;
}
```

`prefers-reduced-motion: reduce`에서는 애니메이션을 끄고 회색 평문으로 둔다.

바뀐 파일: `static/css/app.css`, `static/js/ui.js`, `static/js/main.js`.
`@keyframes lms-bounce`는 제거했다.

### 검증

- DOM 스텁 self-check 3건 — 문구 렌더, 제거 함수 중복 호출 안전, HTML 이스케이프
- 브라우저에서 `.loading`의 computed style이 `shining-text 2.2s`,
  `background-clip: text`, `color: transparent`
- 두 프레임을 찍어 밝은 띠 위치가 이동하는 것을 확인

## 3. 개인정보 동의 모달 제거

### 변경

페이지에 들어오면 곧바로 세션을 발급한다. 첫 화면에서 버튼을 한 번 더 누르지
않는다.

- `static/index.html` — 모달 마크업 삭제
- `static/js/main.js` — `consent()`를 `newSession()`과 `start()`로 나눴다. 저장된
  세션이 있으면 이어 쓰고, 없으면 바로 발급한다
- `static/js/ui.js` — `showConsentModal`·`renderDenied` 삭제
- `static/css/app.css` — 쓰이지 않게 된 `.modal*` 규칙 삭제

`POST /consent` 호출과 `CONSENT_VERSION` 기록은 남긴다. 무엇을 어느 버전으로
고지했는지의 서버 측 기록이고, 고지 본문은 푸터의 `/privacy` 링크가 상시
제공한다(Gemini 국외 이전 고지 포함).

403(서버에 세션이 없음)은 모달을 다시 띄우는 대신 세션을 조용히 재발급하고 다시
물어봐 달라고 안내한다. 자동으로 재전송하지 않는다 — 실패가 반복되면 무한 루프가
된다.

### 검증

로컬에서 `localStorage`를 비우고 다시 들어가 확인했다. 모달 없이 세션이 발급되고,
입력창이 활성화되며, 첫 화면이 렌더된다.

## 4. QnA 게시판 링크 복구

### 증상

폴백 안내 "준비된 매뉴얼 답변에서 확인되지 않는 질문입니다. e-Class QnA 게시판으로
문의 부탁드립니다."의 `e-Class QnA 게시판`에 링크가 걸리지 않는다.

### 원인

링크를 거는 코드(`QNA_LINK_PHRASES`, `setAnswerText`)는 이미 있었다. 세 곳에서
따로 죽어 있었다.

1. `.env`에 `QNA_BOARD_URL=`만 남아 있으면
   `os.environ.get("QNA_BOARD_URL", 기본값)`이 기본값을 쓰지 않는다. 키가
   **존재하고 값이 빈 문자열**이기 때문이다. `/health`가 `""`를 내려보내 링크가
   통째로 사라진다
2. `renderAnswerCard`가 `setAnswerText(..., "")`로 빈 URL을 넘긴다. 상담 카드는
   애초에 링크가 걸릴 수 없었다
3. `appendCandidateBlock`은 안내를 `textContent`로 찍어 링크 경로를 지나지 않는다

호출부마다 URL을 넘기게 둔 구조가 원인이다. 넘기는 것을 잊은 곳만 조용히 맨
텍스트가 된다.

### 변경

- `config.py` — `os.environ.get(name, 기본값)`을 `os.environ.get(name) or 기본값`으로
  바꿨다. `.env`를 비워둬도 기본값이 산다
- `static/js/ui.js` — 게시판 URL을 모듈이 들고 있게 하고 `setQnaBoardUrl()`을
  추가했다. 답변·상담 카드·후보 블록 세 경로가 같은 규칙 하나를 지난다

링크를 거는 문구는 세 가지다: `e-Class QnA 게시판`, `Q&A 바로가기`, `Q&A 게시판`.

### 검증

로컬에서 범위 밖 질문("학교 주차장 요금이 얼마인가요")을 실제로 보내 폴백을
받았다. `href`가 게시판 URL이고 `target="_blank"`, `rel="noopener noreferrer"`가
붙는다.

## 5. 푸터 '대화 기록 삭제' 링크 제거

### 변경

푸터에서 링크를 없애고 `static/js/main.js`의 `#purge` 핸들러를 삭제했다. 푸터에는
`개인정보처리방침`만 남는다.

개인정보처리방침 6항이 이 링크를 삭제 요청 수단으로 지목하고 있었다. 링크만
없애면 방침이 거짓 안내가 되므로 함께 고쳤다.

- 6항 — "챗봇 화면 하단의 링크 또는 문의처를 통해" → "아래 문의처를 통해 요청해
  주십시오"
- 5항 — "첫 진입 동의 모달에서도 별도 고지합니다" 문장 삭제(모달이 없어졌다)
- `static/privacy.html`과 `docs/privacy.md` 양쪽에 반영

`POST /purge` 엔드포인트는 남긴다. 방침이 문의처로 삭제를 요청하라고 안내하는데
지울 수단이 없으면 대응 자체가 불가능하다.

## 6. Gemini API 키 로테이션

### 문제

무료 티어의 분·일 요청 제한은 **키마다 따로** 찬다. 키가 하나뿐이면 429를 만났을
때 기다리는 것 말고 할 수 있는 일이 없다.

- 인덱싱은 분당 창이 풀릴 때까지 최대 90초씩 잔다(`BACKOFF_CAP_S`)
- `chat_stream`에는 재시도가 없어 델타 없이 끝나고 사용자는 폴백 문구를 본다

작업 전 상태를 확인했다. 저장소 전체 이력에 `GEMINI_API_KEY2`·키 풀·라운드로빈
흔적이 없다. 로테이션을 구현한 브랜치도 없다.

### 변경

키를 최대 3개까지 받는다.

```bash
GEMINI_API_KEY=<필수>
GEMINI_API_KEY2=<선택>
GEMINI_API_KEY3=<선택>
```

앞의 키부터 쓰고, 429를 만나면 백오프 **전에** 남은 키를 먼저 쓴다. 키를 하나만
넣어도 그대로 동작한다.

- `gemini_keys.py`(신규) — `KeyRing`(키 목록과 커서), `as_ring()`, `from_env()`.
  커서는 요청 사이에 유지된다. 매 요청 1번 키부터 시작하면 이미 마른 키에 왕복
  한 번씩을 계속 버려 로테이션의 의미가 없어진다
- `generation/gemini.py` — `chat`·`chat_stream`이 429면 다음 키로 재시도한다. 링을
  한 바퀴만 돌고 멈춘다
- `index/gemini_embed.py` — `_post_with_retry`가 백오프 전에 링을 한 바퀴 돌린다.
  살아 있는 키가 있는데 90초를 자는 것은 낭비다
- `config.py`·`rag/state.py`·`index/embed.py` — 단일 `gemini_api_key`를
  `gemini_api_keys` 튜플로 바꿨다. 빈 값과 공백은 걸러낸다

5xx와 400에서는 키를 바꾸지 않는다. 서버 문제나 요청 스키마 문제는 키를 바꿔도
결과가 같고, 멀쩡한 키의 쿼터만 태운다.

로그에는 키 **번호**만 남긴다.

```
[gemini_embed] 429 — 다음 키로 전환 (키 #2/3)
```

기존 호출부가 넘기는 문자열 하나는 `as_ring()`이 흡수한다.
`load_embedder(cfg | str)`과 같은 방식이라 호출부를 고치지 않았다.

### 검증

전체 테스트 239개 통과. 신규 `tests/test_gemini_keys.py` 14건이 다음을 고정한다.

- 빈 키 제거, 커서 순환, 키가 하나면 `rotate()`가 `False`
- 429에서 `sleep` 없이 전환(`slept == []`로 검사)
- 살아난 키를 다음 요청에도 계속 사용
- 모든 키가 마르면 그때 백오프
- 5xx·400에서는 전환하지 않음
- 생성 경로는 링을 한 바퀴 돈 뒤 폴백(무한 재시도 없음)

`test_dockerfile_closure`가 `gemini_keys.py`의 `COPY` 누락을 잡아냈다. Dockerfile,
`docker-compose.yml`, `.env.example`, 배포 가이드, README를 함께 갱신했다.

## 남은 일

- **PR #17을 병합하고 재배포한다.** 1항의 계보 분리는 배포 전까지 해소되지 않는다
- **라이브에서 깨진 이미지를 다시 확인한다.** 로컬에서 재현되지 않아 원인을 특정하지
  못했다. 배포 후에도 남으면 해당 화면의 URL과 화면을 확보해야 한다
- **`/chat` 대기 문구가 한 단계뿐이다.** 서버가 stage 이벤트를 보내면 "검색 → 판정
  → 생성"으로 나눌 수 있다. 현재 SSE 이벤트는 `text`·`text_final`·`done`·`turn_id`
  넷뿐이라 클라이언트가 단계 경계를 모른다
- **생성 경로에는 백오프가 없다.** 모든 키가 429면 곧바로 폴백한다. 사용자를 기다리게
  하지 않으려는 선택이지만, 재시도 한 번의 값어치는 운영 로그를 보고 판단한다
