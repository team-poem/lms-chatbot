from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ingest.extract import (
    unzip_all_recursive, collect_markdown, collect_csv,
    collect_images, copy_assets,
)
from ingest.preprocess import clean_markdown
from ingest.chunk import chunk_markdown_file, chunk_csv_file
from index.embed import Embedder, get_chroma, upsert_chunks
from index.bm25_index import build_bm25, save_bm25
from retrieval.types import Chunk


def _section_path_from(rel_path: Path) -> list[str]:
    return [p for p in rel_path.parts[:-1] if p not in ("", ".")]


def _detect_doc_set(rel_path: Path) -> str:
    blob = " ".join(p.lower() for p in rel_path.parts)
    if "faq" in blob:
        return "faq"
    return "guide"


def _rewrite_image_refs(chunk: Chunk, mapping: dict[str, str], raw_dir: Path) -> Chunk:
    new_refs: list[str] = []
    new_text = chunk.text
    for ref in chunk.image_refs:
        src_dir = Path(chunk.source).parent
        abs_path = (src_dir / ref).resolve()
        try:
            rel_to_raw = str(abs_path.relative_to(raw_dir.resolve()))
        except ValueError:
            continue
        if rel_to_raw in mapping:
            url = mapping[rel_to_raw]
            new_text = new_text.replace(f"({ref})", f"({url})")
            new_refs.append(url)
    return Chunk(
        chunk_id=chunk.chunk_id,
        text=new_text,
        source=chunk.source,
        doc_set=chunk.doc_set,
        title=chunk.title,
        section_path=chunk.section_path,
        image_refs=new_refs or chunk.image_refs,
        csv_refs=chunk.csv_refs,
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=os.environ.get("RAW_DIR", "./data/raw"))
    parser.add_argument("--assets", default=os.environ.get("ASSETS_DIR", "./data/assets"))
    parser.add_argument("--chroma", default=os.environ.get("CHROMA_DIR", "./data/chroma"))
    parser.add_argument("--bm25", default=os.environ.get("BM25_PATH", "./data/bm25.pkl"))
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw)
    assets_dir = Path(args.assets)
    chroma_dir = Path(args.chroma)
    bm25_path = Path(args.bm25)

    print(f"[1/5] zip 재귀 풀기: {raw_dir}")
    unzip_all_recursive(raw_dir)

    print(f"[2/5] assets 복사")
    img_mapping = copy_assets(collect_images(raw_dir), raw_dir, assets_dir)
    print(f"    이미지 {len(img_mapping)}개")

    print(f"[3/5] 청크 생성")
    all_chunks: list[Chunk] = []
    for md in collect_markdown(raw_dir):
        rel = md.relative_to(raw_dir)
        doc_set = _detect_doc_set(rel)
        section_path = _section_path_from(rel)
        text = clean_markdown(md.read_text(encoding="utf-8"))
        md.write_text(text, encoding="utf-8")
        for c in chunk_markdown_file(md, doc_set=doc_set, section_path=section_path):
            all_chunks.append(_rewrite_image_refs(c, img_mapping, raw_dir))
    for csv in collect_csv(raw_dir):
        doc_set = _detect_doc_set(csv.relative_to(raw_dir))
        all_chunks.extend(chunk_csv_file(csv, doc_set=doc_set))
    print(f"    총 청크: {len(all_chunks)}")

    if not all_chunks:
        print("청크가 0개입니다. data/raw 에 Notion export 가 있는지 확인하세요.", file=sys.stderr)
        return 1

    print(f"[4/5] 임베딩 + ChromaDB ({chroma_dir})")
    embedder = Embedder()
    client = get_chroma(chroma_dir)
    upsert_chunks(client, embedder, all_chunks)

    print(f"[5/5] BM25 인덱스 저장 ({bm25_path})")
    pack = build_bm25(all_chunks)
    save_bm25(pack, bm25_path)

    print("완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
