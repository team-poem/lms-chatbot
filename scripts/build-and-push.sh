#!/usr/bin/env bash
# 개발 머신에서 이미지를 빌드하고 ghcr.io 에 푸시.
#
# 선행 1회 셋업:
#   1. GitHub Personal Access Token (classic) 생성 — scope: write:packages, read:packages
#   2. 환경변수로 export 하거나 stdin 으로 전달:
#        echo "ghp_..." | docker login ghcr.io -u <github-username> --password-stdin
#
# 사용:
#   ./scripts/build-and-push.sh                       # latest 태그
#   ./scripts/build-and-push.sh v0.2                  # 명시적 버전 태그
#
# 빌드 플랫폼: Apple Silicon Mac mini 대상 → linux/arm64
# (Intel Mac mini 면 PLATFORM 환경변수로 linux/amd64 지정)

set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${IMAGE:-ghcr.io/team-poem/lms-chatbot}"
PLATFORM="${PLATFORM:-linux/arm64}"
TAG="${1:-latest}"

echo "==> 빌드: $IMAGE:$TAG ($PLATFORM)"
docker buildx build \
  --platform "$PLATFORM" \
  --tag "$IMAGE:$TAG" \
  --push \
  --provenance=false \
  .

echo "==> 완료. 맥미니에서:"
echo "    docker compose pull && docker compose up -d"
