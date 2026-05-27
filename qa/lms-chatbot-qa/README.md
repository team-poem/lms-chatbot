# lms-chatbot-qa

`lms-chatbot` 전용 브라우저 QA CLI입니다. Playwright로 실제 페이지를 열고 챗봇 특화 smoke/adversarial 시나리오를 실행한 뒤 Markdown 리포트와 증거 파일을 남깁니다.

## 설치

```bash
npm install
npx playwright install chromium
```

## 실행

앱을 먼저 띄운 뒤:

```bash
npm run qa:chatbot -- --url http://localhost:8080 --mock-chat
```

실제 `/chat` 백엔드를 호출하려면 `--mock-chat`을 빼세요.

```bash
npm run qa:chatbot -- --url http://localhost:8080
```

Chrome DevTools for Agents CLI 증거 수집까지 같이 실행하려면 `--devtools`를 추가하세요.

```bash
npm run qa:chatbot -- --url http://localhost:8080 --timeout 120000 --devtools
```

`--devtools`는 `chrome-devtools-mcp` 패키지의 `chrome-devtools` CLI를 사용해서 별도 Chrome 세션에서 다음 증거를 수집합니다.

- accessibility snapshot
- DevTools screenshot
- DevTools console messages
- DevTools network requests
- Lighthouse snapshot audit(accessibility, best practices, SEO, agentic browsing)

## 산출물

기본 출력 디렉토리:

```txt
reports/lms-chatbot-qa/latest/
├── qa-report.md
├── console.json
├── network-failures.json
├── responses-4xx-5xx.json
└── screenshots/
```

## 현재 MVP 범위

- 개인정보 동의 모달 통과
- 기본 질문 전송
- 빈 입력 submit 방어 확인
- 긴 입력 전송
- 빠른 연속 입력
- 모바일 viewport에서 질문 전송
- console/page error 수집
- request failed 및 4xx/5xx 응답 수집
- 단계별 screenshot 및 Markdown 리포트 생성

## 의도적으로 제외한 것

- Lighthouse
- memory snapshot
- 완전 자율 탐색
- 세션 인계
- LLM 응답 품질 평가

이 항목들은 챗봇 상태 전이 QA가 안정화된 뒤 붙입니다.
