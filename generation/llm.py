"""생성 백엔드 선택. ollama / gemini 두 어댑터 앞의 얇은 분기 층.

호출부(stream.py, relevance.py)는 이제 어느 백엔드인지 모른다 — LLMConfig 하나만
받아 chat/chat_stream 을 부른다. 백엔드가 하나 더 늘어도 바뀌는 곳은 이 파일뿐이다.

첫 인자(`endpoint`)의 의미는 백엔드마다 다르다 — Ollama 는 호스트 URL, Gemini 는
API 키다. 그 차이를 LLMConfig 가 흡수하고 밖으론 안 샌다.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import AsyncIterator

from generation import gemini, ollama

GEMINI = "gemini"
OLLAMA = "ollama"


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    host: str = ""      # ollama 전용
    api_key: str = ""   # gemini 전용


def _adapter(cfg: LLMConfig):
    """(모듈, endpoint) 쌍. 알 수 없는 provider 는 Ollama 로 떨어뜨리지 않고
    바로 실패시킨다 — 오타(`gemeni`)가 조용히 로컬 Ollama 호출로 둔갑해 커넥션
    거부로 나타나면 원인 추적이 어렵다."""
    if cfg.provider == GEMINI:
        return gemini, cfg.api_key
    if cfg.provider == OLLAMA:
        return ollama, cfg.host
    raise ValueError(f"알 수 없는 LLM_PROVIDER: {cfg.provider!r} (ollama|gemini)")


async def chat(
    cfg: LLMConfig, messages: list[dict], *, options: dict, timeout: float
) -> str:
    mod, endpoint = _adapter(cfg)
    return await mod.chat(endpoint, cfg.model, messages, options=options, timeout=timeout)


async def chat_stream(
    cfg: LLMConfig, messages: list[dict], *, options: dict, timeout: float
) -> AsyncIterator[str]:
    mod, endpoint = _adapter(cfg)
    async for delta in mod.chat_stream(
        endpoint, cfg.model, messages, options=options, timeout=timeout
    ):
        yield delta
