from __future__ import annotations
from dataclasses import dataclass

from sentence_transformers import SentenceTransformer

from config import AppConfig
from index.bm25 import BM25Pack, load_bm25
from index.embed import load_embedder
from index.vector_store import get_chroma_client


@dataclass(frozen=True)
class RagState:
    embedder: SentenceTransformer
    chroma: object  # chromadb.api.ClientAPI — 외부 타입 직접 노출 회피
    bm25: BM25Pack
    ollama_host: str
    ollama_model: str
    qna_contact: str = ""


def load_rag_state(config: AppConfig) -> RagState:
    return RagState(
        embedder=load_embedder(config.embed_model),
        chroma=get_chroma_client(config.chroma_dir),
        bm25=load_bm25(config.bm25_path),
        ollama_host=config.ollama_host,
        ollama_model=config.ollama_model,
        qna_contact=config.qna_contact,
    )
