# LMS 챗봇 (Phase 1 MVP)

동서대학교 LearningX LMS 사용 매뉴얼 기반 교수자 응대 챗봇.

## 현재 상태 (2026-05-26)

- 설계 문서: `docs/superpowers/specs/2026-05-26-lms-chatbot-design.md` (HTML 동봉)
- 구현 계획: `docs/superpowers/plans/2026-05-26-lms-chatbot-phase1.md` (Task 1~17)
- 메타 지시: `AGENT.md`
- 코드: 인덱싱 → 하이브리드 검색 → RAG 파이프라인 → FastAPI 백엔드 → 동의 모달 UI → 처리방침 모두 구현
- 테스트: 28 passed (preprocess, chunk, BM25, hybrid, filters, DAO, extract)
- 162개 청크 인덱싱 완료 (현재 받은 LMS FAQ CSV 기준. LMS 상세 가이드 full export 받으면 더 추가)

## 라이브 시연을 위한 잔여 셋업

1. Ollama 설치 (이 머신에 미설치): `brew install ollama` 후 `ollama serve` (별도 터미널)
2. 모델 받기: `ollama pull gemma3:4b` (~3GB, 1회)
3. LMS 상세 가이드 full export 를 `data/raw/` 에 추가 후 재인덱싱: `.venv/bin/python -m ingest.cli`

## 빠른 시작

```bash
# 1) 의존성 설치 (최초 1회. 약 2~3분)
./run.sh   # 의존성 자동 설치 후 서버 부팅

# 2) 별도 터미널에서 ollama
ollama serve

# 3) 인덱싱 (data/raw 에 Notion export ZIP 두고)
.venv/bin/python -m ingest.cli

# 4) 브라우저
open http://localhost:8080
```

## Ollama 없이 검색 품질만 확인

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
