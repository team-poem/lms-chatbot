from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Literal


DocSet = Literal["guide", "faq"]


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source: str
    doc_set: DocSet
    title: str
    section_path: list[str] = field(default_factory=list)
    image_refs: list[str] = field(default_factory=list)
    csv_refs: list[str] = field(default_factory=list)
    notion_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float
    bm25_score: float
    embed_score: float
