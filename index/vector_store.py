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


def reset_collection(client):
    """컬렉션을 비우고 새로 만든다. 재인덱싱 시 더 이상 생성되지 않는 stale 청크
    (제거된 CSV 행, 본문이 바뀐 md 등)가 upsert만으로는 남기 때문에, 전체 재빌드
    전에 호출해 인덱스를 입력 데이터와 정확히 일치시킨다."""
    try:
        client.delete_collection(_COLLECTION)
    except Exception:
        pass
    return client.get_or_create_collection(_COLLECTION)


def _chunk_meta(c: Chunk) -> dict:
    # csv_refs 는 Chroma 에 저장하지 않는다(검색 후 사용처 없음 → 복원 시 ()).
    # 필드 추가 시 _chunk_from_meta 와 대칭으로 맞춰 section_id 같은 누락을 막을 것.
    return {
        "source": c.source,
        "doc_set": c.doc_set,
        "title": c.title,
        "section_id": c.section_id,
        "section_path": " > ".join(c.section_path),
        "image_refs": ",".join(c.image_refs),
        "notion_url": c.notion_url,
    }


def upsert_chunks(client, model: SentenceTransformer, chunks: list[Chunk]) -> None:
    if not chunks:
        return
    coll = get_collection(client)
    ids = [c.chunk_id for c in chunks]
    docs = [c.text for c in chunks]
    metas = [_chunk_meta(c) for c in chunks]
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
