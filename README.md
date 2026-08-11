# LMS 챗봇 (Phase 1 MVP)

동서대학교 LearningX LMS 사용 매뉴얼 기반 교수자 응대 챗봇.

## 브랜치 / 버전 관리

정식 버전 번호(semver)·태그 체계는 없으며 개발은 브랜치 단위로 진행한다. `main` 이
현재 배포/운영 버전이다. 아래는 2026-06-18 `git fetch origin` 기준 브랜치 현황이다
(브랜치↑N = 해당 브랜치가 `main` 에 아직 없는 커밋 수).

| 브랜치 | 최신 커밋 | main 반영 | 내용 |
|---|---|---|---|
| `main` | `0d0e583` (2026-06-30) | 배포/운영 기준 | **현재 배포/운영 버전.** `feat/consultation-flow`(PR #15)까지 병합됨 |
| `feat/gemini-flash-provider` | 작업 중 | 미병합 | 답변 생성 백엔드를 Gemini API 로 교체(`LLM_PROVIDER`). Ollama 는 옵션으로 보존, 임베딩은 로컬 BGE-M3 유지 |
| `feat/consultation-flow` | `81b3022` | ✅ 병합됨 (PR #15) | 선택형 상담 플로우 — 노드 선택 → 확정 답변 카드(`?mode=consult`). FAQ·가이드 원문 직출력(노드 경로 LLM 미사용), 기존 RAG는 폴백 보존 |
| `refactor/functional-cleanup` | `68bb4f4` (2026-06-12) | 미병합 (브랜치↑16) | 함수형 리팩터링 + devtools QA 러너 분리 |
| `fix/faq-answer-quality` | `4e0b629` (2026-06-10) | 미병합 (브랜치↑17) | FAQ 답변 품질 개선 + 함수형 리팩터링 2라운드 계획 |
| `feat/safety-guardrail` | `ef30015` (2026-06-01) | 미병합 (브랜치↑1) | 민감·악의 요청 안전 가드레일 (오래됨) |
| `release/question-depth` | `a3f790d` (2026-06-08) | ✅ 병합됨 (PR #5) | 질문 뎁스 가이드 네비게이션 **포함** 릴리스 |
| `release/not-question-depth` | `e6f87eb` (2026-06-08) | ✅ 병합됨 | 질문 뎁스 **미포함** 릴리스 |
| `chore/extract-devtools-qa-runner-submodule` | `5649e99` (2026-06-01) | ✅ 병합됨 | devtools-qa-runner 서브모듈 추출 |

태그 `backup-2026-06-05-before-pivot` (`72527e2`) — 방향 전환(pivot) 전 백업 스냅샷.

| `archive/gemma-llm-version` | `d5f8e4a` (2026-06-08) | 보존용 | Gemini 전환 전 gemma3:4b 기준 스냅샷 |

> 수치·날짜는 2026-08-02 GitHub API 조회 기준. 브랜치가 병합·갱신되면 이 표도 갱신한다.
> `refactor/functional-cleanup`·`fix/faq-answer-quality`·`feat/safety-guardrail` 은 여전히 미병합.

## 현재 상태 (2026-05-26)

- 설계 문서: `docs/superpowers/specs/2026-05-26-lms-chatbot-design.md` (HTML 동봉)
- 구현 계획: `docs/superpowers/plans/2026-05-26-lms-chatbot-phase1.md` (Task 1~17)
- 메타 지시: `AGENT.md`
- 코드: 인덱싱 → 하이브리드 검색 → RAG 파이프라인 → FastAPI 백엔드 → 동의 모달 UI → 처리방침 모두 구현
- 테스트: 28 passed (preprocess, chunk, BM25, hybrid, filters, DAO, extract)
- 162개 청크 인덱싱 완료 (현재 받은 LMS FAQ CSV 기준. LMS 상세 가이드 full export 받으면 더 추가)

## 답변 생성 백엔드

기본은 **Gemini API** (`LLM_PROVIDER=gemini`, 기본 모델 `gemini-2.5-flash`)다.
로컬 Ollama + gemma3:4b 로 되돌리려면 `.env` 에 `LLM_PROVIDER=ollama` 만 넣으면 된다
(gemma 시절 코드는 `archive/gemma-llm-version` 브랜치에도 보존).

- 키: https://aistudio.google.com/apikey → `.env` 의 `GEMINI_API_KEY`.
  gemini 인데 키가 비면 **부팅 시점에** 실패한다(첫 질문까지 미루지 않는다).
- 백엔드 분기는 `generation/llm.py` 한 곳. 어댑터는 `generation/gemini.py`,
  `generation/ollama.py` 이고 시그니처가 같다.
- **임베딩은 백엔드와 무관하게 항상 로컬 BGE-M3** 다. 임베딩까지 API 로 바꾸면
  벡터 공간이 달라져 기존 chroma 인덱스가 통째로 무효화된다.

## 라이브 시연을 위한 잔여 셋업

1. `GEMINI_API_KEY` 를 `.env` 에 설정
2. LMS 상세 가이드 full export 를 `data/raw/` 에 추가 후 재인덱싱: `.venv/bin/python -m ingest.cli`

## 빠른 시작

```bash
# 1) 의존성 설치 (최초 1회. 약 2~3분). uv 가 있으면 파이썬 3.11 을 자동으로 맞춘다
#    — 시스템 python3 가 3.9 면 chromadb/torch 설치가 깨진다.
./run.sh   # 의존성 자동 설치 후 서버 부팅

# 2) 인덱싱 (data/raw 에 Notion export ZIP 두고)
.venv/bin/python -m ingest.cli

# 3) 브라우저
open http://localhost:8080
```

## LLM 없이 검색 품질만 확인

```bash
.venv/bin/python -m retrieval.cli "퀴즈 출제하는 방법"
```

## 테스트

```bash
.venv/bin/pytest -q
```

## 도커 배포 (맥미니 등)

상세 절차: `docs/deploy-mini.md`

```bash
# 개발 머신에서 빌드 + ghcr 푸시
./scripts/build-and-push.sh

# 맥미니에서
docker compose pull && docker compose up -d
```

## 문서

- `AGENT.md` — 메타 지시 (응답 규칙, 전처리 룰, 검색 정책, 디렉터리 맵)
- `docs/superpowers/specs/` — 설계 문서
- `docs/superpowers/plans/` — 구현 계획서
- `docs/privacy.md` — 개인정보처리방침 전문 (`/privacy` 에서도 조회)
- `docs/deploy-mini.md` — 맥미니 도커 배포 가이드
