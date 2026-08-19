"""임베딩 백엔드 분기와 Gemini 임베딩 어댑터. 네트워크는 MockTransport 로 막는다.

회귀 표적 넷:
  1. 문서/질문 지시문이 갈리는가 (비대칭 모델의 검색 품질이 여기 달렸다)
  2. 반환 벡터가 단위벡터인가 (vector_store 의 `1 - d/2` 환산 전제)
  3. BATCH_LIMIT 넘는 입력이 순서를 지키며 나눠 가는가
  4. gemini 모드에서 torch 가 임포트되지 않는가 (저사양 배포의 핵심 전제)
"""
from __future__ import annotations

import functools
import math
import sys

import httpx
import pytest

from index import embed, gemini_embed
from index.embed import DOCUMENT, QUERY, EmbedConfig, build_embed_config, load_embedder


def _mock_httpx(monkeypatch, handler) -> None:
    """gemini_embed 가 직접 여는 Client 에 MockTransport 를 물린다."""
    monkeypatch.setattr(
        gemini_embed.httpx,
        "Client",
        functools.partial(httpx.Client, transport=httpx.MockTransport(handler)),
    )


def _ok(dim: int = 4):
    """요청 개수만큼 같은 크기의 비정규화 벡터를 돌려주는 핸들러."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        n = len(json.loads(request.content)["requests"])
        return httpx.Response(
            200, json={"embeddings": [{"values": [3.0] + [4.0] * (dim - 1)}] * n}
        )

    return handler


# ── 지시문 (문서 vs 질문) ────────────────────────────────────────────────


def test_document_and_query_get_different_instructions():
    # 이게 같아지면 비대칭 모델의 검색 품질이 조용히 떨어진다.
    doc = gemini_embed.instruct("출석 인정 기준", DOCUMENT)
    qry = gemini_embed.instruct("출석 인정 기준", QUERY)
    assert doc != qry
    assert "query:" in qry
    assert "text:" in doc


def test_document_instruction_includes_title_when_given():
    assert gemini_embed.instruct("본문", DOCUMENT, title="출결") == "title: 출결 | text: 본문"


def test_unknown_kind_raises():
    # 오타가 조용히 문서 인코딩으로 떨어지면 원인 추적이 어렵다.
    with pytest.raises(ValueError, match="kind"):
        gemini_embed.instruct("x", "docmuent")


# ── 정규화 ──────────────────────────────────────────────────────────────


def test_extract_embeddings_returns_unit_vectors():
    # vector_store 의 유사도 환산이 단위벡터를 전제한다.
    vecs = gemini_embed.extract_embeddings({"embeddings": [{"values": [3.0, 4.0]}]})
    assert vecs[0] == pytest.approx([0.6, 0.8])
    assert math.sqrt(sum(v * v for v in vecs[0])) == pytest.approx(1.0)


def test_zero_vector_survives_normalization():
    assert gemini_embed.l2_normalize([0.0, 0.0]) == [0.0, 0.0]


# ── 배치 ────────────────────────────────────────────────────────────────


def test_batches_split_and_preserve_order(monkeypatch):
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: None)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        reqs = json.loads(request.content)["requests"]
        seen.append(len(reqs))
        # 입력 텍스트를 벡터 첫 성분에 실어 순서 보존을 확인한다.
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    {"values": [float(r["content"]["parts"][0]["text"].split()[-1]), 0.0]}
                    for r in reqs
                ]
            },
        )

    _mock_httpx(monkeypatch, handler)
    texts = [f"doc {i}" for i in range(gemini_embed.BATCH_LIMIT + 5)]
    out = gemini_embed.embed_batch("k", "m", texts, kind=DOCUMENT)

    assert seen == [gemini_embed.BATCH_LIMIT, 5]
    assert len(out) == len(texts)
    # 정규화 후에도 부호·순서는 유지된다(첫 성분이 유일한 비영 성분).
    assert out[0][0] == 0.0          # "doc 0" → 영벡터라 그대로
    assert out[7][0] == pytest.approx(1.0)


def test_empty_input_makes_no_request(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("빈 입력에 요청을 보내면 안 된다")

    _mock_httpx(monkeypatch, handler)
    assert gemini_embed.embed_batch("k", "m", []) == []


def test_count_mismatch_raises(monkeypatch):
    # 응답이 조용히 짧으면 인덱스가 말없이 불완전해진다 — 시끄럽게 실패시킨다.
    _mock_httpx(
        monkeypatch,
        lambda req: httpx.Response(200, json={"embeddings": [{"values": [1.0]}]}),
    )
    with pytest.raises(RuntimeError, match="개수 불일치"):
        gemini_embed.embed_batch("k", "m", ["a", "b"])


def test_http_error_propagates(monkeypatch):
    # 429 는 재시도 대상이라 sleep 을 막지 않으면 백오프만큼 실제로 잠든다.
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: None)
    _mock_httpx(monkeypatch, lambda req: httpx.Response(429, json={"error": "quota"}))
    with pytest.raises(httpx.HTTPStatusError):
        gemini_embed.embed_batch("k", "m", ["a"])


# ── 설정 분기 ───────────────────────────────────────────────────────────


def test_default_provider_is_local(monkeypatch):
    # 임베딩 교체는 재인덱싱+임계값 재보정을 동반한다. 조용히 바뀌면 안 된다.
    monkeypatch.delenv("EMBED_PROVIDER", raising=False)
    assert build_embed_config().provider == embed.LOCAL


def test_llm_gemini_does_not_flip_embeddings(monkeypatch):
    # 생성 백엔드와 임베딩 백엔드는 독립이다.
    monkeypatch.delenv("EMBED_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert build_embed_config().provider == embed.LOCAL


def test_gemini_config_reads_its_own_model_env(monkeypatch):
    # EMBED_MODEL(BGE-M3용)이 gemini 모델명을 덮으면 안 된다.
    monkeypatch.setenv("EMBED_PROVIDER", "gemini")
    monkeypatch.setenv("EMBED_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    cfg = build_embed_config()
    assert cfg.model != "BAAI/bge-m3"
    assert cfg.model.startswith("gemini-embedding")


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("EMBED_PROVIDER", "gemeni")
    with pytest.raises(ValueError, match="EMBED_PROVIDER"):
        build_embed_config()


def test_gemini_without_key_fails_at_load(monkeypatch):
    # 부팅 때 잡는다 — 첫 질문까지 미루면 '검색이 빈다'로만 보인다.
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        load_embedder(EmbedConfig(provider="gemini", model="gemini-embedding-2"))


def test_string_arg_stays_local():
    # 기존 호출 load_embedder(config.embed_model) 하위호환.
    cfg = build_embed_config(provider=embed.LOCAL, model="BAAI/bge-m3")
    assert cfg.provider == embed.LOCAL and cfg.model == "BAAI/bge-m3"


# ── torch 미임포트 (저사양 배포의 전제) ──────────────────────────────────


def test_gemini_path_does_not_import_torch(monkeypatch):
    """gemini 임베더를 만들고 써도 torch 가 올라오지 않아야 한다.

    이게 깨지면 상주 메모리가 ~2.6GB 로 되돌아가 1GB 인스턴스 배포가 막힌다."""
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.delitem(sys.modules, "sentence_transformers", raising=False)

    _mock_httpx(monkeypatch, _ok())
    embedder = load_embedder(
        EmbedConfig(provider="gemini", model="gemini-embedding-2", api_keys=("k",), dim=4)
    )
    out = embed.encode_texts(embedder, ["안녕"], kind=QUERY)

    assert len(out) == 1
    assert "torch" not in sys.modules
    assert "sentence_transformers" not in sys.modules


def test_encode_texts_forwards_kind():
    """분기 층이 kind 를 삼키지 않는지. 삼키면 질문이 문서로 인코딩된다."""

    class Spy:
        def __init__(self):
            self.kinds: list[str] = []

        def encode(self, texts, kind):
            self.kinds.append(kind)
            return [[1.0]] * len(texts)

    spy = Spy()
    embed.encode_texts(spy, ["a"], kind=QUERY)
    embed.encode_texts(spy, ["b"])
    assert spy.kinds == [QUERY, DOCUMENT]


def test_retry_delay_prefers_server_hint():
    assert gemini_embed.retry_delay(0, "7") == 7.0
    assert gemini_embed.retry_delay(0, None) == gemini_embed.BACKOFF_BASE_S
    assert gemini_embed.retry_delay(2, None) == gemini_embed.BACKOFF_BASE_S * 4
    # 분당 창을 넘기되 무한정 늘지는 않는다
    assert gemini_embed.retry_delay(20, None) == gemini_embed.BACKOFF_CAP_S
    assert gemini_embed.BACKOFF_CAP_S > 60  # 분 단위 제한을 넘길 수 있어야 한다
    assert gemini_embed.retry_delay(0, "쓰레기") == gemini_embed.BACKOFF_BASE_S


def test_429_is_retried_then_succeeds(monkeypatch):
    """무료 티어는 분당 제한이 빡빡해 인덱싱 중 429 가 흔하다. 재시도가 없으면
    162청크 인덱싱이 첫 배치에서 통째로 죽는다."""
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
        return httpx.Response(200, json={"embeddings": [{"values": [1.0, 0.0]}]})

    _mock_httpx(monkeypatch, handler)
    out = gemini_embed.embed_batch("k", "m", ["a"])
    assert calls["n"] == 3
    assert out == [[1.0, 0.0]]


def test_400_is_not_retried(monkeypatch):
    """스키마 오류는 재시도해도 소용없다 — 즉시 올린다."""
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "bad"}})

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        gemini_embed.embed_batch("k", "m", ["a"])
    assert calls["n"] == 1


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": {}})

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        gemini_embed.embed_batch("k", "m", ["a"])
    assert calls["n"] == gemini_embed.MAX_RETRIES
