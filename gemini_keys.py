"""Gemini API 키 링 — 쿼터가 마른 키를 건너뛰고 다음 키로 넘어간다.

무료 티어의 제한(분당·일일)은 **키마다 따로** 찬다. 키가 하나면 429 를 만났을 때
할 수 있는 일이 기다리는 것뿐이라, 인덱싱은 분 단위로 늘어지고 사용자 질문은
폴백 문구로 떨어진다. 키를 여러 개 두면 마른 키를 버리고 즉시 다음 키로 넘길 수
있다 — 기다림 없이.

커서는 요청 사이에 **유지된다**. 매 요청 1번 키부터 다시 시작하면 이미 마른 키에
왕복 한 번씩을 계속 버리기 때문이다. 그래서 KeyRing 은 값이 아니라 상태를 가진
객체이고, 프로세스당 하나를 만들어 돌려 쓴다.

키는 환경변수 GEMINI_API_KEY / GEMINI_API_KEY2 / GEMINI_API_KEY3 에서 읽는다.
하나만 채워도 동작한다(로테이션이 없는 것과 같다).
"""
from __future__ import annotations

import os
from typing import Iterable, Mapping, Sequence

# 순서가 곧 우선순위다. 앞의 키부터 쓴다.
ENV_NAMES = ("GEMINI_API_KEY", "GEMINI_API_KEY2", "GEMINI_API_KEY3")


class KeyRing:
    """키 목록 + 지금 쓰는 키를 가리키는 커서.

    빈 문자열·공백은 걸러낸다 — .env 에 `GEMINI_API_KEY3=` 만 남겨두는 일이
    흔한데, 그대로 두면 빈 키로 401 을 맞고 그게 쿼터 소진으로 오인된다.
    """

    def __init__(self, keys: Iterable[str]):
        self._keys: tuple[str, ...] = tuple(
            k.strip() for k in keys if k and k.strip()
        )
        self._i = 0

    @property
    def keys(self) -> tuple[str, ...]:
        """등록된 키들. 값이므로 로그·직렬화에 쓰지 말 것."""
        return self._keys

    def __len__(self) -> int:
        return len(self._keys)

    def __bool__(self) -> bool:
        return bool(self._keys)

    def __repr__(self) -> str:
        # 키 값은 절대 찍지 않는다 — 로그·예외 메시지로 새어나간다.
        return f"KeyRing(keys={len(self._keys)}, at={self._i})"

    def current(self) -> str:
        """지금 쓸 키. 키가 없으면 빈 문자열(호출부가 부팅 시 이미 막는다)."""
        return self._keys[self._i] if self._keys else ""

    def position(self) -> int:
        """지금 커서가 몇 번째 키인지(0-base). 로그용."""
        return self._i

    def rotate(self) -> bool:
        """다음 키로 넘긴다. 넘길 키가 있으면 True.

        키가 하나뿐이면 False 를 돌려준다 — 호출부가 '바꿔봐야 소용없으니
        백오프하라'를 이걸로 판단한다.
        """
        if len(self._keys) < 2:
            return False
        self._i = (self._i + 1) % len(self._keys)
        return True


def as_ring(keys: str | Sequence[str] | KeyRing) -> KeyRing:
    """문자열 하나든 목록이든 KeyRing 으로 맞춘다.

    기존 호출(`embed_batch("KEY", ...)`)과 테스트를 그대로 두기 위한 흡수층이다
    — `load_embedder(cfg | str)` 가 쓰는 것과 같은 방식.
    """
    if isinstance(keys, KeyRing):
        return keys
    if isinstance(keys, str):
        return KeyRing((keys,))
    return KeyRing(keys)


def from_env(env: Mapping[str, str] | None = None) -> KeyRing:
    """GEMINI_API_KEY / …2 / …3 을 순서대로 읽어 링을 만든다."""
    src = os.environ if env is None else env
    return KeyRing(src.get(name, "") for name in ENV_NAMES)
