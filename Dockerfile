# LMS 챗봇 — multi-stage 빌드로 슬림화 (5.7GB → 약 2.2GB)
#
# 1) builder 스테이지: 빌드 도구 + torch CPU-only + 의존성 + BGE-M3 baked
#    (불필요한 모델 변형 onnx/pytorch_model.bin 등 제거)
# 2) runtime 스테이지: 베이스 + venv 사본 + 모델 캐시 + 앱 코드
#    (gcc/build-essential 미포함, curl 만 healthcheck 용)

# ============= builder =============
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 격리된 venv 에 설치 → 그대로 runtime 스테이지로 복사 가능
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 1) torch 를 CPU 전용 휠로 먼저 (이후 sentence-transformers 가 이미 설치된 torch 재사용)
#    공식 torch 휠은 CUDA 라이브러리 ~2GB 동봉 — Mac mini 에선 쓸모 없음
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2) 나머지 의존성
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 3) BGE-M3 모델 baked + 안 쓰는 변형 제거
#    .safetensors 만 유지, onnx/pytorch_model.bin/colbert/sparse 가중치 삭제
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')" \
 && find /opt/hf -name "*.onnx" -delete 2>/dev/null || true \
 && find /opt/hf -name "*.onnx_data" -delete 2>/dev/null || true \
 && find /opt/hf -name "pytorch_model.bin" -delete 2>/dev/null || true \
 && find /opt/hf -name "colbert_linear.pt" -delete 2>/dev/null || true \
 && find /opt/hf -name "sparse_linear.pt" -delete 2>/dev/null || true \
 && find /opt/hf -type d -name "onnx" -exec rm -rf {} + 2>/dev/null || true \
 && find /opt/hf -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
 && du -sh /opt/hf /opt/venv

# ============= runtime =============
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf \
    PATH="/opt/venv/bin:$PATH"

# healthcheck 용 curl 만 (build-essential 미포함)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 빌더에서 venv + 모델 캐시 그대로 복사 (절대 경로 동일하게)
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf /opt/hf

# 애플리케이션 코드
# 루트 레벨 모듈(app_types/config)·rag 패키지 누락 시 backend import 단계에서
# ModuleNotFoundError 로 컨테이너가 부팅 즉시 크래시함. 런타임 import 폐포 전체를 복사.
COPY backend.py app_types.py config.py ./
COPY ingest ./ingest
COPY index ./index
COPY retrieval ./retrieval
COPY generation ./generation
COPY rag ./rag
COPY db ./db
COPY static ./static

RUN mkdir -p data/raw data/assets data/chroma data/logs

ENV OLLAMA_HOST=http://host.docker.internal:11434 \
    OLLAMA_MODEL=gemma3:4b \
    EMBED_MODEL=BAAI/bge-m3 \
    CHROMA_DIR=/app/data/chroma \
    BM25_PATH=/app/data/bm25.pkl \
    LOGS_DB_PATH=/app/data/logs/chat_logs.db \
    ASSETS_DIR=/app/data/assets \
    RAW_DIR=/app/data/raw \
    PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8080"]
