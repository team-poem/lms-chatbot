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
    titles = [c.title for c in chunks]
    # H2 분할이 일어났고, 각 섹션이 (필요 시 추가 분할되어) 등장해야 함
    assert any("섹션 A" in t for t in titles)
    assert any("섹션 B" in t for t in titles)


def test_chunk_markdown_enforces_char_limit(tmp_path: Path):
    """H2가 없고 본문이 _MAX_CHARS(3000)를 초과하면 글자 기준으로 분할."""
    body = "한국어 본문 데이터입니다 " * 400  # 약 8000자
    p = tmp_path / "긴페이지 abcdef1234567890.md"
    p.write_text(f"# 긴 페이지\n\n{body}\n", encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 3500  # _MAX_CHARS + 약간 마진


def test_chunk_extracts_notion_url_from_filename(tmp_path: Path):
    p = tmp_path / "퀴즈 개요 34f0163ecf1481e38badf5eef5c69038.md"
    p.write_text("# 퀴즈 개요\n\n본문\n", encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert chunks[0].notion_url == "https://www.notion.so/34f0163ecf1481e38badf5eef5c69038"
    assert chunks[0].title == "퀴즈 개요"


def test_chunk_no_notion_url_when_filename_has_no_page_id(tmp_path: Path):
    p = tmp_path / "그냥파일.md"
    p.write_text("# 그냥\n\n본문\n", encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert chunks[0].notion_url == ""


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
