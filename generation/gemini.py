"""Gemini Generative Language API 클라이언트 — 스트리밍(chat_stream)·단발(chat).

ollama.py 와 같은 자리(생성·관련성 게이트)에 꽂히도록 시그니처를 맞춘다. 첫 인자만
다르다 — Ollama 는 호스트 URL, Gemini 는 API 키. 둘의 분기는 llm.py 가 맡는다.

Ollama 와 프로토콜이 세 군데 다르고, 그 차이를 이 모듈이 전부 흡수한다:
  1. system 롤이 없다 — messages 의 system 은 systemInstruction 으로 빠진다.
  2. assistant 롤 이름이 'model' 이다.
  3. 스트림이 JSON Lines 가 아니라 SSE(`alt=sse`) 다 — 'data: ' 접두를 벗겨야 한다.

순수 변환(to_contents/parse_sse_line/…)은 모듈 함수로 분리해 네트워크 없이 테스트한다.
"""
from __future__ import annotations
import json
import sys
from typing import AsyncIterator

import httpx

from gemini_keys import KeyRing, as_ring

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


def to_contents(messages: list[dict]) -> tuple[list[dict], dict | None]:
    """Ollama chat messages → (contents, systemInstruction).

    system 메시지는 Gemini 에 롤로 존재하지 않아 systemInstruction 으로 승격한다
    (여럿이면 개행으로 합침). assistant 는 'model' 로 이름만 바꾼다."""
    contents: list[dict] = []
    system_parts: list[str] = []
    for m in messages:
        role, text = m.get("role", "user"), m.get("content", "")
        if role == "system":
            if text:
                system_parts.append(text)
            continue
        contents.append(
            {"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]}
        )
    system = {"parts": [{"text": "\n\n".join(system_parts)}]} if system_parts else None
    return contents, system


def to_generation_config(options: dict) -> dict:
    """tuning.py 의 Ollama 옵션 → Gemini generationConfig.

    `num_ctx`(Ollama 의 컨텍스트 창 크기)는 대응 개념이 없어 버린다 — Gemini 는
    모델이 컨텍스트 길이를 정한다. `num_predict` 만 maxOutputTokens 로 옮긴다.

    thinkingBudget 은 0 을 기본으로 둔다. 2.5 계열은 기본이 사고(thinking) 켜짐인데,
    이 앱의 두 호출(가이드 발췌 요약, 예/아니오 이진 판정)은 모두 근거가 컨텍스트에
    다 주어진 추출형이라 사고 토큰이 지연·비용만 늘린다. options 에 thinking_budget 을
    넣으면 덮어쓴다."""
    cfg: dict = {}
    if "temperature" in options:
        cfg["temperature"] = options["temperature"]
    if "top_p" in options:
        cfg["topP"] = options["top_p"]
    if "num_predict" in options:
        cfg["maxOutputTokens"] = options["num_predict"]
    cfg["thinkingConfig"] = {"thinkingBudget": options.get("thinking_budget", 0)}
    return cfg


def build_payload(messages: list[dict], options: dict) -> dict:
    contents, system = to_contents(messages)
    payload: dict = {"contents": contents, "generationConfig": to_generation_config(options)}
    if system:
        payload["systemInstruction"] = system
    return payload


def extract_text(obj: dict) -> str:
    """응답(또는 스트림 청크) 한 건에서 텍스트 파트만 이어붙인다. 사고 파트
    (`thought: true`)는 답변이 아니므로 제외한다 — thinkingBudget 0 이면 애초에
    오지 않지만, 켠 설정에서 그대로 새어나가는 것을 막는다."""
    candidates = obj.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def parse_sse_line(line: str) -> dict | None:
    """SSE 한 줄 → JSON 오브젝트. 데이터 줄이 아니거나 종료 신호면 None.

    깨진 줄도 None 이다 — 예외를 올리면 스트림 도중 터져서 **그때까지 흘린 델타까지
    포함해 답변 전체가 날아간다**. 한 줄 손실이 답변 전체 손실보다 낫다는 판단이며,
    빈 답변 폴백을 두는 이 모듈의 철학과도 맞다. 대신 조용히 넘기지 않고 남긴다."""
    if not line.startswith("data:"):
        return None
    body = line[len("data:"):].strip()
    if not body or body == "[DONE]":
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        print(
            f"[gemini.parse_sse_line] SSE 파싱 실패(해당 줄만 버림). {e} :: {body[:120]}",
            file=sys.stderr,
            flush=True,
        )
        return None


def _headers(api_key: str) -> dict:
    return {"x-goog-api-key": api_key, "Content-Type": "application/json"}


# 쿼터 소진. 이 상태에서만 키를 바꾼다 — 5xx 는 키를 바꿔도 그대로다.
QUOTA_STATUS = 429


def _log_rotate(where: str, ring: KeyRing) -> None:
    """어떤 키로 넘어갔는지 번호만 남긴다. 키 값은 절대 찍지 않는다."""
    print(
        f"[{where}] 429 — 다음 키로 전환 (키 #{ring.position() + 1}/{len(ring)})",
        file=sys.stderr,
        flush=True,
    )


def _log_http_error(where: str, model: str, status: int, body: str) -> None:
    """폴백 동작은 그대로 두되 원인만 남긴다. 본문은 앞부분만 — 키가 섞일 일은
    없지만 로그를 길게 오염시키지 않기 위해서다."""
    print(
        f"[{where}] HTTP {status} model={model} :: {body[:300].strip()}",
        file=sys.stderr,
        flush=True,
    )


async def chat_stream(
    keys: str | KeyRing, model: str, messages: list[dict], *, options: dict, timeout: float
) -> AsyncIterator[str]:
    """스트리밍 chat. 텍스트 델타(비어 있지 않은 것만)를 그대로 흘린다.

    ollama.chat_stream 과 마찬가지로 raise_for_status 를 부르지 않는다 — 에러 응답은
    델타 없이 자연 종료되고, 호출부(stream.py)는 빈 답변을 폴백으로 처리한다.
    다만 **이유는 로그로 남긴다**: 폴백만 있고 흔적이 없으면 모델·스키마 비호환이
    '답변이 빈다'로만 나타나 진단이 불가능하다(2026-08-12 모델 별칭 사고 —
    docs/2026-08-12-model-alias-decision.md)."""
    ring = as_ring(keys)
    url = f"{API_ROOT}/{model}:streamGenerateContent?alt=sse"
    payload = build_payload(messages, options)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        # 429 는 그 키의 쿼터가 말랐다는 뜻이라 같은 키로 다시 쏴봐야 소용없다.
        # 남은 키를 한 바퀴까지 즉시 시도하고, 전부 마르면 델타 없이 끝낸다(폴백).
        for _ in range(len(ring) or 1):
            async with client.stream(
                "POST", url, json=payload, headers=_headers(ring.current())
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    _log_http_error("gemini.chat_stream", model, resp.status_code, body)
                    if resp.status_code == QUOTA_STATUS and ring.rotate():
                        _log_rotate("gemini.chat_stream", ring)
                        continue
                    return
                async for line in resp.aiter_lines():
                    obj = parse_sse_line(line)
                    if obj is None:
                        continue
                    delta = extract_text(obj)
                    if delta:
                        yield delta
                return


async def chat(
    keys: str | KeyRing, model: str, messages: list[dict], *, options: dict, timeout: float
) -> str:
    """단발 chat. 응답 본문 텍스트만 반환. HTTP 오류는 예외로 전파."""
    ring = as_ring(keys)
    url = f"{API_ROOT}/{model}:generateContent"
    payload = build_payload(messages, options)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        for _ in range(len(ring) or 1):
            resp = await client.post(url, json=payload, headers=_headers(ring.current()))
            if resp.status_code == QUOTA_STATUS and ring.rotate():
                _log_rotate("gemini.chat", ring)
                continue
            resp.raise_for_status()
            return extract_text(resp.json())
        resp.raise_for_status()   # 모든 키가 429 — 마지막 응답을 그대로 올린다
        return extract_text(resp.json())
