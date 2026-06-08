# 첫 진입 FAQ 질문 제안 — 설계

작성일: 2026-06-08
브랜치: fix/faq-answer-quality

## 배경 / 문제

그동안 답변 파이프라인과 첫 진입 UI에 로직이 "덕지덕지" 쌓이면서 두 가지 문제가 생겼다.

1. **답변 가드레일 과작동** — `generation/stream.py` 에 절대 임베딩 유사도 바닥
   (`ABS_EMBED_FLOOR = 0.60`) 게이트가 추가되면서, 실제 FAQ 질문조차 폴백
   메시지(QnA 게시판 안내)로 떨어져 **답을 아예 하지 않는** 상태가 되었다.
2. **첫 진입 UI 과설계** — 카테고리 → 드릴다운 → 가이드 문서 뷰어(`/catalog`,
   `/guide`)로 구성된 무거운 카탈로그 메뉴가 쌓였다.

결론: **덜어내기**. 답변 동작은 main 시점으로 되돌리고, 첫 진입은 단순한 FAQ
질문 제안으로 교체한다.

## 목표

- 답변 파이프라인을 main 상태로 복원해 정상적으로 답하게 한다.
- 첫 진입 시 노션 교수자 매뉴얼 FAQ DATABASE의 질문 중 **5~7개를 무작위**로
  보여주고, 안내문과 함께 클릭으로 질문할 수 있게 한다.

## 변경 사항

### A. 답변 파이프라인 복원
- `generation/stream.py` 를 main 으로 복원(ABS_EMBED_FLOOR 게이트,
  `_has_grounding`, `_qna_fallback_msg`, `_section_images`, `max_embed_sim`
  분기 제거 → `NO_GUIDE_MSG` + `top_score < SCORE_THRESHOLD` 단일 게이트).
- 더 이상 쓰이지 않는 `qna_board_url`/`qna_contact` 를 `config.py`·`rag/state.py`
  에서 제거. `/admin/logs` 가 쓰는 `admin_token` 은 유지.
- 인덱싱 관련 변경(`doc_title`/`seq`, `_chunk_from_meta`)은 무해하고 재인덱싱
  비용이 있어 유지한다(`hybrid_search` 가 계속 사용).

### B. 첫 진입 FAQ 제안
- 제거: `generation/catalog.py`, `generation/guide.py`, backend `/catalog`·
  `/guide` 라우트, `static/index.html` 카탈로그 UI, `tests/test_catalog.py`·
  `tests/test_guide.py`.
- 추가: `generation/faq.py` — FAQ DATABASE에서 추출한 80개 질문 baked +
  `sample_questions(n)` / `sample_for_entry()`(5~7개 무작위).
- backend `GET /faq` — `n` 미지정 시 5~7개, 지정 시 n개 반환.
- `static/index.html` — 첫 진입에 안내문 + 질문 칩. 칩 클릭 시 해당 질문을
  챗봇에 전송한다.

## 첫 진입 질문 선택 방법 (의사결정)

### 채택안 — 칩 클릭 → 챗봇에 질문 전송
칩을 누르면 그 질문이 일반 질의 흐름(`ask()` → `POST /chat`)을 그대로 타고
스트리밍 답변을 받는다. main의 QA 흐름을 재사용하므로 단순하고, "빠르게
답변해 드립니다"라는 안내문과 동작이 일치한다.

### 대안 (기록용) — 칩 클릭 → 가이드 문서 열기
칩을 누르면 해당 매뉴얼 문서를 뷰어로 그대로 보여주는 방식. LLM 생성 없이
정확한 원문을 보여줄 수 있다는 장점이 있으나, 가이드 문서 매핑·조립
인프라(`/guide`, `build_guide`, 문서 제목 매핑)가 필요해 이번 "덜어내기"
방향과 상충한다. 추후 정확도가 중요한 항목에 한해 선택적으로 도입할 수 있어
대안으로 남겨둔다.

## 랜덤 추출 위치
서버에서 매 진입마다 새로 추출한다(`GET /faq`). 클라이언트는 받은 질문을
그대로 렌더링한다 — 추출 로직 단일화, 진입마다 신선한 구성.

## 테스트
- `tests/test_faq.py` — 질문 로드 수(80) 고정, 중복 없음, `sample_questions`
  개수·중복·경계, `sample_for_entry` 개수 범위(5~7).
- `tests/test_stream.py` 는 main 으로 복원(복원된 stream.py와 정합).
