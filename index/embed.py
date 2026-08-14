"""임베딩 백엔드 선택. local(BGE-M3) / gemini 두 어댑터 앞의 얇은 분기 층.

generation/llm.py 와 같은 구성이다 — 호출부(vector_store.py, pipeline.py)는 어느
백엔드인지 모르고 EmbedConfig 하나만 받는다.

**torch 는 지연 임포트다.** sentence_transformers 를 모듈 최상단에서 부르면
gemini 모드에서도 torch 가 통째로 올라와(상주 ~2.6GB) 저사양 인스턴스 배포가
불가능해진다. 로컬 백엔드를 실제로 고른 순간에만 임포트하므로, gemini 모드의
상주 메모리는 chroma+httpx 수준(수백 MB)에 머문다.

주의 — 백엔드를 바꾸면 벡터 공간이 달라져 기존 chroma 인덱스가 통째로 무효다.
반드시 재인덱싱해야 하고, tuning.py 의 유사도 임계값(ABS_EMBED_FLOOR 등)도
BGE-M3 실측값이라 함께 재보정해야 한다.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Protocol

from index.gemini_embed import DOCUMENT, QUERY, embed_batch
from tuning import EMBED_MAX_SEQ_LEN

LOCAL = "local"
GEMINI = "gemini"


@dataclass(frozen=True)
class EmbedConfig:
    provider: str
    model: str
    api_key: str = ""   # gemini 전용
    dim: int = 768      # gemini 전용 (출력 차원)


class Embedder(Protocol):
    """encode 하나만 있으면 된다. kind 는 문서/질문 구분으로, 비대칭 모델
    (gemini)만 실제로 사용하고 대칭 모델(BGE-M3)은 무시한다."""

    def encode(self, texts: list[str], kind: str) -> list[list[float]]: ...


class LocalEmbedder:
    """BGE-M3 로컬 추론. 대칭 모델이라 kind 를 쓰지 않는다."""

    def __init__(self, model_name: str):
        # 지연 임포트 — 이 줄이 모듈 최상단으로 올라가면 gemini 모드에서도
        # torch 가 올라온다(위 모듈 독스트링 참조).
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._model.max_seq_length = EMBED_MAX_SEQ_LEN

    def encode(self, texts: list[str], kind: str = DOCUMENT) -> list[list[float]]:
        vecs = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=4,
        )
        return [v.tolist() for v in vecs]


class GeminiEmbedder:
    """Gemini Embedding API. 문서/질문을 다르게 인코딩한다."""

    def __init__(self, api_key: str, model: str, dim: int):
        self._api_key = api_key
        self._model = model
        self._dim = dim

    def encode(self, texts: list[str], kind: str = DOCUMENT) -> list[list[float]]:
        return embed_batch(
            self._api_key, self._model, texts, kind=kind, dim=self._dim
        )


def build_embed_config(
    *, provider: str | None = None, model: str | None = None, api_key: str | None = None
) -> EmbedConfig:
    """환경변수에서 임베딩 설정을 읽는다. 인자를 주면 그쪽이 이긴다(테스트용).

    기본은 local — 임베딩 교체는 재인덱싱과 임계값 재보정을 동반하므로 조용히
    바뀌면 안 된다. 생성(LLM_PROVIDER)이 gemini 라도 임베딩은 따로 켜야 한다."""
    prov = provider if provider is not None else os.environ.get("EMBED_PROVIDER", LOCAL)
    if prov == GEMINI:
        return EmbedConfig(
            provider=GEMINI,
            model=model or os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-2"),
            api_key=api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", ""),
            dim=int(os.environ.get("EMBED_DIM", "768")),
        )
    if prov == LOCAL:
        return EmbedConfig(
            provider=LOCAL,
            model=model or os.environ.get("EMBED_MODEL", "BAAI/bge-m3"),
        )
    raise ValueError(f"알 수 없는 EMBED_PROVIDER: {prov!r} (local|gemini)")


def load_embedder(cfg: EmbedConfig | str | None = None) -> Embedder:
    """EmbedConfig → 임베더. 문자열/None 이 오면 로컬 모델명으로 해석한다
    (기존 호출 `load_embedder(config.embed_model)` 하위호환)."""
    if cfg is None or isinstance(cfg, str):
        cfg = build_embed_config(provider=LOCAL, model=cfg)
    if cfg.provider == GEMINI:
        if not cfg.api_key:
            raise RuntimeError(
                "EMBED_PROVIDER=gemini 인데 GEMINI_API_KEY 가 비어 있습니다. "
                ".env 에 키를 넣거나 EMBED_PROVIDER=local 로 되돌리십시오."
            )
        return GeminiEmbedder(cfg.api_key, cfg.model, cfg.dim)
    return LocalEmbedder(cfg.model)


def encode_texts(
    model: Embedder, texts: list[str], *, kind: str = DOCUMENT
) -> list[list[float]]:
    """문서 인덱싱은 kind=DOCUMENT, 검색 질의는 kind=QUERY 로 부른다.

    기본값이 DOCUMENT 인 이유: 인덱싱 경로가 압도적으로 많고, 질의 경로는
    vector_store.query_embed 한 곳뿐이라 그쪽만 명시하면 된다."""
    return model.encode(texts, kind)


__all__ = [
    "DOCUMENT",
    "QUERY",
    "EmbedConfig",
    "Embedder",
    "GeminiEmbedder",
    "LocalEmbedder",
    "build_embed_config",
    "encode_texts",
    "load_embedder",
]
