from __future__ import annotations
import re

from ingest.preprocess import strip_emoji


_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", flags=re.MULTILINE)


def clean_response(text: str) -> str:
    """완성된 텍스트에 대한 풀 클린업. 마크업 매칭은 양쪽 끝 마커가 모두
    있어야 가능하므로, 스트리밍 토큰에 바로 적용하면 누수가 발생함.
    스트리밍 중에는 streaming_clean 사용, 종료 후 full text 에 clean_response 적용."""
    text = strip_emoji(text)
    text = _BOLD.sub(lambda m: m.group(1), text)
    text = _ITALIC.sub(lambda m: m.group(1), text)
    text = _HEADING.sub("", text)
    return text


def streaming_clean(token: str) -> str:
    """토큰 단위 안전 클린업: 이모지만 제거 (단일 문자 단위, 토큰 경계 영향 없음).
    bold/italic/heading 은 토큰 경계 사이에 마커가 걸칠 수 있어 스트리밍에서는
    건드리지 않음. 종료 시 clean_response 로 일괄 클린한 결과를 별도 이벤트로 전송."""
    return strip_emoji(token)
