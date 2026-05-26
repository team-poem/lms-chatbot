from __future__ import annotations
import hashlib
import re
from pathlib import Path

import pandas as pd

from retrieval.types import Chunk, DocSet


_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_H2_RE = re.compile(r"^##\s+(.+)$", flags=re.MULTILINE)
_TOKEN_LIMIT = 2000
_MAX_CHARS = 3000  # 임베더(BGE-M3, max_seq=1024)에 안전하게 들어가는 한국어 청크 상한
_OVERLAP = 200    # 분할 시 청크간 겹침


def _hash_id(*parts: str) -> str:
    h = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def _approx_tokens(text: str) -> int:
    return len(text.split())


def extract_image_refs(text: str) -> list[str]:
    seen: list[str] = []
    for match in _IMG_RE.finditer(text):
        path = match.group(1).strip()
        if path not in seen:
            seen.append(path)
    return seen


def _split_long(text: str) -> list[str]:
    """문자 길이 _MAX_CHARS 를 넘는 본문을 약간 겹침을 주며 분할."""
    if len(text) <= _MAX_CHARS:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + _MAX_CHARS, len(text))
        # 줄바꿈 경계에서 자르기
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start + _MAX_CHARS // 2:
                end = nl
        parts.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - _OVERLAP, start + 1)
    return parts


_EMPTY_PARENS_RE = re.compile(r"\s*\(\s*\)\s*")
_PAGE_ID_RE = re.compile(r"\s([0-9a-f]{32})$")


def _derive_title(path: Path) -> str:
    name = path.stem
    parts = name.rsplit(" ", 1)
    if len(parts) == 2 and len(parts[1]) >= 16:
        name = parts[0]
    # 파일명에 있던 (📄) 같은 장식 이모지가 preprocess 단계에서 사라지고
    # () 빈 괄호만 남는 경우가 흔함 — 제거하고 공백 정리.
    from ingest.preprocess import strip_emoji
    name = strip_emoji(name)
    name = _EMPTY_PARENS_RE.sub(" ", name)
    return name.strip()


def _extract_notion_url(path: Path) -> str:
    """Notion export 파일명은 '<title> <32-hex-page-id>.md' 형태. 페이지 ID 추출하여
    notion.so URL 생성. 사용자가 본인 워크스페이스에 로그인되어 있으면 자동 리다이렉트됨.
    하위 페이지 폴더로 떨어진 .csv 등은 stem 에 페이지 ID 없을 수 있어 빈 문자열 반환."""
    m = _PAGE_ID_RE.search(path.stem)
    if not m:
        return ""
    return f"https://www.notion.so/{m.group(1)}"


def chunk_markdown_file(
    path: Path,
    *,
    doc_set: DocSet,
    section_path: list[str],
) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    title = _derive_title(path)
    source = str(path)
    notion_url = _extract_notion_url(path)

    def _emit(prefix: str, base_title: str, body: str) -> list[Chunk]:
        out: list[Chunk] = []
        parts = _split_long(body)
        for j, part in enumerate(parts):
            suffix = "" if len(parts) == 1 else f" ({j + 1}/{len(parts)})"
            out.append(
                Chunk(
                    chunk_id=_hash_id(source, prefix, str(j)),
                    text=part,
                    source=source,
                    doc_set=doc_set,
                    title=base_title + suffix,
                    section_path=list(section_path),
                    image_refs=extract_image_refs(part),
                    notion_url=notion_url,
                )
            )
        return out

    if _approx_tokens(text) <= _TOKEN_LIMIT:
        return _emit("0", title, text)

    matches = list(_H2_RE.finditer(text))
    if not matches:
        return _emit("0", title, text)

    chunks: list[Chunk] = []
    for i, m in enumerate(matches):
        section_title = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        chunks.extend(_emit(str(i), f"{title} — {section_title}", body))
    return chunks


def chunk_csv_file(path: Path, *, doc_set: DocSet) -> list[Chunk]:
    df = pd.read_csv(path)
    source = str(path)
    base_title = f"FAQ — {_derive_title(path)}"
    notion_url = _extract_notion_url(path)
    chunks: list[Chunk] = []
    for i, row in df.iterrows():
        text_parts = []
        for col, val in row.items():
            if pd.isna(val):
                continue
            text_parts.append(f"{col}: {val}")
        text = "\n".join(text_parts)
        chunks.append(
            Chunk(
                chunk_id=_hash_id(source, str(i)),
                text=text,
                source=source,
                doc_set=doc_set,
                title=base_title,
                section_path=[],
                csv_refs=[source],
                notion_url=notion_url,
            )
        )
    return chunks
