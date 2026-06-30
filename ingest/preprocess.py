from __future__ import annotations
import re


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "]+",
    flags=re.UNICODE,
)

_IMG_PLACEHOLDER = "\x00IMG{}\x00"
_IMG_LINK_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# 표시 텍스트가 있는 링크: 텍스트만 남김
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# 빈 텍스트 링크 '[](url)': 표시할 텍스트가 없으므로 통째로 제거 (Notion이 첨부
# 이미지를 이렇게 내보내 본문에 media-cdn URL이 그대로 남는 것을 방지).
_EMPTY_LINK_RE = re.compile(r"\[\]\([^)]+\)")
_ASIDE_OPEN = re.compile(r"<aside>\s*", flags=re.IGNORECASE)
_ASIDE_CLOSE = re.compile(r"\s*</aside>", flags=re.IGNORECASE)
_HR_LINE = re.compile(r"^\s*-{3,}\s*$", flags=re.MULTILINE)
_MULTI_BLANK = re.compile(r"\n{3,}")
# 파일명·목차 라벨에서 장식 이모지가 제거되고 남는 빈 괄호 '()' 제거용.
# chunk(derive_title)와 generation/catalog(_clean_doc_label)가 공유한다.
_EMPTY_PARENS_RE = re.compile(r"\s*\(\s*\)\s*")
# FAQ DATABASE md 전용 메타헤더 4종(메뉴명/시기/연번/태그)을 라인 단위로 제거.
# 이 라벨들은 data/raw 전체에서 FAQ DATABASE 폴더의 본문 상단에만 라인 시작으로
# 존재함이 확인됨. 본문에 들어가면 답변 대신 분류용 메타데이터가 노출된다(#24).
_META_HEADER_RE = re.compile(
    r"^(?:메뉴명|시기|연번|태그)\s*[:：].*(?:\n|$)", flags=re.MULTILINE
)


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def strip_empty_parens(text: str) -> str:
    return _EMPTY_PARENS_RE.sub(" ", text)


def clean_markdown(src: str) -> str:
    images: list[str] = []

    def stash(match: re.Match) -> str:
        images.append(match.group(0))
        return _IMG_PLACEHOLDER.format(len(images) - 1)

    text = _IMG_LINK_RE.sub(stash, src)
    text = _ASIDE_OPEN.sub("", text)
    text = _ASIDE_CLOSE.sub("", text)
    text = _EMPTY_LINK_RE.sub("", text)
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    text = _HR_LINE.sub("", text)
    text = _META_HEADER_RE.sub("", text)
    text = strip_emoji(text)
    text = _MULTI_BLANK.sub("\n\n", text)

    for i, original in enumerate(images):
        text = text.replace(_IMG_PLACEHOLDER.format(i), original)

    return text.strip() + "\n"
