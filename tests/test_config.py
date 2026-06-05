from rag.state import RagState
from config import load_config


def test_qna_board_url_from_env(monkeypatch):
    monkeypatch.setenv("QNA_BOARD_URL", "https://qna.example.edu/board")
    assert load_config().qna_board_url == "https://qna.example.edu/board"


def test_qna_board_url_defaults_empty(monkeypatch):
    monkeypatch.delenv("QNA_BOARD_URL", raising=False)
    # .env 에 QNA_BOARD_URL 이 없다는 전제(현재 레포 상태). load_dotenv 는 기존 env 를
    # 덮어쓰지 않으므로 미설정이면 빈 문자열.
    assert load_config().qna_board_url == ""


def test_ragstate_carries_qna_url():
    st = RagState(
        embedder=None, chroma=None, bm25=None,
        ollama_host="h", ollama_model="m", qna_board_url="u",
    )
    assert st.qna_board_url == "u"
