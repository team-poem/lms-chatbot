# 모델 버전 고정 결정 — `-latest` 별칭을 쓰지 않는다

**날짜**: 2026-08-12
**결정**: 생성 모델은 `gemini-2.5-flash` 로 고정한다. `gemini-flash-latest` 같은
별칭은 쓰지 않는다. 임베딩 모델도 마찬가지로 고정한다(이유는 다르다, 아래 참조).

## 무슨 일이 있었나

생성 모델을 `gemini-flash-latest` 로 바꿔 최신 모델을 자동으로 따라가게 하려 했다.
전환 직후 실제 API 를 호출해 보니 **모든 생성 요청이 HTTP 400 으로 실패**했다.

원인은 모델이 바뀐 것 자체가 아니라 **API 계약이 함께 바뀐 것**이었다.

| 요청 | `gemini-2.5-flash` | `gemini-flash-latest`(= `gemini-3.6-flash`) |
|---|---|---|
| `thinkingConfig.thinkingBudget = 0` | OK | **HTTP 400** `Request contains an invalid argument.` |
| `thinkingBudget = 128` | OK | OK |
| `thinkingConfig` 생략 | OK | OK |

`generation/gemini.py` 의 `to_generation_config()` 는 `thinkingBudget` 을 **항상**
넣는다(기본값 0). 그래서 별칭을 켜는 순간 답변 생성과 관련성 게이트 호출이 전부
깨진다.

```python
cfg["thinkingConfig"] = {"thinkingBudget": options.get("thinking_budget", 0)}
```

`thinkingBudget=0` 은 의도적인 선택이었다 — 이 앱의 두 LLM 호출(가이드 발췌 요약,
예/아니오 이진 판정)은 근거가 컨텍스트에 다 주어진 추출형이라 사고 토큰이 지연과
비용만 늘린다. 그 판단은 지금도 유효하다.

## 왜 위험했나 — 조용히 깨진다

`generation/gemini.py` 의 `chat_stream` 은 의도적으로 `raise_for_status()` 를
부르지 않는다. 에러 응답은 델타 없이 자연 종료되고 호출부(`generation/stream.py`)가
빈 답변을 폴백으로 처리한다. 즉 **400 이 예외로 드러나지 않고 "답변이 비어 있다"
로만 나타난다.** 로그에도 원인이 남지 않는다.

별칭을 쓴 채 배포했다면 학기 중 어느 날 구글이 별칭을 넘기는 순간, 에러 하나 없이
챗봇이 모든 질문에 빈 답변을 내놓기 시작했을 것이다.

## 결정과 근거

**고정한다.** `-latest` 의 장점(자동 업그레이드)보다 다음 손실이 크다.

1. **API 계약이 예고 없이 바뀐다.** 이번 건이 실물 사례다. 모델 성향 변화만 걱정하면
   됐을 줄 알았는데 요청 스키마 호환성까지 깨졌다.
2. **임계값이 실측 기반이다.** `tuning.py` 의 `ABS_EMBED_FLOOR`·`ABS_EMBED_CONFIDENT`
   와 관련성 게이트 프롬프트는 특정 모델로 재서 맞춘 값이다. 모델이 흔들리면 근거가
   사라진다.
3. **A/B 비교가 불가능해진다.** `scripts/embed_baseline.py` 로 전후 분포를 재는 중인데,
   밑바닥 모델이 움직이면 비교 자체가 성립하지 않는다.
4. **교수자 대상 서비스다.** 학기 중 답변 품질이 예고 없이 변하는 것을 감당하기 어렵다.

## 그럼 모델을 어떻게 올리나

별칭에 맡기지 말고 **사람이 정해서 올린다**. 절차는 이렇다.

1. 새 모델을 `.env` 의 `GEMINI_MODEL` 에 **명시적으로** 지정한다 (예: `gemini-3.6-flash`).
   별칭이 아니라 버전을 적는다.
2. 요청 호환성을 먼저 확인한다 — 특히 `thinkingConfig`. 아래 스니펫으로 한 번 찔러본다.
3. `scripts/embed_baseline.py` 와 QA 러너로 품질을 재고 기존 기준선과 비교한다.
4. `tuning.py` 임계값이 여전히 유효한지 확인한다. 아니면 재보정한다.
5. 통과하면 커밋한다.

```bash
# 요청 호환성 빠른 확인 (모델명만 바꿔가며)
curl -s -H "x-goog-api-key: $GEMINI_API_KEY" -H 'Content-Type: application/json' \
  -d '{"contents":[{"role":"user","parts":[{"text":"ping"}]}],
       "generationConfig":{"maxOutputTokens":16,"thinkingConfig":{"thinkingBudget":0}}}' \
  "https://generativelanguage.googleapis.com/v1beta/models/<모델명>:generateContent"
```

## 임베딩은 이유가 다르다

임베딩도 고정하지만 근거가 더 강하다. 임베딩 모델이 바뀌면 **벡터 공간이 달라져
기존 chroma 인덱스가 통째로 무효**가 된다. 검색이 실패하는 게 아니라 **엉뚱한 문서를
자신 있게 찾아오기 시작한다** — 에러도 나지 않는다. 다행히 Gemini 임베딩에는
`-latest` 별칭이 아예 없다(2026-08-12 기준 `gemini-embedding-001`,
`gemini-embedding-2`, `gemini-embedding-2-preview` 셋뿐).

## 후속 조치 — 조용한 실패 봉쇄 (완료)

이번 사고를 진단 불가능하게 만든 구조를 손봤다. **폴백 동작은 그대로 두고 원인만
로그로 남긴다.**

- `generation/gemini.py` · `generation/ollama.py` 의 `chat_stream`: 응답이 4xx/5xx 면
  본문 앞부분과 모델명을 stderr 에 남기고 델타 없이 종료한다(종전과 동일한 빈 답변
  폴백).
- `generation/relevance.py`: 게이트 실패 시 `None`(통과)은 유지하되 예외 종류와
  메시지를 남긴다. 이 게이트가 조용히 항상 열리면 환각 방어선이 사라지는데,
  증상만으로는 알 수 없었다.

실제 재현으로 확인했다:

```
[gemini.chat_stream] HTTP 400 model=gemini-flash-latest :: {
  "error": { "code": 400, "message": "Request contains an invalid argument.", ... }
}
```

회귀 테스트는 `tests/test_gemini.py` 의
`test_stream_logs_http_error_but_keeps_empty_fallback` 와 성공 경로가 조용한지 보는
`test_stream_success_path_logs_nothing`.
