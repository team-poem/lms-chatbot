from __future__ import annotations
import os
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from retrieval.types import Chunk


_COLLECTION = "lms_chunks"


_MAX_SEQ_LEN = 1024  # BGE-M3 supports up to 8192, but on CPU 1024 is the practical cap


class Embedder:
    def __init__(self, model_name: str | None = None) -> None:
        name = model_name or os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
        self.model = SentenceTransformer(name)
        # 토크나이저가 너무 긴 입력을 알아서 잘라내도록 강제.
        self.model.max_seq_length = _MAX_SEQ_LEN

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=4,
        )
        return [v.tolist() for v in vecs]


def get_chroma(persist_dir: Path):
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def upsert_chunks(client, embedder: Embedder, chunks: list[Chunk]) -> None:
    coll = client.get_or_create_collection(_COLLECTION)
    if not chunks:
        return
    ids = [c.chunk_id for c in chunks]
    docs = [c.text for c in chunks]
    metas = [{
        "source": c.source,
        "doc_set": c.doc_set,
        "title": c.title,
        "section_path": " > ".join(c.section_path),
        "image_refs": ",".join(c.image_refs),
    } for c in chunks]
    vecs = embedder.encode(docs)
    coll.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)


def query_embed(client, embedder: Embedder, query: str, k: int = 20) -> list[tuple[str, float]]:
    coll = client.get_or_create_collection(_COLLECTION)
    qvec = embedder.encode([query])[0]
    res = coll.query(query_embeddings=[qvec], n_results=k)
    ids = res["ids"][0]
    dists = res["distances"][0]
    return [(i, max(0.0, 1.0 - d / 2.0)) for i, d in zip(ids, dists)]
