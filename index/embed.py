from __future__ import annotations
import os

from sentence_transformers import SentenceTransformer


_MAX_SEQ_LEN = 1024  # CPU 추론 안전선 (BGE-M3 spec은 8192이나 메모리 폭주 방지)


def load_embedder(model_name: str | None = None) -> SentenceTransformer:
    name = model_name or os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
    model = SentenceTransformer(name)
    model.max_seq_length = _MAX_SEQ_LEN
    return model


def encode_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    vecs = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=4,
    )
    return [v.tolist() for v in vecs]
