from __future__ import annotations
from pathlib import Path

import pandas as pd

from config import AppConfig
from ingest.pipeline import collect_chunks


def _make_config(raw_dir: Path, tmp: Path) -> AppConfig:
    return AppConfig(
        ollama_host="http://localhost:11434",
        ollama_model="gemma3:4b",
        embed_model="BAAI/bge-m3",
        chroma_dir=tmp / "chroma",
        bm25_path=tmp / "bm25.pkl",
        logs_db_path=tmp / "logs.db",
        assets_dir=tmp / "assets",
        raw_dir=raw_dir,
        port=8080,
    )


def test_collect_chunks_skips_answerless_csv(tmp_path: Path):
    """답변 컬럼이 없는 FAQ CSV는 청킹에서 제외한다 (검색 노이즈 제거).
    같은 질문의 md 본문만 인덱싱되어야 한다."""
    raw = tmp_path / "raw"
    raw.mkdir()
    # 답변이 있는 md
    (raw / "로그인 안됨 abcdef1234567890.md").write_text(
        "# 로그인이 안 됩니다\n\n메뉴명: 기본\n태그: 로그인\n\n **답변** : 교직원 번호로 로그인하십시오.\n",
        encoding="utf-8",
    )
    # 답변 없는 CSV (질문 + 메타데이터만)
    pd.DataFrame({"FAQ": ["로그인이 안 됩니다"], "메뉴명": ["기본"]}).to_csv(
        raw / "FAQ.csv", index=False
    )

    config = _make_config(raw, tmp_path)
    chunks = collect_chunks(config)

    # CSV 청크(csv_refs 설정됨 / 'FAQ:'로 시작)가 없어야 함
    assert all(c.csv_refs == () for c in chunks), "CSV 청크가 인덱싱됨"
    assert not any(c.text.lstrip().startswith("FAQ:") for c in chunks)
    # md 본문은 인덱싱됨
    assert any("교직원 번호로 로그인" in c.text for c in chunks)


def test_collect_chunks_strips_metaheader_from_md(tmp_path: Path):
    """md 본문에 인덱싱되는 청크 텍스트에 메타헤더가 남지 않는다 (#24)."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "푸시 알림 abcdef1234567890.md").write_text(
        "# 앱 푸시 알림이 너무 많이 오는데 어떻게 해야 하나요?\n\n"
        "메뉴명: 모바일 앱\n시기: 2.학기중\n연번: 1\n태그: 알림\n\n"
        " **답변** : 알림은 [계정] - [알림] 메뉴에서 설정할 수 있습니다.\n",
        encoding="utf-8",
    )
    config = _make_config(raw, tmp_path)
    chunks = collect_chunks(config)
    joined = "\n".join(c.text for c in chunks)
    for label in ("메뉴명:", "시기:", "연번:", "태그:"):
        assert label not in joined, f"{label} 메타헤더가 청크에 남음"
    assert "[계정] - [알림] 메뉴" in joined
