# 배포 후 첫 화면이 죽은 사고 — 캐시 스큐

2026-08-19, 새 버전을 배포한 뒤 라이브에서 추천 질문과 입력창이 사라졌다. 서버는
정상이었고 원인은 브라우저 캐시였다. 이 문서는 증상부터 최종 조치까지의 경위와,
중간에 틀렸던 두 판단을 기록한다.

같은 종류의 사고를 다시 만나면 [조사 방법](#조사-방법)부터 읽으면 된다.

## 증상

배포 직후 라이브(https://lms-bot.121.145.133.68.sslip.io/)에서 다음이 관찰됐다.

- 첫 화면의 추천 질문 칩이 하나도 렌더되지 않는다
- 입력창이 비활성 상태로 남는다
- 대화 영역에 placeholder만 남는다

서버 응답은 모두 정상이었다.

```
GET /health   200  build=3bf9fe9…  ← 배포된 코드는 최신
GET /faq      200  questions 8개
GET /entry    200
GET /         200  동의 모달 마크업 없음(새 HTML)
```

배포는 성공했고 API도 답한다. 화면만 죽었다.

## 조사 방법

### 1단계: 콘솔 예외 확인

브라우저 콘솔에 예외가 하나 있었다.

```
TypeError: Cannot read properties of null (reading 'addEventListener')
    at /static/js/main.js:160
```

`main.js`가 존재하지 않는 요소에 이벤트를 걸었다. ES 모듈에서 최상위 예외가 나면
그 아래 코드가 전부 실행되지 않는다. 세션 발급과 첫 화면 렌더가 모두 이 줄
아래에 있었다.

### 2단계: 브라우저가 쓰는 파일과 서버가 주는 파일 비교

`curl`로 받은 `main.js`의 160번째 줄은 정상이었다. 그렇다면 브라우저가 다른 파일을
쓰고 있다는 뜻이다. 페이지 안에서 두 벌을 받아 비교했다.

```js
const fresh = await fetch('/static/js/main.js?cb=' + Math.random()).then(r => r.text());
const used  = await fetch('/static/js/main.js').then(r => r.text());
```

| | 서버 최신(`fresh`) | 브라우저가 쓰는 것(`used`) |
|---|---|---|
| 크기 | 5,728B | 5,971B |
| `#agree` 참조 | 없음 | 있음 |

쿼리 스트링을 붙인 요청은 캐시를 우회한다. 두 응답의 크기가 다르면 캐시가
관여했다는 증거다.

## 원인

새 HTML과 옛 JavaScript가 한 페이지에서 만났다.

이날 배포에서 개인정보 동의 모달을 제거했다. HTML에서 `#agree`·`#deny` 버튼이
사라졌고, `main.js`에서 그 버튼에 붙던 이벤트 등록도 함께 지웠다. 두 파일은 짝을
이뤄야 한다.

브라우저는 HTML만 새로 받고 JavaScript는 캐시에서 썼다. 옛 `main.js`가 이미 없는
`#agree`에 `addEventListener`를 걸었고, `null`에 접근해 모듈이 중단됐다.

캐시가 갈린 이유는 `Cache-Control` 헤더가 없어서다. FastAPI의 `StaticFiles`와
`FileResponse`는 `ETag`와 `Last-Modified`만 붙인다. `Cache-Control`이 없으면
브라우저는 **휴리스틱 캐싱**을 한다 — `Last-Modified`로부터 지난 시간의 10% 정도를
임의로 신선하다고 보고 **서버에 묻지 않는다**. 파일마다 `Last-Modified`가 다르므로
갱신 시점도 제각각이 되고, HTML과 JS가 갈린다.

## 조치

### 1차 시도: `Cache-Control: no-cache` (PR #19) — 실패

`/`·`/privacy`·`/static/*`에 `no-cache`를 붙였다. 병합하고 배포했는데 증상이 그대로
남았다. 두 가지가 겹쳤다.

**첫째, 원리상 부족하다.** `no-cache`는 **앞으로의** 요청을 재검증하게 만들 뿐이다.
이미 캐시에 자리 잡은 옛 `main.js`에는 소급되지 않는다. 그 브라우저는 여전히
서버에 묻지 않는다.

**둘째, 병합 사고가 겹쳤다.** PR #19은 브랜치를 강제 푸시하기 전 상태로 병합됐다.
확인 방법은 병합 커밋이 아니라 파일 내용이다.

```bash
git show origin/main:backend.py | grep -c 'STATIC_PREFIX'   # 0 → 반영 안 됨
```

`/health`의 `build`가 최신이어도 그 커밋에 원하는 변경이 들었는지는 별개다.

### 2차 시도: 자산 경로에 빌드 해시 (PR #21)

자산을 `/static/<빌드해시 12자>/js/main.js`로 서빙한다. 배포마다 URL이 달라지므로
캐시가 원천적으로 맞지 않는다. `index.html`은 서빙 시점에 `"/static/`을
`"/static/<해시>/`로 바꿔 내보낸다.

```python
BUILD_SHA = os.environ.get("BUILD_SHA", "dev")
STATIC_PREFIX = f"/static/{BUILD_SHA[:12]}"

app.mount(STATIC_PREFIX, StaticFiles(directory="static"), name="static_versioned")
app.mount("/static", StaticFiles(directory="static"), name="static")
```

설계에서 정한 것 셋.

- **쿼리 스트링(`?v=`)이 아니라 경로 접두를 쓴다.** `main.js`는 `./ui.js`를
  상대경로로 `import`한다. 진입점에만 쿼리를 붙이면 이 import에는 쿼리가 붙지 않아
  옛 `ui.js`가 그대로 온다. 경로 접두는 상대경로 해석에 그대로 반영되므로 import
  대상까지 같은 버전으로 따라온다
- **버전 없는 `/static` 마운트를 남긴다.** 캐시에 옛 HTML이 남은 사용자가 이 경로로
  찾아온다. 404로 만들면 그 사용자는 빈 화면을 본다
- **`no-cache`는 `index.html`에만 남긴다.** HTML은 버전을 붙일 곳이 없어 매번
  재검증해야 한다. 자산은 URL이 버전을 들고 있어 재검증이 필요 없다

## 재발 방지

`tests/test_cache_headers.py` 9건이 다음을 고정한다.

- `index.html`이 버전 경로를 가리키고, 버전 없는 경로가 남아 있지 않을 것
- 버전 경로로 `main.js`·`ui.js`·`api.js`·`app.css`가 모두 200일 것
- 버전 없는 경로도 200일 것(옛 HTML 보유자 보호)
- `/`·`/privacy`에 `no-cache`가 붙고, `/health` 같은 API 응답은 영향받지 않을 것

## 다음에 볼 것

배포 후 화면이 이상하면 순서대로 확인한다.

1. **`/health`의 `build`** — 배포 자체가 됐는지
2. **`git show origin/main:<파일> | grep <변경 표식>`** — 그 커밋에 원하는 변경이
   실제로 들었는지. 병합됐다는 사실과 내용이 들었다는 사실은 다르다
3. **브라우저 콘솔** — 최상위 예외 하나가 화면 전체를 죽인다
4. **`fetch`로 캐시 우회 비교** — 서버가 주는 파일과 브라우저가 쓰는 파일의 크기가
   다르면 캐시 문제다

## 함께 볼 문서

- [2026-08-19 작업 기록](2026-08-19-ui-and-key-rotation.md) — 이 배포에 담긴 변경
- [맥미니 배포 가이드](deploy-mini.md) — 이미지 갱신 절차
