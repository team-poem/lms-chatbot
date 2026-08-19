"""키 로테이션. 무료 티어 쿼터(키마다 따로 참)를 여러 키로 넘기는 동작을 고정한다.

핵심 두 가지만 지킨다:
  1. 429 를 만나면 **기다리지 않고** 다음 키로 넘어간다.
  2. 살아난 키를 다음 요청에도 계속 쓴다(커서 유지). 매번 1번 키부터 시작하면
     이미 마른 키에 왕복을 계속 버린다 — 로테이션을 넣는 이유 자체가 사라진다.
"""
from __future__ import annotations

import asyncio
import functools

import httpx
import pytest

import gemini_keys
from gemini_keys import KeyRing, as_ring, from_env
from generation import gemini
from index import gemini_embed


# ── 링 자체 ────────────────────────────────────────────────────────
def test_blank_keys_are_dropped():
    # .env 에 `GEMINI_API_KEY3=` 만 남기는 일이 흔하다. 빈 키를 남겨두면 401 을
    # 맞고 그게 쿼터 소진으로 오인된다.
    ring = KeyRing(["a", "", "  ", "b"])
    assert (len(ring), ring.keys) == (2, ("a", "b"))


def test_rotate_cycles_and_reports_position():
    ring = KeyRing(["a", "b", "c"])
    assert (ring.current(), ring.position()) == ("a", 0)
    assert ring.rotate() and ring.current() == "b"
    assert ring.rotate() and ring.current() == "c"
    assert ring.rotate() and ring.current() == "a"   # 한 바퀴


def test_single_key_never_rotates():
    # 키가 하나면 바꿔봐야 같은 키다. 호출부는 이 False 로 '백오프하라'를 판단한다.
    ring = KeyRing(["only"])
    assert ring.rotate() is False and ring.current() == "only"


def test_empty_ring_is_falsy():
    assert not KeyRing([]) and KeyRing([]).current() == ""


def test_as_ring_accepts_plain_string():
    # 기존 호출·테스트가 문자열 하나를 그대로 넘긴다.
    assert as_ring("k").keys == ("k",)
    r = KeyRing(["a"])
    assert as_ring(r) is r


def test_from_env_reads_three_slots_in_order():
    ring = from_env({"GEMINI_API_KEY": "a", "GEMINI_API_KEY2": "b", "GEMINI_API_KEY3": "c"})
    assert ring.keys == ("a", "b", "c")
    assert gemini_keys.ENV_NAMES[0] == "GEMINI_API_KEY"   # 1번 슬롯 이름은 안 바뀐다


# ── 임베딩 경로 ────────────────────────────────────────────────────
def _mock_sync(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        gemini_embed.httpx, "Client",
        functools.partial(httpx.Client, transport=httpx.MockTransport(handler)),
    )


def _mock_async(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        gemini.httpx, "AsyncClient",
        functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )


def _key_of(request: httpx.Request) -> str:
    return request.headers["x-goog-api-key"]


QUOTA = {"error": {"status": "RESOURCE_EXHAUSTED"}}


def test_embed_rotates_to_next_key_without_sleeping(monkeypatch):
    """1번 키가 429 면 2번 키로 즉시 넘어간다. 백오프 sleep 은 일어나지 않는다."""
    slept: list[float] = []
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: slept.append(s))
    seen: list[str] = []

    def handler(request):
        seen.append(_key_of(request))
        if _key_of(request) == "k1":
            return httpx.Response(429, json=QUOTA)
        return httpx.Response(200, json={"embeddings": [{"values": [1.0, 0.0]}]})

    _mock_sync(monkeypatch, handler)
    ring = KeyRing(["k1", "k2"])
    out = gemini_embed.embed_batch(ring, "m", ["a"], dim=2)

    assert len(out) == 1
    assert seen == ["k1", "k2"]
    assert slept == []             # 살아 있는 키가 있는데 기다리면 안 된다
    assert ring.current() == "k2"  # 커서가 남는다


def test_embed_keeps_using_the_surviving_key(monkeypatch):
    """다음 호출은 1번 키를 다시 찔러보지 않는다(커서 유지)."""
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: None)
    seen: list[str] = []

    def handler(request):
        seen.append(_key_of(request))
        if _key_of(request) == "k1":
            return httpx.Response(429, json=QUOTA)
        return httpx.Response(200, json={"embeddings": [{"values": [1.0, 0.0]}]})

    _mock_sync(monkeypatch, handler)
    ring = KeyRing(["k1", "k2"])
    gemini_embed.embed_batch(ring, "m", ["a"], dim=2)
    seen.clear()
    gemini_embed.embed_batch(ring, "m", ["b"], dim=2)

    assert seen == ["k2"]


def test_embed_backs_off_only_when_every_key_is_dry(monkeypatch):
    """전부 429 면 그때는 기다린다 — 분당 창이 풀리길 기다리는 것 말곤 방법이 없다."""
    slept: list[float] = []
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: slept.append(s))
    _mock_sync(monkeypatch, lambda r: httpx.Response(429, json=QUOTA))

    with pytest.raises(httpx.HTTPStatusError):
        gemini_embed.embed_batch(KeyRing(["k1", "k2"]), "m", ["a"], dim=2)

    assert slept, "모든 키가 마르면 백오프해야 한다"


def test_embed_does_not_rotate_on_5xx(monkeypatch):
    """5xx 는 서버 문제라 키를 바꿔도 같다. 키를 태우지 않고 바로 백오프한다."""
    monkeypatch.setattr(gemini_embed.time, "sleep", lambda s: None)
    seen: list[str] = []

    def handler(request):
        seen.append(_key_of(request))
        return httpx.Response(503, json={"error": "unavailable"})

    _mock_sync(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        gemini_embed.embed_batch(KeyRing(["k1", "k2"]), "m", ["a"], dim=2)

    assert set(seen) == {"k1"}


# ── 생성 경로 ──────────────────────────────────────────────────────
SSE_OK = b'data: {"candidates":[{"content":{"parts":[{"text":"\xec\x95\x88\xeb\x85\x95"}]}}]}\n\n'


def test_chat_stream_rotates_on_429(monkeypatch):
    """429 면 다음 키로 다시 쏜다. 이게 없으면 사용자는 빈 답변(폴백)만 본다."""
    seen: list[str] = []

    def handler(request):
        seen.append(_key_of(request))
        if _key_of(request) == "k1":
            return httpx.Response(429, json=QUOTA)
        return httpx.Response(200, content=SSE_OK)

    _mock_async(monkeypatch, handler)

    async def run():
        ring = KeyRing(["k1", "k2"])
        out = [
            d async for d in gemini.chat_stream(
                ring, "m", [{"role": "user", "content": "q"}], options={}, timeout=5.0
            )
        ]
        return out, ring

    out, ring = asyncio.run(run())
    assert out == ["\uc548\ub155"]
    assert seen == ["k1", "k2"]
    assert ring.current() == "k2"


def _drain(ring):
    async def run():
        return [
            d async for d in gemini.chat_stream(
                ring, "m", [{"role": "user", "content": "q"}], options={}, timeout=5.0
            )
        ]
    return asyncio.run(run())


def test_chat_stream_gives_up_when_all_keys_are_dry(monkeypatch):
    """전부 429 면 델타 없이 끝낸다 — 호출부(stream.py)가 폴백으로 처리한다."""
    seen: list[str] = []

    def handler(request):
        seen.append(_key_of(request))
        return httpx.Response(429, json=QUOTA)

    _mock_async(monkeypatch, handler)
    assert _drain(KeyRing(["k1", "k2"])) == []
    assert seen == ["k1", "k2"]   # 무한 재시도 금지 — 한 바퀴만


def test_chat_stream_does_not_rotate_on_400(monkeypatch):
    """400 은 스키마·모델 문제다. 키를 바꿔도 같으므로 태우지 않는다
    (2026-08-12 모델 별칭 사고: thinkingBudget=0 거부)."""
    seen: list[str] = []

    def handler(request):
        seen.append(_key_of(request))
        return httpx.Response(400, json={"error": "invalid argument"})

    _mock_async(monkeypatch, handler)
    assert _drain(KeyRing(["k1", "k2"])) == []
    assert seen == ["k1"]


def test_chat_rotates_on_429(monkeypatch):
    """단발 chat(관련성 게이트)도 같은 규칙을 따른다."""
    seen: list[str] = []

    def handler(request):
        seen.append(_key_of(request))
        if _key_of(request) == "k1":
            return httpx.Response(429, json=QUOTA)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "\uc608"}]}}]}
        )

    _mock_async(monkeypatch, handler)
    out = asyncio.run(
        gemini.chat(
            KeyRing(["k1", "k2"]), "m", [{"role": "user", "content": "q"}],
            options={}, timeout=5.0,
        )
    )
    assert out == "\uc608"
    assert seen == ["k1", "k2"]
