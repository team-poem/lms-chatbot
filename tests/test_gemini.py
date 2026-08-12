"""Gemini 어댑터의 프로토콜 변환. 네트워크 없이 순수 함수만 본다 —
Ollama 와 다른 세 지점(system 롤 승격, assistant→model, SSE 파싱)이 회귀 표적이다."""
from __future__ import annotations

import asyncio
import functools

import httpx
import pytest

from generation import gemini
from generation.llm import LLMConfig, _adapter


def _mock_httpx(monkeypatch, handler) -> None:
    """gemini 모듈이 직접 여는 AsyncClient 에 MockTransport 를 물린다."""
    monkeypatch.setattr(
        gemini.httpx,
        "AsyncClient",
        functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )


def test_system_message_becomes_system_instruction():
    # Gemini 에는 system 롤이 없다. persona.build_prompt 가 항상 system 을 얹으므로
    # 이걸 놓치면 페르소나 규칙이 통째로 사라진다.
    contents, system = gemini.to_contents(
        [{"role": "system", "content": "너는 조교다"}, {"role": "user", "content": "안녕"}]
    )
    assert system == {"parts": [{"text": "너는 조교다"}]}
    assert contents == [{"role": "user", "parts": [{"text": "안녕"}]}]


def test_multiple_system_messages_are_joined():
    _, system = gemini.to_contents(
        [{"role": "system", "content": "A"}, {"role": "system", "content": "B"}]
    )
    assert system["parts"][0]["text"] == "A\n\nB"


def test_assistant_role_renamed_to_model():
    contents, system = gemini.to_contents([{"role": "assistant", "content": "답"}])
    assert contents[0]["role"] == "model"
    assert system is None


def test_generation_config_maps_temperature_and_drops_num_ctx():
    # num_ctx 는 Ollama 전용 노브 — 그대로 넘기면 400 이 난다.
    cfg = gemini.to_generation_config({"num_ctx": 8192, "temperature": 0.2})
    assert cfg["temperature"] == 0.2
    assert "num_ctx" not in cfg


def test_generation_config_disables_thinking_by_default():
    # 두 호출 다 컨텍스트가 주어진 추출형이라 사고 토큰은 지연·비용만 늘린다.
    assert gemini.to_generation_config({})["thinkingConfig"]["thinkingBudget"] == 0


def test_generation_config_thinking_budget_overridable():
    cfg = gemini.to_generation_config({"thinking_budget": 512})
    assert cfg["thinkingConfig"]["thinkingBudget"] == 512


def test_build_payload_omits_system_instruction_when_absent():
    # relevance 게이트는 user 메시지 하나만 보낸다 — 빈 systemInstruction 을 넣으면 400.
    payload = gemini.build_payload([{"role": "user", "content": "q"}], {})
    assert "systemInstruction" not in payload


def test_parse_sse_line_extracts_json():
    assert gemini.parse_sse_line('data: {"a": 1}') == {"a": 1}


def test_parse_sse_line_ignores_non_data_lines():
    assert gemini.parse_sse_line("") is None
    assert gemini.parse_sse_line(": keep-alive") is None
    assert gemini.parse_sse_line("data: [DONE]") is None


def test_extract_text_joins_parts():
    obj = {"candidates": [{"content": {"parts": [{"text": "가"}, {"text": "나"}]}}]}
    assert gemini.extract_text(obj) == "가나"


def test_extract_text_skips_thought_parts():
    # thinkingBudget 을 켠 설정에서 사고 내용이 답변으로 새어나가는 것을 막는다.
    obj = {
        "candidates": [
            {"content": {"parts": [{"text": "숨은 생각", "thought": True}, {"text": "답"}]}}
        ]
    }
    assert gemini.extract_text(obj) == "답"


def test_extract_text_empty_when_no_candidates():
    # 안전 필터로 차단되면 candidates 가 비어 온다. 여기서 터지면 스트림 전체가 죽는다.
    assert gemini.extract_text({}) == ""
    assert gemini.extract_text({"candidates": []}) == ""


def test_adapter_routes_by_provider():
    mod, endpoint = _adapter(LLMConfig(provider="gemini", model="m", api_key="k"))
    assert (mod, endpoint) == (gemini, "k")


def test_adapter_rejects_unknown_provider():
    # 오타가 조용히 Ollama 로 떨어지면 커넥션 거부로만 보여 원인 추적이 어렵다.
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        _adapter(LLMConfig(provider="gemeni", model="m"))


# ── HTTP 배선 (MockTransport — 네트워크 없음) ──────────────────────────

_SSE = (
    'data: {"candidates":[{"content":{"parts":[{"text":"퀴즈"}]}}]}\n'
    "\n"
    ": keep-alive\n"
    'data: {"candidates":[{"content":{"parts":[{"text":" 출제"}]}}]}\n'
    "\n"
)


def test_chat_stream_yields_deltas_and_sets_auth(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        return httpx.Response(200, content=_SSE.encode())

    _mock_httpx(monkeypatch, handler)

    async def run():
        return [
            d
            async for d in gemini.chat_stream(
                "KEY", "gemini-2.5-flash", [{"role": "user", "content": "q"}],
                options={"temperature": 0.2}, timeout=5.0,
            )
        ]

    assert asyncio.run(run()) == ["퀴즈", " 출제"]
    # alt=sse 가 빠지면 응답이 JSON 배열로 와서 델타가 하나도 안 나온다.
    assert "streamGenerateContent?alt=sse" in seen["url"]
    assert seen["key"] == "KEY"


def test_chat_stream_survives_http_error(monkeypatch):
    # ollama 어댑터와 같은 정책 — 에러 응답은 델타 없이 자연 종료(호출부가 폴백 처리).
    _mock_httpx(monkeypatch, lambda req: httpx.Response(401, json={"error": "bad key"}))

    async def run():
        return [
            d
            async for d in gemini.chat_stream(
                "BAD", "m", [{"role": "user", "content": "q"}], options={}, timeout=5.0
            )
        ]

    assert asyncio.run(run()) == []


def test_chat_returns_text_and_raises_on_error(monkeypatch):
    _mock_httpx(
        monkeypatch,
        lambda req: httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "예"}]}}]}
        ),
    )
    got = asyncio.run(
        gemini.chat("K", "m", [{"role": "user", "content": "q"}], options={}, timeout=5.0)
    )
    assert got == "예"

    # 게이트(relevance)는 이 예외를 잡아 None(통과)으로 바꾼다 — 전파되어야 그게 된다.
    _mock_httpx(monkeypatch, lambda req: httpx.Response(429, json={"error": "quota"}))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(
            gemini.chat("K", "m", [{"role": "user", "content": "q"}], options={}, timeout=5.0)
        )


def test_stream_logs_http_error_but_keeps_empty_fallback(monkeypatch, capsys):
    """에러 응답은 여전히 델타 없이 끝나되(폴백 유지), 원인은 stderr 에 남아야 한다.

    2026-08-12: 모델 별칭이 thinkingBudget=0 을 거부해 400 이 났는데, 로그가 없어
    '답변이 빈다'로만 보였다. 그 진단 불가 상태를 막기 위한 회귀 표적이다."""
    _mock_httpx(
        monkeypatch,
        lambda req: httpx.Response(400, json={"error": {"message": "invalid argument"}}),
    )

    async def collect():
        return [
            d async for d in gemini.chat_stream(
                "K", "some-model", [{"role": "user", "content": "q"}],
                options={}, timeout=5,
            )
        ]

    assert asyncio.run(collect()) == []          # 폴백 동작 불변
    err = capsys.readouterr().err
    assert "HTTP 400" in err
    assert "some-model" in err
    assert "invalid argument" in err


def test_stream_success_path_logs_nothing(monkeypatch, capsys):
    _mock_httpx(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            text='data: {"candidates":[{"content":{"parts":[{"text":"안녕"}]}}]}\n\n',
        ),
    )

    async def collect():
        return [
            d async for d in gemini.chat_stream(
                "K", "m", [{"role": "user", "content": "q"}], options={}, timeout=5
            )
        ]

    assert asyncio.run(collect()) == ["안녕"]
    assert capsys.readouterr().err == ""
