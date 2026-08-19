"""문서 중간표현(IR) — 어디서 왔든 같은 모양으로 접는다.

노션에서 긁어온 블록과 이미 인덱싱된 export 마크다운을 **직접** 비교하면 포맷
차이(HTML 잔재, 공백, 링크 표기)가 전부 '변경'으로 잡힌다. 둘 다 IR 로 한 번
접고 나서 비교해야 실제 내용 변화만 남는다.

IR 모델은 kordoc(https://github.com/chrisryugj/kordoc, MIT)의 IRBlock 을 필요한
만큼만 옮겼다. 원본은 HWP·PDF 를 다루느라 bbox·각주·페이지번호까지 들고 있는데,
여기서 쓰는 것은 텍스트·표·이미지·헤딩 레벨뿐이다.

지금 어댑터는 markdown → IR 하나다(`from_markdown`). 노션 → IR 어댑터가 붙으면
같은 IR 을 내놓기만 하면 되고, 비교(sync/diff.py)는 손대지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# 블록 종류. 노션 블록 타입도 여기로 접힌다
# (paragraph→text, heading_1~3→heading, bulleted/numbered_list_item→list, …).
TEXT = "text"
HEADING = "heading"
LIST = "list"
TABLE = "table"
IMAGE = "image"
CODE = "code"
SEPARATOR = "separator"


@dataclass(frozen=True)
class Block:
    type: str
    text: str = ""
    level: int = 0                       # heading 전용 (1~6)
    ordered: bool = False                # list 전용
    rows: tuple[tuple[str, ...], ...] = ()   # table 전용
    src: str = ""                        # image 전용 (원본 경로/URL)

    def compare_text(self) -> str:
        """유사도 비교에 쓸 텍스트. 표는 셀을 이어 붙인다."""
        if self.type == TABLE:
            return " ".join(c for row in self.rows for c in row)
        return self.text


@dataclass(frozen=True)
class Document:
    """비교 단위. page_id 가 노션 페이지와 로컬 파일을 잇는 열쇠다."""

    page_id: str
    title: str
    blocks: tuple[Block, ...] = field(default_factory=tuple)


_WS_RE = re.compile(r"\s+")


def normalize(s: str) -> str:
    """공백 접기. 비교·해시가 **같은 기준**을 써야 한다 — 한쪽만 정규화하면
    공백만 바뀐 문서가 '내용 변경'으로 잡혀 불필요하게 다시 받아온다."""
    return _WS_RE.sub(" ", s).strip()


# ── markdown → IR ──────────────────────────────────────────────────
_H_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_IMG_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]*)\)\s*$")
_HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
# 파일명 끝의 노션 page id. export 는 '제목 <32hex>.md' 로 떨어진다.
_PAGE_ID_RE = re.compile(r"\s([0-9a-f]{32})$")


def page_id_of(path: Path) -> str:
    """파일명 끝 32자리 hex → 노션 page id. 없으면 빈 문자열."""
    m = _PAGE_ID_RE.search(path.stem)
    return m.group(1) if m else ""


def _table_row(line: str) -> tuple[str, ...]:
    cells = line.strip().strip("|").split("|")
    return tuple(c.strip() for c in cells)


def from_markdown(text: str) -> tuple[Block, ...]:
    """마크다운 → 블록 목록.

    범용 파서가 아니다 — 노션 export 가 실제로 내는 것(헤딩·문단·목록·표·이미지·
    구분선·코드펜스)만 다룬다. 인라인 강조는 비교에 영향이 없어 텍스트로 남긴다.
    """
    blocks: list[Block] = []
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush_para() -> None:
        if para:
            body = " ".join(l.strip() for l in para).strip()
            if body:
                blocks.append(Block(type=TEXT, text=body))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        if stripped.startswith("```"):
            flush_para()
            fence, body = stripped[:3], []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                body.append(lines[i])
                i += 1
            i += 1                                  # 닫는 펜스
            blocks.append(Block(type=CODE, text="\n".join(body)))
            continue

        if _HR_RE.match(stripped):
            flush_para()
            blocks.append(Block(type=SEPARATOR))
            i += 1
            continue

        m = _IMG_RE.match(stripped)
        if m:
            flush_para()
            blocks.append(Block(type=IMAGE, text=m.group(1), src=m.group(2)))
            i += 1
            continue

        m = _H_RE.match(stripped)
        if m:
            flush_para()
            blocks.append(Block(type=HEADING, level=len(m.group(1)), text=m.group(2).strip()))
            i += 1
            continue

        # 표: 헤더 줄 다음이 구분선일 때만 표로 본다. 본문에 '|' 가 섞인 문장을
        # 표로 오인하면 블록 경계가 통째로 어긋난다.
        if "|" in stripped and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            flush_para()
            rows = [_table_row(stripped)]
            i += 2
            while i < len(lines) and "|" in lines[i]:
                rows.append(_table_row(lines[i]))
                i += 1
            blocks.append(Block(type=TABLE, rows=tuple(rows)))
            continue

        m = _UL_RE.match(line) or _OL_RE.match(line)
        if m:
            flush_para()
            blocks.append(Block(type=LIST, text=m.group(1).strip(),
                                ordered=bool(_OL_RE.match(line))))
            i += 1
            continue

        para.append(line)
        i += 1

    flush_para()
    return tuple(blocks)


def document_from_file(path: Path) -> Document:
    """export .md 한 장 → Document. 제목은 파일명에서 뽑는다(본문 헤딩이 아니라)."""
    pid = page_id_of(path)
    title = path.stem[: -(len(pid) + 1)].strip() if pid else path.stem
    return Document(page_id=pid, title=title,
                    blocks=from_markdown(path.read_text(encoding="utf-8")))
