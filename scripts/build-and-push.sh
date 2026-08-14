#!/usr/bin/env bash
# 개발 머신에서 이미지를 빌드하고 Docker Hub 에 푸시.
#
# 선행 셋업:
#   - Docker Desktop 에 amazon7737 계정으로 로그인되어 있어야 함 (이미 OK).
#     문제 시: docker login -u amazon7737
#
# 사용:
#   ./scripts/build-and-push.sh                       # latest 태그
#   ./scripts/build-and-push.sh v0.2                  # 명시적 버전 태그
#
# 빌드 플랫폼: Apple Silicon Mac mini 대상 → linux/arm64
# (Intel Mac mini 면 PLATFORM=linux/amd64 로 실행)

set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${IMAGE:-amazon7737/lms-chatbot}"
PLATFORM="${PLATFORM:-linux/arm64}"
TAG="${1:-latest}"

echo "==> 빌드: $IMAGE:$TAG ($PLATFORM)"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  GIT_SHA="$GIT_SHA-dirty"   # 커밋 안 된 변경이 섞였음을 이미지에 남긴다
fi
echo "==> 커밋: $GIT_SHA"

docker buildx build \
  --platform "$PLATFORM" \
  --build-arg "GIT_SHA=$GIT_SHA" \
  --tag "$IMAGE:$TAG" \
  --push \
  .

echo "==> 완료. 맥미니에서:"
echo "    docker compose pull && docker compose up -d"
