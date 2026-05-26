from __future__ import annotations
import re

from ingest.preprocess import strip_emoji


_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", flags=re.MULTILINE)


def clean_response(text: str) -> str:
    text = strip_emoji(text)
    text = _BOLD.sub(lambda m: m.group(1), text)
    text = _ITALIC.sub(lambda m: m.group(1), text)
    text = _HEADING.sub("", text)
    return text
