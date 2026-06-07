from rag.state import RagState
from config import load_config


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


def test_qna_contact_defaults_empty(monkeypatch):
    monkeypatch.delenv("QNA_CONTACT", raising=False)
    monkeypatch.setattr("config.load_dotenv", lambda *a, **k: None)
    assert load_config().qna_contact == ""


def test_ragstate_carries_qna_fields():
    st = RagState(
        embedder=None, chroma=None, bm25=None,
        ollama_host="h", ollama_model="m", qna_board_url="u", qna_contact="c",
    )
    assert st.qna_board_url == "u"
    assert st.qna_contact == "c"
