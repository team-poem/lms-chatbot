from __future__ import annotations
import hashlib
import re
from pathlib import Path

import pandas as pd

from retrieval.types import Chunk, DocSet


_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_H2_RE = re.compile(r"^##\s+(.+)$", flags=re.MULTILINE)
_TOKEN_LIMIT = 2000


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


def _derive_title(path: Path) -> str:
    name = path.stem
    parts = name.rsplit(" ", 1)
    if len(parts) == 2 and len(parts[1]) >= 16:
        return parts[0]
    return name


def chunk_markdown_file(
    path: Path,
    *,
    doc_set: DocSet,
    section_path: list[str],
) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    title = _derive_title(path)
    source = str(path)

    if _approx_tokens(text) <= _TOKEN_LIMIT:
        return [
            Chunk(
                chunk_id=_hash_id(source, "0"),
                text=text,
                source=source,
                doc_set=doc_set,
                title=title,
                section_path=list(section_path),
                image_refs=extract_image_refs(text),
            )
        ]

    matches = list(_H2_RE.finditer(text))
    if not matches:
        return [
            Chunk(
                chunk_id=_hash_id(source, "0"),
                text=text,
                source=source,
                doc_set=doc_set,
                title=title,
                section_path=list(section_path),
                image_refs=extract_image_refs(text),
            )
        ]

    chunks: list[Chunk] = []
    for i, m in enumerate(matches):
        section_title = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        chunks.append(
            Chunk(
                chunk_id=_hash_id(source, str(i)),
                text=body,
                source=source,
                doc_set=doc_set,
                title=f"{title} — {section_title}",
                section_path=list(section_path),
                image_refs=extract_image_refs(body),
            )
        )
    return chunks


def chunk_csv_file(path: Path, *, doc_set: DocSet) -> list[Chunk]:
    df = pd.read_csv(path)
    source = str(path)
    base_title = f"FAQ — {_derive_title(path)}"
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
            )
        )
    return chunks
