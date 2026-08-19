"""Notion MCP 의 enhanced markdown → 우리 파이프라인이 먹는 export 형 md.

MCP `fetch` 는 REST 의 블록 JSON 이 아니라 자체 마크다운을 준다(`<page>`,
`<columns>`, `<callout>` 같은 태그가 섞인 형태). 이걸 기존 인덱싱 경로가
기대하는 모양 — Notion "Markdown & CSV" export 가 내던 것 — 으로 되돌린다.

변환이 지켜야 할 다운스트림 계약은 export 시절과 같다:

  1. TOC: `## 카테고리` + `[문서](url)` 줄 + 볼드 소제목 줄.
     generation/catalog.parse_toc 가 이 관례로 트리를 만들고, 볼드 소제목이
     있는 카테고리는 메타 네비로 제외한다.
  2. 본문 이미지: `![](URL인코딩된 상대경로)`. pipeline._rewrite_image_refs 가
     unquote 해서 assets 매핑에 대조한다.
  3. 노션이 주는 이미지 URL 은 만료된다(presigned, 수 분). 여기서는 다운로드
     목록만 만들고, **호출부가 fetch 직후 즉시 내려받아야 한다.**

TOC 와 본문은 버리는 것이 다르다. TOC 는 구조(헤딩·링크·볼드)만 남기고 전부
버린다 — 장식 이미지·컬럼 레이아웃은 네비에 기여하지 않는다. 본문은 반대로
텍스트를 최대한 살린다 — 검색 품질이 여기 달렸다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlparse

# MCP 페이지 URL 끝의 32자리 hex. https://app.notion.com/p/<32hex>?...
_PAGE_URL_ID_RE = re.compile(r"/p/([0-9a-f]{32})")
_PAGE_TAG_RE = re.compile(r'<page url="([^"]+)"[^>]*>([^<]*)</page>')
_SPAN_RE = re.compile(r"<span[^>]*>|</span>")
_COLOR_ANNO_RE = re.compile(r"\s*\{color=\"[^\"]*\"\}\s*")
_IMG_RE = re.compile(r"^!\[[^\]]*\]\((https?://[^)]+)\)\s*$")
_H_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BOLD_LINE_RE = re.compile(r"^\*\*.+\*\*\s*$")
_HR_RE = re.compile(r"^-{3,}\s*$")
# 구조 태그 줄(여닫이 통째로 버림). callout 은 예외 — 안의 텍스트는 본문이다.
_DROP_TAG_RE = re.compile(
    r"^</?(?:columns|column|synced_block|page|content|ancestor-path|properties|"
    r"parent-page|ancestor-\d-page|page-discussions)\b.*$|"
    r"^<(?:empty-block|table_of_contents|divider)[^>]*/?>$"
)
_CALLOUT_OPEN_RE = re.compile(r"^\s*<callout[^>]*>\s*$")
_CALLOUT_CLOSE_RE = re.compile(r"^\s*</callout>\s*$")


def page_id_from_url(url: str) -> str:
    m = _PAGE_URL_ID_RE.search(urlparse(url).path)
    return m.group(1) if m else ""


def _clean_inline(line: str) -> str:
    """span·색 주석·<br> 등 인라인 장식 제거."""
    line = _SPAN_RE.sub("", line)
    line = _COLOR_ANNO_RE.sub("", line)
    line = line.replace("<br>", " ")
    return line.rstrip()


@dataclass(frozen=True)
class TocEntry:
    """TOC 한 줄 — 자식 문서 수집 목록의 재료."""

    page_id: str
    title: str


def toc_markdown(mcp_text: str, title: str) -> tuple[str, list[TocEntry]]:
    """TOC 페이지 → parse_toc 호환 md + 자식 문서 목록.

    구조 신호 세 가지(## 헤딩, 볼드 소제목, page 링크)만 남긴다. `---` 는
    버린다 — parse_toc 는 카테고리 아래 아무 줄이나 문서 제목으로 보므로,
    남기면 '---' 라는 유령 문서가 생긴다.
    """
    out = [f"# {title}", ""]
    entries: list[TocEntry] = []
    for raw in mcp_text.splitlines():
        line = _clean_inline(raw.strip())
        if not line or _HR_RE.match(line):
            continue
        m = _H_RE.match(line)
        if m and len(m.group(1)) >= 2:
            out += ["", f"## {m.group(2).strip()}", ""]
            continue
        # 링크 매치를 DROP 보다 먼저 본다 — 래퍼 <page url="..."> 와 인라인
        # <page url="...">제목</page> 이 같은 태그명이라, DROP 을 먼저 돌리면
        # 문서 링크가 통째로 사라진다(자식 수집 목록이 비는 조용한 실패).
        m = _PAGE_TAG_RE.search(line)
        if m:
            url, label = m.group(1), m.group(2).strip()
            pid = page_id_from_url(url)
            if pid and label:
                out.append(f"[{label}]({url})")
                entries.append(TocEntry(page_id=pid, title=label))
            continue
        if _DROP_TAG_RE.match(line):
            continue
        if _BOLD_LINE_RE.match(line):
            out.append(line)          # 메타 섹션 신호 — parse_toc 가 소비한다
            continue
        # 나머지(장식 이미지·본문 문장 등)는 TOC 에선 전부 버린다.
    return "\n".join(out).rstrip() + "\n", entries


@dataclass(frozen=True)
class PageResult:
    markdown: str
    # (원격 URL, 로컬 파일명). URL 은 수 분 내 만료 — 호출부가 즉시 받아야 한다.
    images: tuple[tuple[str, str], ...] = ()
    dropped_tags: tuple[str, ...] = field(default_factory=tuple)


def _image_filename(url: str, seq: int) -> str:
    """S3 경로 마지막 조각을 파일명으로. 겹치면 seq 로 구분한다."""
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1]) or f"image_{seq}.png"
    stem, dot, ext = name.rpartition(".")
    return f"{stem}_{seq}.{ext}" if dot else f"{name}_{seq}"


def page_markdown(mcp_text: str, title: str, *, asset_dir: str) -> PageResult:
    """본문 페이지 → 인덱싱용 md.

    asset_dir 는 이미지가 놓일 폴더 이름(예: '주차학습 개요 및 구성 <id>').
    md 안의 참조는 export 관례대로 URL 인코딩해 둔다.
    """
    out = [f"# {title}", ""]
    images: list[tuple[str, str]] = []
    dropped: set[str] = set()

    for raw in mcp_text.splitlines():
        line = raw.strip()
        if not line:
            out.append("")
            continue
        if _CALLOUT_OPEN_RE.match(line) or _CALLOUT_CLOSE_RE.match(line):
            continue                   # 태그만 벗기고 안의 텍스트는 살린다
        m = _PAGE_TAG_RE.search(line)
        if m:
            out.append(m.group(2).strip())   # 링크 대상은 별도 문서 — 제목만 남긴다
            continue
        if _DROP_TAG_RE.match(line):
            continue
        line = _clean_inline(line)
        if not line:
            continue

        m = _IMG_RE.match(line)
        if m:
            url = m.group(1)
            fname = _image_filename(url, len(images))
            images.append((url, fname))
            out.append(f"![]({quote(asset_dir)}/{quote(fname)})")
            continue

        m = _H_RE.match(line)
        if m:
            out += ["", f"{m.group(1)} {m.group(2).strip()}", ""]
            continue

        unknown = re.match(r"^</?([a-z_-]+)", line)
        if unknown and not line.startswith(("**", "*", "-", "#")):
            dropped.add(unknown.group(1))
            continue
        out.append(line)

    md = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).rstrip() + "\n"
    return PageResult(markdown=md, images=tuple(images),
                      dropped_tags=tuple(sorted(dropped)))
