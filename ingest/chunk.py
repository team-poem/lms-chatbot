from __future__ import annotations
import hashlib
import re
from pathlib import Path

import pandas as pd

from app_types import Chunk, DocSet


# 이미지 경로에 괄호가 들어갈 수 있다 — Notion 폴더명 '... (📄)' 가 URL 인코딩돼도
# 경로 안에 리터럴 '( )' 가 남는다. 단순 [^)]+ 는 첫 ')' 에서 잘려 경로 절반(이미지
# 46%)을 깨뜨렸다. 한 단계 균형 괄호 '(...)' 를 경로의 일부로 허용해 전체를 잡는다.
_IMG_RE = re.compile(r"!\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)")
# H2·H3 헤딩으로 섹션 분할. H1(#)은 페이지 제목이라 분할 대상이 아니다.
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$", flags=re.MULTILINE)
_H1_LINE_RE = re.compile(r"^#\s+.*$", flags=re.MULTILINE)
_MAX_CHARS = 3000  # 임베더(BGE-M3, max_seq=1024)에 안전하게 들어가는 한국어 청크 상한
_OVERLAP = 200    # 분할 시 청크간 겹침


def _hash_id(*parts: str) -> str:
    h = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def extract_image_refs(text: str) -> list[str]:
    seen: list[str] = []
    for match in _IMG_RE.finditer(text):
        path = match.group(1).strip()
        if path not in seen:
            seen.append(path)
    return seen


_ANY_HEADING_RE = re.compile(r"^#{1,6}\s+.*$", flags=re.MULTILINE)


def is_contentful(chunk: Chunk) -> bool:
    """검색·답변에 쓸모 있는 본문이 있는가. 헤딩만 있거나 'Untitled'(노션의 빈
    이미지 블록 잔재)뿐인 껍데기 청크는 검색 노이즈라 인덱싱에서 뺀다. 단 이미지가
    있으면 캡션 없는 그림 섹션이라도 가치가 있으므로 유지한다."""
    if chunk.image_refs:
        return True
    body = _ANY_HEADING_RE.sub("", chunk.text).replace("Untitled", "").strip()
    return len(body) >= 15


def _clean_heading(s: str) -> str:
    return s.strip().strip("*").strip()


def _has_meaningful_preamble(preamble: str) -> bool:
    """첫 헤딩 앞 본문이 의미 있는가. 이미지가 있거나, H1 제목 줄을 뺀 텍스트가
    남으면 별도 청크로 보존한다. 제목만 있는 preamble 은 버린다."""
    if extract_image_refs(preamble):
        return True
    body = _H1_LINE_RE.sub("", preamble)
    return bool(body.strip())


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

    seq = [0]

    def _emit(prefix: str, base_title: str, body: str) -> list[Chunk]:
        out: list[Chunk] = []
        parts = _split_long(body)
        section_id = _hash_id(source, prefix)  # 같은 섹션의 길이분할 연속분이 공유
        for j, part in enumerate(parts):
            suffix = "" if len(parts) == 1 else f" ({j + 1}/{len(parts)})"
            out.append(
                Chunk(
                    chunk_id=_hash_id(source, prefix, str(j)),
                    section_id=section_id,
                    doc_title=title,
                    seq=seq[0],
                    text=part,
                    source=source,
                    doc_set=doc_set,
                    title=base_title + suffix,
                    section_path=tuple(section_path),
                    image_refs=tuple(extract_image_refs(part)),
                    notion_url=notion_url,
                )
            )
            seq[0] += 1
        return out

    matches = list(_HEADING_RE.finditer(text))
    # 헤딩이 2개 미만이면 분할하지 않는다(단순 페이지 과편화 방지).
    # 본문이 _MAX_CHARS 를 넘으면 _emit 내부의 _split_long 이 글자 기준으로 처리.
    if len(matches) < 2:
        return _emit("0", title, text)

    chunks: list[Chunk] = []
    preamble = text[: matches[0].start()]
    if _has_meaningful_preamble(preamble):
        chunks.extend(_emit("pre", title, preamble))
    for i, m in enumerate(matches):
        section_title = _clean_heading(m.group(2)) or f"섹션 {i + 1}"
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
                section_id=_hash_id(source, str(i)),
                doc_title=base_title,
                seq=i,
                text=text,
                source=source,
                doc_set=doc_set,
                title=base_title,
                section_path=(),
                csv_refs=(source,),
                notion_url=notion_url,
            )
        )
    return chunks
