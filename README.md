# LMS 챗봇 (Phase 1 MVP)

동서대학교 LearningX LMS 사용 매뉴얼 기반 교수자 응대 챗봇.

## 빠른 시작

1. Ollama 설치 후 모델 받기: `ollama pull gemma3:4b`
2. Notion 가이드북 export(Markdown & CSV ZIP)를 `data/raw/` 에 둠
3. 인덱싱: `.venv/bin/python -m ingest.cli`
4. 서버 실행: `./run.sh`
5. 브라우저: http://localhost:8080

자세한 구성은 `AGENT.md` 와 `docs/superpowers/specs/` 참조.
