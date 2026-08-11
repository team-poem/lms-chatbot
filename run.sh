#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# 파이썬 3.11 고정 — Dockerfile 과 같은 버전이다. 시스템 python3 는 맥에 따라
# 3.9 라서 chromadb/sentence-transformers/torch 설치가 깨진다. uv 가 있으면
# 인터프리터까지 받아오므로 그쪽을 우선한다.
if [ ! -d .venv ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 .venv
    uv pip install --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
    uv pip install --python .venv/bin/python -r requirements.txt
  else
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
  fi
fi
if [ ! -f .env ]; then
  cp .env.example .env
fi
.venv/bin/python -m uvicorn backend:app --host 0.0.0.0 --port "${PORT:-8080}" --reload
