"""프론트엔드 자산의 캐시 재검증.

Cache-Control 이 없으면 브라우저가 휴리스틱 캐싱을 해서, 배포를 해도 이미 방문한
사용자는 옛 화면을 계속 본다(빌드 해시만 최신이고 화면은 옛것). index.html 이
자산을 버전 없는 경로로 참조하므로 URL 로는 캐시를 깰 수 없어, 헤더가 유일한
방어선이다. 회귀하면 조용히 옛 UI 가 배포된 것처럼 보이므로 테스트로 고정한다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend


@pytest.fixture(scope="module")
def client():
    # lifespan(모델·인덱스 로드)을 태우지 않는다 — 헤더만 보는 테스트다.
    return TestClient(backend.app)


@pytest.mark.parametrize("path", ["/", "/privacy", "/static/css/app.css", "/static/js/main.js"])
def test_frontend_assets_must_revalidate(client, path):
    assert client.get(path).headers.get("cache-control") == "no-cache"


def test_health_is_not_touched(client):
    # 미들웨어가 API 응답까지 건드리면 안 된다.
    assert "cache-control" not in client.get("/health").headers
