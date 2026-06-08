# 매뉴얼 전용 답변과 QnA 폴백 설계

작성일: 2026-06-05

## 배경

처장 지침으로 챗봇의 동작 목표가 바뀌었다. 질문자의 말투나 표현을 고려해 폭넓게 응대하던 방향을 접고, 노션 매뉴얼에서 근거를 찾은 질문만 정확히 답한다. 그 외에는 답을 만들지 않고 QnA 게시판으로 안내한다.

그동안 만든 말투·표현 강건성 기능(인사 응대, 범위/역량 안내, 구어체 폴백, 토픽 택소노미)은 백업 프로젝트(lms-chatbot-backup-2026-06-05)에 보존한다. 작업본에서는 제거한다.

## 목표

- 매뉴얼에 근거가 있는 질문은 정확히 답한다(기존 검색·생성·이미지 격리 유지).
- 근거가 없으면 답을 지어내지 않고 QnA 게시판 링크로 안내한다.
- 시스템·모델에 대한 메타 질문은 기존처럼 거절한다.

## 비목표

- 말투·표현 강건성(인사·범위·역량·구어체 대응)은 더 이상 제공하지 않는다.
- QA 하니스 재설계는 이번 범위가 아니다. 별도 spec/plan으로 진행한다.
- 검색 임계값(ABS_EMBED_FLOOR 등)과 임베딩 모델은 바꾸지 않는다.

## 새 라우팅 모델 (generation/stream.py)

```
1. is_meta_question  → META_REPLY (시스템·모델 질문 거절, 유지)
2. hybrid_search → grounding 게이트(기존 ABS_EMBED_FLOOR / SCORE_THRESHOLD 그대로)
     · 통과 → 매뉴얼 기반 답변 생성 (섹션 이미지 격리 유지)
     · 미달 → QnA 게시판 안내 + 링크
```

제거되는 검색 전 분기: is_help_request, is_social_chitchat, is_scope_question, match_topic, topic_for_fallback. 인사·잡담·범위·역량·오프토픽은 모두 검색 게이트에서 미달로 떨어져 QnA 안내로 간다.

## QnA 폴백

- config에 `QNA_BOARD_URL` 추가. 환경변수에서 읽고 기본값은 빈 문자열.
- 기존 `NO_GUIDE_MSG`("교육혁신처 교수학습개발센터로 문의 부탁드립니다")를 QnA 안내 메시지로 교체한다.
- 메시지 구성:
  - URL이 있으면: "해당 내용은 매뉴얼에서 확인되지 않습니다. 자세한 문의는 QnA 게시판을 이용해 주세요: {QNA_BOARD_URL}"
  - URL이 비어 있으면 링크 없이: "해당 내용은 매뉴얼에서 확인되지 않습니다. 자세한 문의는 QnA 게시판을 이용해 주세요."
- 메시지 생성은 순수 함수로 분리해 단위 테스트가 가능하게 한다(URL 유무 두 경우).

## 제거 대상 (백업본에 보존됨)

- generation/guardrail.py: is_help_request, is_social_chitchat, is_scope_question 및 관련 정규식·상수(SOCIAL_REPLY 포함). is_meta_question 과 META_REPLY 는 유지.
- generation/suggestions.py: 토픽 택소노미 전체(_TOPICS, build_help_reply, build_topic_reply, match_topic, topic_for_fallback). 파일이 통째로 미사용이면 파일을 제거한다.
- generation/stream.py: 위 함수 import 와 검색 전 분기 호출 제거. topic_for_fallback 폴백 제거.
- 관련 테스트 정리: tests/test_suggestions.py 제거, tests/test_social.py 에서 social/scope/help 관련 테스트 제거(메타 관련 테스트는 유지하거나 test_guardrail.py 로 이동), tests/test_stream.py 에서 scope/topic 폴백 테스트 제거.

## 유지 대상

- is_meta_question / META_REPLY
- hybrid_search, 생성 파이프라인, persona(매뉴얼 컨텍스트 내에서만 답변)
- 섹션 단위 청킹과 이미지 격리(직전 작업)

## 예상 동작과 트레이드오프

- 매뉴얼에 답이 있어도 질문이 짧거나 표현이 모호해 임베딩 근거가 바닥 미만이면 QnA로 안내된다(예: "로그인 안됨"). 이는 새 방향이 받아들이는 트레이드오프다. 답을 지어내기보다 QnA로 보내는 쪽을 택한다.
- 인사·잡담도 QnA 안내를 받는다. 말투 대응은 목표가 아니다.

## 테스트

- QnA 메시지 순수 함수: URL 있음/없음 두 경우.
- 라우팅(tests/test_stream.py): 근거 미달 입력이 QnA 안내로 가는지, 메타 질문이 여전히 거절되는지, 근거 있는 질문이 생성 경로로 가는지.
- 제거된 함수에 대한 테스트는 함께 삭제한다.

## 영향 범위 (파일)

- config.py — QNA_BOARD_URL 추가
- generation/stream.py — 라우팅 단순화, QnA 폴백 메시지
- generation/guardrail.py — social/scope/help 술어 제거
- generation/suggestions.py — 토픽 택소노미 제거(또는 파일 삭제)
- tests/ — 관련 테스트 정리

## 후속 (별도 작업)

- QA 하니스 재설계: 기존 social/scope/paraphrase/conversation 프로파일을 대체해 (a) 매뉴얼 답변 정확성과 (b) 비답변 → QnA 폴백 두 가지를 검증한다. 별도 spec/plan으로 진행한다.
