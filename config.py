from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    ollama_host: str
    ollama_model: str
    embed_model: str
    chroma_dir: Path
    bm25_path: Path
    logs_db_path: Path
    assets_dir: Path
    raw_dir: Path
    port: int
    admin_token: str | None = None
    qna_board_url: str = ""
    qna_contact: str = ""


def load_config() -> AppConfig:
    load_dotenv()
    return AppConfig(
        ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "gemma3:4b"),
        embed_model=os.environ.get("EMBED_MODEL", "BAAI/bge-m3"),
        chroma_dir=Path(os.environ.get("CHROMA_DIR", "./data/chroma")),
        bm25_path=Path(os.environ.get("BM25_PATH", "./data/bm25.pkl")),
        logs_db_path=Path(os.environ.get("LOGS_DB_PATH", "./data/logs/chat_logs.db")),
        assets_dir=Path(os.environ.get("ASSETS_DIR", "./data/assets")),
        raw_dir=Path(os.environ.get("RAW_DIR", "./data/raw")),
        port=int(os.environ.get("PORT", "8080")),
        # 관리자 로그 조회 토큰. 미설정이면 /admin/logs 는 비활성(404).
        admin_token=os.environ.get("ADMIN_TOKEN") or None,
        # 매뉴얼에 근거 없는 질문을 안내할 QnA 게시판 URL. 동서대 e-Class QnA 게시판이
        # 기본값이며, 다른 배포에선 QNA_BOARD_URL 로 덮어쓴다.
        qna_board_url=os.environ.get(
            "QNA_BOARD_URL",
            "https://eclass1.dongseo.ac.kr/catalogs/5c5d29852b16ce2565531c02/boards_v2/3/posts",
        ),
        # 폴백 안내에 함께 노출할 문의처. 기본값은 교육혁신처 교수학습개발센터 직통이며
        # QNA_CONTACT 로 덮어쓸 수 있다.
        qna_contact=os.environ.get(
            "QNA_CONTACT", "교육혁신처 교수학습개발센터 ☎ 051-320-4835"
        ),
    )
