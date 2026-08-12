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
    nodes_overlay_path: Path
    port: int
    admin_token: str | None = None
    qna_board_url: str = ""
    qna_contact: str = ""
    # 생성 백엔드 선택. 'gemini' 면 gemini_*, 'ollama' 면 ollama_* 를 쓴다.
    # 임베딩 백엔드는 이 값과 독립이다 — EMBED_PROVIDER 로 따로 고른다
    # (index/embed.py). 생성만 gemini 로 쓰고 임베딩은 로컬로 두는 것이 기본값이다.
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    # **버전을 고정한다. `-latest` 별칭을 쓰지 않는다.**
    # 2026-08-12 실측: gemini-flash-latest 는 gemini-3.6-flash 를 가리켰고, 이 모델은
    # thinkingBudget=0 을 HTTP 400 으로 거부한다(2.5-flash 는 허용). 우리 코드는 그
    # 필드를 항상 넣으므로 별칭을 켜는 순간 모든 생성 호출이 실패한다. 자세한 경위와
    # 재검토 절차는 docs/2026-08-12-model-alias-decision.md 참조.
    gemini_model: str = "gemini-2.5-flash"
    # 요청 상한(ratelimit.py). 0 = 해당 층 비활성. /chat 은 매번 Gemini 과금이라
    # 공개 배포에서 이 값들이 유일한 비용 방어선이다.
    rl_chat_per_session: int = 100
    rl_consent_per_ip_hour: int = 100
    rl_chat_per_day: int = 3000


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
        nodes_overlay_path=Path(
            os.environ.get("NODES_OVERLAY_PATH", "./data/nodes.overlay.json")
        ),
        port=int(os.environ.get("PORT", "8080")),
        # 관리자 로그 조회 토큰. 미설정이면 /admin/logs 는 비활성(404).
        admin_token=os.environ.get("ADMIN_TOKEN") or None,
        # 매뉴얼에 근거 없는 질문을 안내할 QnA 게시판 URL. 동서대 e-Class QnA 게시판이
        # 기본값이며, 다른 배포에선 QNA_BOARD_URL 로 덮어쓴다.
        qna_board_url=os.environ.get(
            "QNA_BOARD_URL",
            "https://eclass1.dongseo.ac.kr/catalogs/5c5d29852b16ce2565531c02/boards_v2/3/posts",
        ),
        # 폴백 안내에 함께 노출할 문의처. 기본값은 비움 — 안내는 e-Class QnA 게시판만
        # 한다(전화번호 미노출). 필요 시 QNA_CONTACT 로 연락처를 덧붙일 수 있다.
        qna_contact=os.environ.get("QNA_CONTACT", ""),
        # 기본은 gemini. 로컬 Ollama 로 되돌리려면 LLM_PROVIDER=ollama.
        # 키 유무 검증은 여기서 하지 않는다 — 부팅 경로(rag.state.load_rag_state)에서
        # 한 번에 잡는다. load_config 는 테스트가 환경변수만 보고 부르는 순수 로더다.
        llm_provider=os.environ.get("LLM_PROVIDER", "gemini"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        # 캠퍼스망은 NAT 뒤에 다수 사용자가 있어 IP 상한을 빡빡하게 잡으면 강의동
        # 하나가 통째로 막힌다. 기본값은 넉넉하게 두고 운영에서 조인다.
        rl_chat_per_session=int(os.environ.get("RL_CHAT_PER_SESSION", "100")),
        rl_consent_per_ip_hour=int(os.environ.get("RL_CONSENT_PER_IP_HOUR", "100")),
        rl_chat_per_day=int(os.environ.get("RL_CHAT_PER_DAY", "3000")),
    )
