# LMS 챗봇 — 단일 스테이지 이미지
# 베이스: Python 3.11 (3.14는 Linux ARM 휠이 아직 미흡), Debian slim
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# chromadb/sentence-transformers 빌드 시 필요한 최소 시스템 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 의존성 레이어 캐시 (코드 변경 때마다 재설치 안 되게 분리)
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# BGE-M3 임베딩 모델을 이미지에 굽기 — 부팅 시 다운로드 대기 없음.
# (대신 이미지 크기 ~2GB 증가. 의도된 트레이드오프.)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

# 애플리케이션 코드 (data/, .venv/ 등은 .dockerignore 로 제외)
COPY backend.py ./
COPY ingest ./ingest
COPY index ./index
COPY retrieval ./retrieval
COPY generation ./generation
COPY db ./db
COPY static ./static

# 데이터 디렉터리 (실제 데이터는 docker-compose 의 volume 마운트로 주입)
RUN mkdir -p data/raw data/assets data/chroma

# 컨테이너 기본 환경. docker-compose 의 environment 로 덮어쓸 수 있음.
ENV OLLAMA_HOST=http://host.docker.internal:11434 \
    OLLAMA_MODEL=gemma3:4b \
    EMBED_MODEL=BAAI/bge-m3 \
    CHROMA_DIR=/app/data/chroma \
    BM25_PATH=/app/data/bm25.pkl \
    LOGS_DB_PATH=/app/data/chat_logs.db \
    ASSETS_DIR=/app/data/assets \
    RAW_DIR=/app/data/raw \
    PORT=8080

EXPOSE 8080

# 콜드 스타트(BGE-M3 로드)에 최대 2분 허용
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8080"]
