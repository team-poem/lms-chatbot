"""Ollama /api/chat HTTP 클라이언트 — 스트리밍(chat_stream)·단발(chat).

stream.py(답변 생성)와 relevance.py(관련성 게이트)가 같은 엔드포인트를 각자
httpx 로 호출하던 중복을 모은다. 예외 처리는 호출부 정책에 맡긴다 — 생성은
전파(스트림 중단이 곧 실패), 게이트는 잡아서 None(답을 막지 않음).
"""
from __future__ import annotations
import json
import sys
from typing import AsyncIterator

import httpx


async def chat_stream(
    host: str, model: str, messages: list[dict], *, options: dict, timeout: float
) -> AsyncIterator[str]:
    """스트리밍 chat. 토큰 델타(비어 있지 않은 것만)를 그대로 흘린다.

    의도적으로 raise_for_status 를 호출하지 않는다 — HTTP 에러 응답(JSON 본문)은
    델타 없이 자연 종료되는 것이 종전 stream.py 동작이며, 추가하면 행동이 바뀐다.
    클라이언트도 요청마다 새로 연다(커넥션 풀 미사용) — 종전 동작 보존.
    다만 에러 응답의 **이유는 로그로 남긴다**(gemini 쪽과 같은 판단): 폴백만 있고
    흔적이 없으면 '답변이 빈다'로만 나타나 진단이 불가능하다."""
    payload = {"model": model, "messages": messages, "stream": True, "options": options}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        async with client.stream("POST", f"{host}/api/chat", json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "replace")
                print(
                    f"[ollama.chat_stream] HTTP {resp.status_code} model={model} "
                    f":: {body[:300].strip()}",
                    file=sys.stderr,
                    flush=True,
                )
                return
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                delta = obj.get("message", {}).get("content", "")
                if delta:
                    yield delta
                if obj.get("done"):
                    break


async def chat(
    host: str, model: str, messages: list[dict], *, options: dict, timeout: float
) -> str:
    """단발 chat. 응답 본문 텍스트만 반환. HTTP 오류는 예외로 전파."""
    payload = {"model": model, "messages": messages, "stream": False, "options": options}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        resp = await client.post(f"{host}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
