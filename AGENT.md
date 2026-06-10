# AGENT.md — LMS 챗봇

본 코드베이스에서 작업하는 AI 에이전트와 인간 개발자를 위한 메타 지시 문서.

## 한 문단 요약
동서대학교 LearningX LMS 사용 매뉴얼(교수자용 상세 가이드 + LMS FAQ)을 검색 근거로 사용해, 교수자가 "이 기능 어떻게 쓰나요?" 류 질문을 했을 때 본문 설명 + 캡처 이미지로 답하는 RAG 챗봇. Phase 1 은 6월 초 보고용 라이브 시연 MVP.

## 신뢰 경계
- 답변은 인덱싱된 가이드북 내용으로만 한다. 모델의 일반 LMS·교육학 지식으로 추론하지 않는다.
- 검색 결과 신뢰도가 임계값 미만이면 LLM 호출 없이 정형 안내 메시지를 반환한다.

## 응답 규칙 (RESPONSE_RULES — generation/persona.py 의 시스템 프롬프트에 동일 반영)
1. 존대 + 격식체 ("~합니다", "~하시면 됩니다"). "님" 호칭 불사용.
2. 마크업 금지: 굵게(`**`), 기울임(`*`), 헤딩(`#`). 단계 안내용 숫자 리스트는 허용.
3. 이모티콘·이모지 출력 금지. 가이드 원문의 장식 이모지(🟠 등)도 옮기지 않는다.
4. 답변 말미에 참조한 가이드 페이지 제목을 한 줄로 표기.
5. 가이드 범위 외 질문은 정중히 거절. 일반 지식 추론 금지.

## 전처리 룰 (PREPROCESS_RULES — ingest/preprocess.py 에 동일 반영)
1. 유니코드 이모지 전 범위 제거 (한국어 본문에 의미 있는 이모지 거의 없음).
2. Notion artifact 정리: 헤딩 접미 마커 `(📄)`, 단독 `---` 라인, `<aside>...</aside>` callout → 일반 문단.
3. 외부 링크는 텍스트만 남기고 URL 제거. 단, 이미지 링크 `![](path)` 는 보존.
4. 연속 공백·줄바꿈 축약.
5. 이중 안전망: LLM 응답에서도 generation/filters.py 가 이모지·금지 마크업을 후처리로 제거.

## 검색 정책
- 청크 기본 단위: .md 1개 파일(=Notion 1개 페이지). 2,000 토큰 초과 시 H2 기준 분할.
- CSV 행 단위: 1행 = 1청크 (FAQ 질문 + 메타 태그).
- 하이브리드 점수: `BM25_norm * 0.4 + embed_sim * 0.6`. 점수 1위 문서의 청크만 최대 5개가 LLM 컨텍스트로 들어감 (1 질문 : 1 문서).
- 검색·게이트·LLM 옵션의 모든 수치는 `tuning.py` 에서 단일 관리 (실측 근거 주석 포함).
- 게이트 순서: 메타 질문 가드 → 임베딩 절대 바닥(ABS_EMBED_FLOOR)·정규화 임계(SCORE_THRESHOLD) → 애매 구간(< ABS_EMBED_CONFIDENT)만 LLM 관련성 게이트 → FAQ 문서면 원문 직출력, 가이드 문서면 LLM 생성.

## 이미지 동반 정책
- 응답은 SSE 이벤트 스트림: `text`(델타) → `text_final`(정제 전문) → `done`(images, sources, score) → `turn_id`.
- 이미지: 답변에 쓴 1순위 문서의 전 섹션 `image_refs` 를 seq 순으로 최대 5장(`tuning.MAX_IMAGES`). 조회 실패 시 컨텍스트 청크 이미지로 폴백. 폴백 답변에는 이미지·출처를 붙이지 않음.
- 출처: 1 질문 : 1 문서 — 문서 단위 제목·노션 링크 한 건만 노출 ('FAQ —' 접두 문서는 제외).

## 로깅과 개인정보
- SQLite (`data/chat_logs.db`): sessions / turns / feedback.
- 저장 항목: 질의·응답·시각·표시명(선택)·피드백·운영 메타데이터. 실명·학번·이메일·IP 수집 없음.
- 보유 기간 6개월. 동의 철회 시 해당 세션 즉시 삭제.
- 수집 목적은 ①가이드 업데이트 우선순위 도출 ②응답 품질 모니터링 으로만 한정. 모델 학습에 활용하지 않음 (개보법상 별도 동의 필요).
- 처리방침: `docs/privacy.md`. 첫 진입 시 동의 모달에서 항목별 분리 고지.
- 책임자: 김강민. 문의처: 동서대학교 교육혁신처 교수학습개발센터.

## 개발 워크플로
- 가이드 업데이트 시: 새 export 를 `data/raw/` 에 넣고 `python -m ingest.cli` 재실행 (idempotent).
- 모델 교체: `.env` 의 `OLLAMA_MODEL` 변경. 코드 수정 불필요 (`generation/stream.py` 는 RagState 경유로만 모델명을 받음).
- 품질 튜닝(임계값·가중치·LLM 옵션): `tuning.py` 만 수정.
- 추후 GPU 서버 이전: `.env` 의 `OLLAMA_HOST` 만 변경.
- 새 의존성 추가 시 `requirements.txt` 갱신 후 PR 에 이유 명시.

## 디렉터리 맵
- `config.py` 배포 환경 설정 (env 단일 진입점, AppConfig)
- `tuning.py` 품질 튜닝 노브 단일 관리 (임계값·가중치·LLM 옵션)
- `app_types.py` 횡단 데이터 타입 (Chunk, Retrieval, ChatEvent …)
- `ingest/` 정제된 청크까지. 임베딩은 하지 않음
- `index/` 임베딩 + BM25 인덱스 빌드/저장
- `retrieval/` 인덱스에서 검색만 (hybrid_search, doc_image_refs)
- `generation/` 검색 결과 + LLM 결합 + 후처리 (ollama.py 가 HTTP 클라이언트)
- `rag/` RagState 정의·로드 (서버가 기동 시 1회)
- `db/` SQLite 스키마와 DAO
- `qa/` QA 러너 (devtools-qa-runner 서브모듈) + 프로파일
- `backend.py` FastAPI 얇은 wrapper
- `static/` index.html(마크업) + css/app.css + js/{api,ui,main}.js (통신/렌더/배선)
- `docs/` spec, plans, privacy
- `tests/` 순수 함수 위주 pytest
