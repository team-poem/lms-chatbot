from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

from app_types import Chunk
from config import AppConfig
from index.bm25 import build_bm25, save_bm25
from index.embed import load_embedder
from index.vector_store import get_chroma_client, reset_collection, upsert_chunks
from ingest.chunk import chunk_csv_file, chunk_markdown_file
from ingest.extract import (collect_csv, collect_images, collect_markdown,
                            copy_assets, unzip_all_recursive)
from ingest.preprocess import clean_markdown


@dataclass(frozen=True)
class IngestResult:
    chunk_count: int
    image_count: int


def _section_path_from(rel_path: Path) -> tuple[str, ...]:
    return tuple(p for p in rel_path.parts[:-1] if p not in ("", "."))


def _detect_doc_set(rel_path: Path) -> str:
    blob = " ".join(p.lower() for p in rel_path.parts)
    return "faq" if "faq" in blob else "guide"


def _rewrite_image_refs(chunk: Chunk, mapping: dict[str, str], raw_dir: Path) -> Chunk:
    """Notion .md 의 image 경로는 URL 인코딩되어 있음 (예 '%EB%A1%9C').
    파일 시스템 경로(매핑 키)는 비인코딩 한글이므로 unquote 후 조회한다.
    매핑 실패 시 빈 image_refs 로 — 깨진 /<path> 404 방지.
    """
    new_refs: list[str] = []
    new_text = chunk.text
    for ref in chunk.image_refs:
        decoded = unquote(ref)
        src_dir = Path(chunk.source).parent
        abs_path = (src_dir / decoded).resolve()
        try:
            rel_to_raw = str(abs_path.relative_to(raw_dir.resolve()))
        except ValueError:
            continue
        if rel_to_raw in mapping:
            url = mapping[rel_to_raw]
            new_text = new_text.replace(f"({ref})", f"({url})")
            new_text = new_text.replace(f"({decoded})", f"({url})")
            new_refs.append(url)
    return replace(chunk, text=new_text, image_refs=tuple(new_refs))


def collect_chunks(
    config: AppConfig, *, log: Callable[[str], None] = print
) -> list[Chunk]:
    """raw_dir의 md를 정제·청킹하여 청크 리스트를 만든다. 이미지 매핑 적용 포함.

    답변 컬럼이 없는 FAQ CSV(질문 + 분류 메타데이터만 담긴 파일)는 인덱싱하지
    않는다. 동일 질문의 md 본문과 중복이며 답변이 없어 검색 노이즈만 유발한다.
    """
    raw_dir = config.raw_dir
    images = collect_images(raw_dir)
    img_mapping = copy_assets(images, raw_dir, config.assets_dir)
    log(f"    이미지 {len(img_mapping)}개")

    all_chunks: list[Chunk] = []
    for md in collect_markdown(raw_dir):
        rel = md.relative_to(raw_dir)
        doc_set = _detect_doc_set(rel)
        section_path = list(_section_path_from(rel))
        text = clean_markdown(md.read_text(encoding="utf-8"))
        md.write_text(text, encoding="utf-8")
        for c in chunk_markdown_file(md, doc_set=doc_set, section_path=section_path):
            all_chunks.append(_rewrite_image_refs(c, img_mapping, raw_dir))
    return all_chunks


def run_ingest(config: AppConfig, *, log: Callable[[str], None] = print) -> IngestResult:
    raw_dir = config.raw_dir
    chroma_dir = config.chroma_dir
    bm25_path = config.bm25_path

    log(f"[1/5] zip 재귀 풀기: {raw_dir}")
    unzip_all_recursive(raw_dir)

    log("[2/5] assets 복사 + [3/5] 청크 생성")
    all_chunks = collect_chunks(config, log=log)
    img_count = len(collect_images(raw_dir))
    log(f"    총 청크: {len(all_chunks)}")

    if not all_chunks:
        log("청크가 0개입니다. data/raw 에 Notion export 가 있는지 확인하세요.")
        return IngestResult(chunk_count=0, image_count=img_count)

    log(f"[4/5] 임베딩 + ChromaDB ({chroma_dir})")
    embedder = load_embedder(config.embed_model)
    client = get_chroma_client(chroma_dir)
    # 재인덱싱은 전체 재빌드 — 입력에 없는 stale 청크가 남지 않도록 컬렉션을 비운다.
    reset_collection(client)
    upsert_chunks(client, embedder, all_chunks)

    log(f"[5/5] BM25 인덱스 저장 ({bm25_path})")
    pack = build_bm25(all_chunks)
    save_bm25(pack, bm25_path)

    log("완료")
    return IngestResult(chunk_count=len(all_chunks), image_count=img_count)
