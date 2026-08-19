# lms-chatbot-devtools-qa

Chrome DevTools for Agents CLI만 사용해서 `lms-chatbot`을 조작하고 검증하는 실험용 QA 러너입니다.

기존 `qa/lms-chatbot-qa`는 Playwright가 사용자 행동을 실행하고 DevTools가 증거를 수집하는 하이브리드 방식입니다. 이 러너는 `chrome-devtools` CLI의 `take_snapshot`, `fill`, `click`, `press_key`, `emulate`, `take_screenshot`, `list_console_messages`, `list_network_requests`, `lighthouse_audit`만으로 사용자 행동과 증거 수집을 모두 수행합니다.

## 실행

```bash
npm run qa:chatbot:devtools -- --url https://<배포 호스트> --timeout 120000
```

## 현재 시나리오

- 개인정보 동의 모달 처리(snapshot에서 버튼/입력 uid를 찾아 fill/click)
- 기본 질문 전송(fill + Enter)
- 빈 입력 방어 확인
- 모바일 viewport emulation 후 질문 전송
- console/network/Lighthouse/screenshot/snapshot 수집

## 산출물

```txt
reports/lms-chatbot-devtools-qa/latest/
├── qa-report.md
├── chrome-devtools-qa.json
├── screenshots/
├── snapshots/
└── lighthouse/
```

## 주의

- 이 러너는 Chrome DevTools CLI의 accessibility snapshot uid에 의존합니다.
- Playwright보다 제어 API가 제한적이라 복잡한 조건 대기/route mock/세밀한 assertion은 어렵습니다.
- 대신 “Chrome DevTools for Agents만으로 실제 브라우저 QA가 가능한가”를 검증하는 데 목적이 있습니다.
