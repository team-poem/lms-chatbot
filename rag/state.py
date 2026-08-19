from __future__ import annotations
from dataclasses import dataclass

from config import AppConfig
from gemini_keys import KeyRing
from generation.llm import GEMINI, LLMConfig
from index.bm25 import BM25Pack, load_bm25
from index.embed import Embedder, build_embed_config, load_embedder
from index.vector_store import get_chroma_client


@dataclass(frozen=True)
class RagState:
    # SentenceTransformer 로 좁히지 않는다 — gemini 임베딩 백엔드에선 torch 가
    # 아예 올라오지 않는데, 여기서 그 타입을 참조하면 임포트가 되살아난다.
    embedder: Embedder
    chroma: object  # chromadb.api.ClientAPI — 외부 타입 직접 노출 회피
    bm25: BM25Pack
    llm: LLMConfig
    qna_contact: str = ""


def build_llm_config(config: AppConfig) -> LLMConfig:
    """AppConfig 의 평평한 환경변수들을 백엔드 하나로 접는다.

    Gemini 인데 키가 없으면 여기서 즉시 실패시킨다. 그대로 두면 첫 질문이 들어온
    뒤에야 401 로 드러나고, 관련성 게이트는 예외를 삼켜(None=통과) 증상이 '답변이
    빈다'로만 보인다 — 부팅 때 잡는 편이 훨씬 싸다."""
    if config.llm_provider == GEMINI and not config.gemini_api_keys:
        raise RuntimeError(
            "LLM_PROVIDER=gemini 인데 GEMINI_API_KEY 가 비어 있습니다 "
            "(GEMINI_API_KEY2·3 은 선택). "
            ".env 에 키를 넣거나 LLM_PROVIDER=ollama 로 되돌리십시오."
        )
    return LLMConfig(
        provider=config.llm_provider,
        model=(
            config.gemini_model
            if config.llm_provider == GEMINI
            else config.ollama_model
        ),
        host=config.ollama_host,
        api_key=KeyRing(config.gemini_api_keys),
    )


def load_rag_state(config: AppConfig) -> RagState:
    return RagState(
        # EMBED_PROVIDER 로 갈린다. 기본 local(BGE-M3)이라 기존 배포는 그대로다.
        # 모델명은 build_embed_config 가 백엔드별로 알맞은 환경변수(EMBED_MODEL /
        # GEMINI_EMBED_MODEL)에서 읽는다 — config.embed_model 을 넘기면 gemini
        # 모드에서 모델명이 'BAAI/bge-m3' 로 덮인다.
        embedder=load_embedder(build_embed_config()),
        chroma=get_chroma_client(config.chroma_dir),
        bm25=load_bm25(config.bm25_path),
        llm=build_llm_config(config),
        qna_contact=config.qna_contact,
    )
