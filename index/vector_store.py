from __future__ import annotations
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from app_types import Chunk
from index.embed import encode_texts


_COLLECTION = "lms_chunks"


def get_chroma_client(persist_dir: Path):
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def get_collection(client):
    return client.get_or_create_collection(_COLLECTION)


def upsert_chunks(client, model: SentenceTransformer, chunks: list[Chunk]) -> None:
    if not chunks:
        return
    coll = get_collection(client)
    ids = [c.chunk_id for c in chunks]
    docs = [c.text for c in chunks]
    metas = [{
        "source": c.source,
        "doc_set": c.doc_set,
        "title": c.title,
        "section_path": " > ".join(c.section_path),
        "image_refs": ",".join(c.image_refs),
        "notion_url": c.notion_url,
    } for c in chunks]
    vecs = encode_texts(model, docs)
    coll.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)


def query_embed(client, model: SentenceTransformer, query: str, k: int = 20) -> list[tuple[str, float]]:
    coll = get_collection(client)
    qvec = encode_texts(model, [query])[0]
    res = coll.query(query_embeddings=[qvec], n_results=k)
    ids = res["ids"][0]
    dists = res["distances"][0]
    # cosine 거리(0~2) → 유사도(0~1)
    return [(i, max(0.0, 1.0 - d / 2.0)) for i, d in zip(ids, dists)]
