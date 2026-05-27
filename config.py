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


def load_config() -> AppConfig:
    load_dotenv()
    return AppConfig(
        ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "gemma3:4b"),
        embed_model=os.environ.get("EMBED_MODEL", "BAAI/bge-m3"),
        chroma_dir=Path(os.environ.get("CHROMA_DIR", "./data/chroma")),
        bm25_path=Path(os.environ.get("BM25_PATH", "./data/bm25.pkl")),
        logs_db_path=Path(os.environ.get("LOGS_DB_PATH", "./data/chat_logs.db")),
        assets_dir=Path(os.environ.get("ASSETS_DIR", "./data/assets")),
        raw_dir=Path(os.environ.get("RAW_DIR", "./data/raw")),
        port=int(os.environ.get("PORT", "8080")),
    )
