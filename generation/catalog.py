"""매뉴얼 가이드 네비게이션 트리.

노션 매뉴얼 목차(TOC) 페이지의 `##` 구조를 파싱해 대분류 → 하위 문서 트리를
만든다. 카테고리를 코드에 박지 않고(데이터 기반) 매뉴얼이 바뀌면 목차만 갱신·
재인덱싱하면 자동 반영된다.

뎁스:
  1뎁스(첫 진입): 대분류 목록을 칩으로 보여줌
  2뎁스: 대분류 선택 → 그 하위 문서 목록
  3뎁스: 하위 문서 제목을 질문으로 전송(기존 FAQ 칩과 동일 경로)

메타 네비 섹션(전체/글로벌/기본 메뉴 안내)은 `**볼드 소제목**`을 자식으로 가져
이를 신호로 제외한다. 남는 것은 콘텐츠 대분류(주차학습 … 루브릭)뿐이다.

깨진 export 링크: 노션 마크다운 export 는 하위 페이지 링크를
'제목 ()%20<32hex>.md)' 처럼 깨뜨려 둔다. URL 인코딩 조각엔 항상 '%' 가 있고
한글 제목엔 없으므로 첫 '%' 이전까지를 제목으로 본다.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import load_config
from ingest.preprocess import strip_emoji

# 매뉴얼 TOC 페이지 제목 접미사. 'LMS 매뉴얼', 'CMS 매뉴얼' …
_MANUAL_SUFFIX = "매뉴얼"

_H2_RE = re.compile(r"^##\s+(.*)$")
_H1_RE = re.compile(r"^#\s+(.*)$")
_MD_LINK_RE = re.compile(r"^\[(.+)\]\(.*\)\s*$")
_EMPTY_PARENS_RE = re.compile(r"\s*\(\s*\)\s*")


@dataclass(frozen=True)
class Category:
    name: str
    docs: tuple[str, ...]


@dataclass(frozen=True)
class Manual:
    name: str                       # 'LMS' / 'CMS' — UI 라벨 + manual 스코프 키
    title: str                      # 'LMS 매뉴얼'
    categories: tuple[Category, ...]


def _clean_heading(raw: str) -> str:
    """'## ** 주차학습**' 류에서 *, 이모지, 공백 정리 → '주차학습'."""
    s = strip_emoji(raw.replace("*", " "))
    return re.sub(r"\s+", " ", s).strip()


def _is_bold_subheader(line: str) -> bool:
    """줄 전체가 볼드(**...**)인 소제목인가. 메타 네비 섹션의 표지."""
    s = line.strip()
    return s.startswith("**") and s.endswith("**") and len(s) > 4


def _clean_doc_label(line: str) -> str:
    """TOC 문서 줄에서 사람이 읽는 제목만 추출한다."""
    s = line.strip()
    m = _MD_LINK_RE.match(s)
    s = m.group(1) if m else s.split("%", 1)[0]
    s = strip_emoji(s)
    s = _EMPTY_PARENS_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_toc(md_text: str) -> tuple[Category, ...]:
    """TOC 본문 → 콘텐츠 대분류 트리.

    매뉴얼마다 목차 관례가 다르다:
      LMS: `## 카테고리` + 문서 줄. 볼드 소제목을 가진 섹션은 메타 네비라 제외.
      CMS: `**카테고리**` 볼드 줄 + `[문서](url)` 링크. `##` 없음.
    `##` 존재 여부로 분기한다."""
    has_h2 = any(_H2_RE.match(l) for l in md_text.splitlines())
    return _parse_h2_toc(md_text) if has_h2 else _parse_bold_toc(md_text)


def _parse_h2_toc(md_text: str) -> tuple[Category, ...]:
    """LMS 식: `##` 카테고리. 볼드 소제목(메타 섹션 표지)을 가진 카테고리는 제외."""
    result: list[Category] = []
    name = ""
    docs: list[str] = []
    has_bold = False

    def flush() -> None:
        if name and docs and not has_bold:
            result.append(Category(name=name, docs=tuple(docs)))

    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        h2 = _H2_RE.match(line)
        if h2:
            flush()
            name, docs, has_bold = _clean_heading(h2.group(1)), [], False
            continue
        if _H1_RE.match(line):
            flush()
            name, docs, has_bold = "", [], False
            continue
        if not name:
            continue
        if _is_bold_subheader(line):
            has_bold = True
            continue
        label = _clean_doc_label(line)
        if label:
            docs.append(label)
    flush()
    return tuple(result)


def _parse_bold_toc(md_text: str) -> tuple[Category, ...]:
    """CMS 식: 볼드 줄이 카테고리, 그 아래 링크/문서 줄이 하위 문서. 문서가 없는
    카테고리는 제외."""
    result: list[Category] = []
    name = ""
    docs: list[str] = []

    def flush() -> None:
        if name and docs:
            result.append(Category(name=name, docs=tuple(docs)))

    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if _H1_RE.match(line):
            continue
        if _is_bold_subheader(line):
            flush()
            name, docs = _clean_heading(line), []
            continue
        if not name:
            continue
        label = _clean_doc_label(line)
        if label:
            docs.append(label)
    flush()
    return tuple(result)


def _manual_key(title: str) -> str:
    """'LMS 매뉴얼' → 'LMS'. 매뉴얼 폴더/TOC 제목 → 스코프 키."""
    return title[: -len(_MANUAL_SUFFIX)].strip() if title.endswith(_MANUAL_SUFFIX) else title


def _find_manual_tocs(raw_dir: Path) -> list[Path]:
    """'…매뉴얼' 제목의 TOC 인덱스 페이지(같은 이름 형제 폴더에 자식 .md 보유)."""
    from ingest.chunk import _derive_title
    out: list[Path] = []
    for md in raw_dir.rglob("*.md"):
        title = _derive_title(md)
        if not title.endswith(_MANUAL_SUFFIX):
            continue
        sibling = md.parent / title
        if sibling.is_dir() and any(sibling.rglob("*.md")):
            out.append(md)
    return out


@lru_cache(maxsize=1)
def build_catalog() -> tuple[Manual, ...]:
    """raw_dir 의 매뉴얼 TOC 들을 파싱해 매뉴얼 트리를 만든다(없으면 빈 튜플 —
    네비는 graceful 하게 생략). LMS 를 항상 앞에 둔다(주 사용 매뉴얼)."""
    from ingest.chunk import _derive_title
    raw_dir = load_config().raw_dir
    manuals: list[Manual] = []
    for toc in _find_manual_tocs(raw_dir):
        title = _derive_title(toc)
        cats = parse_toc(toc.read_text(encoding="utf-8"))
        if cats:
            manuals.append(Manual(name=_manual_key(title), title=title, categories=cats))
    manuals.sort(key=lambda m: (m.name != "LMS", m.name))
    return tuple(manuals)
