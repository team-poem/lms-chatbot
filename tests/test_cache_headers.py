"""프론트엔드 자산 캐시 방어.

배포 후 HTML 만 갱신되고 JS 가 캐시에서 오면 페이지가 통째로 죽는다 — 2026-08-19
실측: 옛 main.js 가 새 HTML 에 없는 `#agree` 에 addEventListener 를 걸다 TypeError 로
모듈이 중단됐고 추천 질문·세션 발급·입력창 활성화가 전부 실행되지 않았다.

두 겹을 고정한다: (1) 자산 경로에 빌드 해시가 들어가고 index.html 이 그 경로를
가리킬 것, (2) index.html 자신은 매번 재검증할 것.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend


@pytest.fixture(scope="module")
def client():
    # lifespan(모델·인덱스 로드)을 태우지 않는다 — 라우팅과 헤더만 보는 테스트다.
    return TestClient(backend.app)


def test_index_points_at_versioned_assets(client):
    html = client.get("/").text
    assert f'"{backend.STATIC_PREFIX}/js/main.js"' in html
    assert f'"{backend.STATIC_PREFIX}/css/app.css"' in html
    # 버전 없는 경로가 index.html 에 남아 있으면 캐시가 그대로 맞아버린다.
    assert '"/static/js/' not in html and '"/static/css/' not in html


@pytest.mark.parametrize("name", ["js/main.js", "js/ui.js", "js/api.js", "css/app.css"])
def test_versioned_path_serves_assets(client, name):
    # ui.js·api.js 는 main.js 가 상대경로로 import 한다. 경로 접두라야 이들까지
    # 같은 버전으로 따라온다(쿼리 스트링으로는 안 되는 이유).
    assert client.get(f"{backend.STATIC_PREFIX}/{name}").status_code == 200


def test_unversioned_static_still_served(client):
    # 캐시에 남은 옛 HTML 이 이 경로로 찾아온다. 404 로 만들면 그 사용자는 빈 화면을 본다.
    assert client.get("/static/js/main.js").status_code == 200


@pytest.mark.parametrize("path", ["/", "/privacy"])
def test_html_must_revalidate(client, path):
    assert client.get(path).headers.get("cache-control") == "no-cache"


def test_api_response_is_not_touched(client):
    assert "cache-control" not in client.get("/health").headers
