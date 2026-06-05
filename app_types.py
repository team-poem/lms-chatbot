from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


DocSet = Literal["guide", "faq"]
ChunkId = str
Score = float


@dataclass(frozen=True)
class Chunk:
    chunk_id: ChunkId
    text: str
    source: str
    doc_set: DocSet
    title: str
    section_id: str = ""
    section_path: tuple[str, ...] = ()
    image_refs: tuple[str, ...] = ()
    csv_refs: tuple[str, ...] = ()
    notion_url: str = ""


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: Score
    bm25_score: Score
    embed_score: Score


@dataclass(frozen=True)
class Source:
    title: str
    url: str = ""


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: Score


@dataclass(frozen=True)
class Retrieval:
    items: tuple[ScoredChunk, ...]
    top_score: Score
    # 후보 중 최대 원시 임베딩 유사도(정규화 전, 0~1). top_score 는 후보 집합 내
    # 정규화값이라 절대 연관도를 못 재므로, "질문이 가이드에 실제로 다뤄지는가"
    # 판단에는 이 절대 유사도를 쓴다.
    max_embed_sim: Score = 0.0


@dataclass(frozen=True)
class ChatEvent:
    """ /chat SSE 스트림 단위 이벤트.
      text: delta 채워짐 (스트리밍 토큰 일부)
      text_final: text 채워짐 (스트림 종료 시 풀 클린업 결과)
      done: images, sources, score 채워짐
      turn_id: turn_id 채워짐 (DB 저장 후 클라이언트 피드백용)
    """
    type: Literal["text", "text_final", "done", "turn_id"]
    delta: str = ""
    text: str = ""
    images: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    score: Score = 0.0
    turn_id: int | None = None
