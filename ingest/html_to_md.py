"""Notion HTML export → Markdown.

Notion 은 "Markdown & CSV" 와 "HTML" 두 형식으로 내보낼 수 있는데, 손에 있는
export 가 HTML 뿐일 때 기존 인덱싱 경로(collect_markdown → clean_markdown →
chunk_markdown_file)를 그대로 쓰기 위한 변환기다. 각 .html 옆에 같은 이름의
.md 를 만들어 두면 그 뒤 파이프라인은 형식을 알 필요가 없다.

의존성을 늘리지 않으려고 표준 html.parser 로 짰다. 범용 HTML→MD 변환기가 아니라
**Notion export 구조 전용**이다. 일반 웹 문서에는 쓰지 말 것.

다운스트림과 맞물리는 지점이 셋이고, 어긋나면 조용히 품질만 나빠진다:

  1. properties 표는 md 표가 아니라 `메뉴명: 출결` 같은 `키: 값` 라인으로 낸다 —
     preprocess._META_HEADER_RE 가 라인 시작 기준으로 이 4종(메뉴명/시기/연번/태그)을
     지우기 때문이다. md 표로 내면 분류 메타가 답변 본문에 그대로 노출된다(#24).
  2. 이미지는 `![alt](src)` 로, src 는 **URL 인코딩된 원본 그대로** 둔다 —
     pipeline._rewrite_image_refs 가 unquote 해서 assets 매핑에 대조한다.
  3. 외부 URL 이미지(Notion 속성 아이콘 등)는 버린다. 로컬 자산이 아니라서
     copy_assets 매핑에 없고, 남기면 깨진 참조만 늘어난다.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

_SKIP_CONTENT = {"script", "style", "head"}
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCKS = {"p", "div", "section", "article", "header", "figure", "figcaption",
           "blockquote", "ul", "ol", "table", "tr"} | set(_HEADINGS)


def _is_external(src: str) -> bool:
    return src.startswith(("http://", "https://", "//", "data:"))


class _NotionHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip_depth = 0
        self._in_property_table = 0
        self._cell: list[str] | None = None      # 현재 th/td 텍스트 버퍼
        self._row: list[str] = []                # [th텍스트, td텍스트]
        self._list_stack: list[str] = []         # 'ul' | 'ol'
        self._ol_index: list[int] = []
        self._pending_marker: str | None = None  # li 시작 시 붙일 불릿

    # ── 출력 헬퍼 ──────────────────────────────────────────────────────
    def _emit(self, text: str) -> None:
        if self._cell is not None:
            self._cell.append(text)
        else:
            self.out.append(text)

    def _newline(self, n: int = 1) -> None:
        if self._cell is not None:
            return
        self.out.append("\n" * n)

    # ── 태그 ───────────────────────────────────────────────────────────
    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = dict(attrs_list)
        if tag in _SKIP_CONTENT:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "table":
            # Notion 의 속성 표만 키:값 라인으로 편다. 본문 표는 일반 처리.
            if "properties" in (attrs.get("class") or ""):
                self._in_property_table += 1
            self._newline(2)
        elif tag == "tr":
            self._row = []
        elif tag in ("th", "td"):
            self._cell = []
        elif tag in _HEADINGS:
            self._newline(2)
            self._emit("#" * _HEADINGS[tag] + " ")
        elif tag == "br":
            self._newline()
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            # 이탤릭 마커는 붙이지 않고 텍스트만 남긴다. 본문에 확장자 표기('*vtt,
            # *smi, *srt')처럼 리터럴 '*' 가 섞여 있어 마커를 감싸면 짝이 어긋나
            # 오히려 문장이 깨진다. 강조 자체는 답변 내용에 기여하지 않는다.
            # <strong>(**)은 유지한다 — generation/faq.faq_answer 가 '**답변**'
            # 라벨을 정규식으로 떼어내는 데 쓴다.
            pass
        elif tag == "code":
            self._emit("`")
        elif tag in ("ul", "ol"):
            self._list_stack.append(tag)
            if tag == "ol":
                # Notion 은 번호 항목을 하나씩 별개의 <ol> 로 감싸고 순번을 start 로
                # 넘긴다(start="1", start="2", …). 이걸 무시하면 모든 항목이 '1.' 이
                # 되어 절차 문서의 단계 번호가 통째로 뭉개진다.
                try:
                    start = int(attrs.get("start") or 1)
                except ValueError:
                    start = 1
                self._ol_index.append(start - 1)
            self._newline()
        elif tag == "li":
            depth = max(0, len(self._list_stack) - 1)
            if self._list_stack and self._list_stack[-1] == "ol":
                self._ol_index[-1] += 1
                marker = f"{self._ol_index[-1]}. "
            else:
                marker = "- "
            self._pending_marker = "  " * depth + marker
        elif tag == "blockquote":
            self._newline(2)
            self._emit("> ")
        elif tag == "img":
            src = attrs.get("src") or ""
            if src and not _is_external(src):
                self._emit(f"![{attrs.get('alt') or ''}]({src})")
        elif tag == "a":
            # 링크는 표시 텍스트만 남긴다. clean_markdown 이 어차피 `[t](url)` →
            # `t` 로 접으므로, 여기서 md 링크를 만들 이유가 없다.
            pass
        elif tag in _BLOCKS:
            self._newline(2)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_CONTENT:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag in ("th", "td"):
            text = re.sub(r"\s+", " ", "".join(self._cell or [])).strip()
            self._cell = None
            self._row.append(text)
        elif tag == "tr":
            self._flush_row()
        elif tag == "table":
            if self._in_property_table:
                self._in_property_table -= 1
            self._newline(2)
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            pass  # 여는 쪽과 대칭 — 이탤릭 마커는 내지 않는다.
        elif tag == "code":
            self._emit("`")
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            if tag == "ol" and self._ol_index:
                self._ol_index.pop()
            self._newline()
        elif tag == "li":
            self._newline()
        elif tag in _BLOCKS:
            self._newline(2)

    def _flush_row(self) -> None:
        cells = [c for c in self._row if c]
        self._row = []
        if not cells:
            return
        if self._in_property_table and len(cells) >= 2:
            # `메뉴명: 출결` — preprocess._META_HEADER_RE 가 잡는 형식.
            self.out.append(f"{cells[0]}: {' '.join(cells[1:])}\n")
        else:
            self.out.append(" | ".join(cells) + "\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data.strip():
            # 셀 안에서는 공백도 단어 구분에 필요하다.
            if self._cell is not None and data.strip() == "" and data:
                self._cell.append(" ")
            return
        if self._pending_marker is not None:
            self._emit(self._pending_marker)
            self._pending_marker = None
        self._emit(data)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in ("img", "br"):
            self.handle_endtag(tag)


_MULTI_BLANK = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+\n")


def html_to_markdown(source: str) -> str:
    """Notion export HTML 한 편 → Markdown 텍스트."""
    parser = _NotionHTMLParser()
    parser.feed(source)
    parser.close()
    text = "".join(parser.out)
    text = _TRAILING_WS.sub("\n", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    # unescape 를 다시 부르지 않는다 — convert_charrefs=True 라 파서가 이미 풀었고,
    # 한 번 더 돌리면 본문의 리터럴 '&amp;' 가 '&' 로 잘못 접힌다.
    return text.strip() + "\n"


def convert_html_files(raw_dir: Path) -> int:
    """raw_dir 의 .html 을 같은 이름 .md 로 변환한다. 반환값은 새로 만든 개수.

    이미 .md 가 있으면 건드리지 않는다 — 진짜 Markdown export 가 함께 있으면
    그쪽이 원본이고, 변환본이 덮어쓰면 품질이 떨어진다."""
    made = 0
    for h in sorted(raw_dir.rglob("*.html")):
        md = h.with_suffix(".md")
        if md.exists():
            continue
        md.write_text(html_to_markdown(h.read_text(encoding="utf-8")), encoding="utf-8")
        made += 1
    return made
