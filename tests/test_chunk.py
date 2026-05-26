import pandas as pd
from pathlib import Path
from ingest.chunk import chunk_markdown_file, chunk_csv_file, extract_image_refs


def test_extract_image_refs_finds_paths():
    md = "본문\n![](images/a.png)\n중간\n![캡션](images/b.png)"
    assert extract_image_refs(md) == ["images/a.png", "images/b.png"]


def test_extract_image_refs_dedup_preserve_order():
    md = "![](x.png)\n![](y.png)\n![](x.png)"
    assert extract_image_refs(md) == ["x.png", "y.png"]


def test_chunk_markdown_small_returns_single(tmp_path: Path):
    p = tmp_path / "퀴즈 개요 abcdef1234567890.md"
    p.write_text("# 퀴즈 개요\n\n본문 짧음\n\n![](img/q.png)\n", encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=["시험 및 설문"])
    assert len(chunks) == 1
    c = chunks[0]
    assert c.title == "퀴즈 개요"
    assert c.image_refs == ["img/q.png"]
    assert c.section_path == ["시험 및 설문"]
    assert c.doc_set == "guide"
    assert c.source.endswith("퀴즈 개요 abcdef1234567890.md")


def test_chunk_markdown_large_splits_on_h2(tmp_path: Path):
    body_a = "단어 " * 1200
    body_b = "단어 " * 1200
    text = f"# 큰 페이지\n\n## 섹션 A\n\n{body_a}\n\n## 섹션 B\n\n{body_b}\n"
    p = tmp_path / "큰페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert len(chunks) == 2
    assert chunks[0].title == "큰페이지 — 섹션 A"
    assert chunks[1].title == "큰페이지 — 섹션 B"


def test_chunk_csv_each_row_becomes_chunk(tmp_path: Path):
    p = tmp_path / "FAQ.csv"
    pd.DataFrame({
        "FAQ": ["로그인이 안 됩니다", "수업계획서 입력 방법"],
        "메뉴명": ["기본", "수업계획서"],
        "시기": ["1.학기초", "1.학기초"],
        "연번": [1, 15],
        "태그": ["로그인", "수업계획서"],
    }).to_csv(p, index=False)
    chunks = chunk_csv_file(p, doc_set="faq")
    assert len(chunks) == 2
    assert "로그인이 안 됩니다" in chunks[0].text
    assert "기본" in chunks[0].text
    assert chunks[0].doc_set == "faq"
    assert chunks[0].title.startswith("FAQ")
