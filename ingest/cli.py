from __future__ import annotations
import argparse

from config import load_config
from ingest.pipeline import run_ingest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Notion export(data/raw/)를 청크/임베딩/BM25 인덱스로 변환."
    )
    parser.parse_args(argv)  # 옵션은 env 로 제어, 추후 필요 시 인자 추가
    config = load_config()
    result = run_ingest(config)
    return 0 if result.chunk_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
