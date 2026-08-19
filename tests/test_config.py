from pathlib import Path

import pytest

from config import AppConfig, load_config
from generation.llm import GEMINI, LLMConfig
from rag.state import RagState, build_llm_config


def test_qna_board_url_from_env(monkeypatch):
    monkeypatch.setenv("QNA_BOARD_URL", "https://qna.example.edu/board")
    assert load_config().qna_board_url == "https://qna.example.edu/board"


def test_qna_board_url_defaults_to_eclass(monkeypatch):
    monkeypatch.delenv("QNA_BOARD_URL", raising=False)
    # load_config 내부의 load_dotenv 가 .env 를 읽어 값을 덮지 않도록 차단해
    # 테스트를 환경 독립적으로 만든다.
    monkeypatch.setattr("config.load_dotenv", lambda *a, **k: None)
    assert "eclass1.dongseo.ac.kr" in load_config().qna_board_url


def test_qna_contact_from_env(monkeypatch):
    monkeypatch.setenv("QNA_CONTACT", "교육혁신처 051-320-0000")
    assert load_config().qna_contact == "교육혁신처 051-320-0000"


def test_qna_contact_defaults_empty_no_phone(monkeypatch):
    # 기본값은 비움 — 문의 안내는 QnA 게시판만, 전화번호 미노출.
    monkeypatch.delenv("QNA_CONTACT", raising=False)
    monkeypatch.setattr("config.load_dotenv", lambda *a, **k: None)
    assert load_config().qna_contact == ""


def test_ragstate_carries_qna_contact():
    st = RagState(
        embedder=None, chroma=None, bm25=None,
        llm=LLMConfig(provider="ollama", model="m", host="h"), qna_contact="c",
    )
    assert st.qna_contact == "c"


def test_llm_provider_defaults_to_gemini(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr("config.load_dotenv", lambda *a, **k: None)
    assert load_config().llm_provider == GEMINI


def _config(**kw) -> AppConfig:
    base = dict(
        ollama_host="http://localhost:11434", ollama_model="gemma3:4b",
        embed_model="BAAI/bge-m3", chroma_dir=Path("."), bm25_path=Path("."),
        logs_db_path=Path("."), assets_dir=Path("."), raw_dir=Path("."),
        nodes_overlay_path=Path("."), port=8080,
    )
    return AppConfig(**{**base, **kw})


def test_build_llm_config_picks_gemini_model():
    cfg = build_llm_config(
        _config(llm_provider=GEMINI, gemini_api_keys=("k",), gemini_model="gemini-2.5-flash")
    )
    assert (cfg.provider, cfg.model) == (GEMINI, "gemini-2.5-flash")
    assert cfg.api_key.current() == "k"


def test_build_llm_config_picks_ollama_model():
    cfg = build_llm_config(_config(llm_provider="ollama"))
    assert (cfg.provider, cfg.model, cfg.host) == (
        "ollama", "gemma3:4b", "http://localhost:11434"
    )


def test_build_llm_config_rejects_gemini_without_key():
    # 부팅 때 잡지 않으면 첫 질문에서 401 → 게이트가 예외를 삼켜 '답이 빈다'로만 보인다.
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_llm_config(_config(llm_provider=GEMINI, gemini_api_keys=()))
