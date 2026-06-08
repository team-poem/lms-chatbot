import pandas as pd
from pathlib import Path
from ingest.chunk import chunk_markdown_file, chunk_csv_file, extract_image_refs


def test_extract_image_refs_finds_paths():
    md = "본문\n![](images/a.png)\n중간\n![캡션](images/b.png)"
    assert extract_image_refs(md) == ["images/a.png", "images/b.png"]


def test_extract_image_refs_dedup_preserve_order():
    md = "![](x.png)\n![](y.png)\n![](x.png)"
    assert extract_image_refs(md) == ["x.png", "y.png"]


def test_extract_image_refs_handles_parens_in_path():
    # Notion 폴더명에 괄호가 있으면(예 '... (📄)') URL 인코딩돼도 경로 안에
    # 리터럴 ')'가 남는다. 단순 [^)]+ 는 그 ')'에서 잘려 경로를 깨뜨리므로,
    # 균형 잡힌 한 단계 괄호는 경로의 일부로 포함해야 한다.
    md = "![Untitled](folder%20(%F0%9F%93%84)/Untitled.png)"
    assert extract_image_refs(md) == ["folder%20(%F0%9F%93%84)/Untitled.png"]


def test_extract_image_refs_handles_multiple_paren_groups():
    md = "![](a%20(x)/b%20(y)/img.png)"
    assert extract_image_refs(md) == ["a%20(x)/b%20(y)/img.png"]


def _chunk(text: str, image_refs=()):
    from app_types import Chunk
    return Chunk(
        chunk_id="c", text=text, source="s", doc_set="guide", title="t",
        section_id="sid", image_refs=tuple(image_refs),
    )


def test_is_contentful_drops_heading_only():
    from ingest.chunk import is_contentful
    assert is_contentful(_chunk("## 학기 초\n\n")) is False


def test_is_contentful_drops_untitled_stub():
    from ingest.chunk import is_contentful
    assert is_contentful(_chunk("## 학기 초\n\nUntitled\n\n")) is False


def test_is_contentful_keeps_real_body():
    from ingest.chunk import is_contentful
    assert is_contentful(_chunk("## 로그인\n\n로그인은 메인에서 진행합니다.")) is True


def test_is_contentful_keeps_image_only_section():
    from ingest.chunk import is_contentful
    assert is_contentful(_chunk("## 화면\n\n", image_refs=("/assets/a.png",))) is True


def test_chunk_markdown_small_returns_single(tmp_path: Path):
    p = tmp_path / "퀴즈 개요 abcdef1234567890.md"
    p.write_text("# 퀴즈 개요\n\n본문 짧음\n\n![](img/q.png)\n", encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=["시험 및 설문"])
    assert len(chunks) == 1
    c = chunks[0]
    assert c.title == "퀴즈 개요"
    assert c.image_refs == ("img/q.png",)
    assert c.section_path == ("시험 및 설문",)
    assert c.doc_set == "guide"
    assert c.source.endswith("퀴즈 개요 abcdef1234567890.md")


def test_chunk_markdown_two_h2_sections_split(tmp_path: Path):
    body_a = "단어 " * 1200
    body_b = "단어 " * 1200
    text = f"# 큰 페이지\n\n## 섹션 A\n\n{body_a}\n\n## 섹션 B\n\n{body_b}\n"
    p = tmp_path / "큰페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    titles = [c.title for c in chunks]
    # 헤딩 2개이므로 섹션 분할이 일어나고, 각 섹션이 (필요 시 추가 분할되어) 등장해야 함
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


def test_csv_chunk_has_unique_section_id(tmp_path: Path):
    p = tmp_path / "FAQ.csv"
    pd.DataFrame({
        "FAQ": ["로그인이 안 됩니다", "수업계획서 입력 방법"],
        "메뉴명": ["기본", "수업계획서"],
    }).to_csv(p, index=False)
    chunks = chunk_csv_file(p, doc_set="faq")
    assert chunks[0].section_id  # 비어있지 않음
    assert chunks[0].section_id != chunks[1].section_id  # 행마다 고유


def test_chunk_markdown_splits_h3_and_isolates_images(tmp_path: Path):
    text = (
        "# 로그인 페이지\n\n"
        "### 로그인\n\n로그인 설명 텍스트입니다.\n\n"
        "### 대시보드 표시 유형 선택\n\n설명\n\n![](img/dash.png)\n"
    )
    p = tmp_path / "로그인 34f0163ecf148120811ee6bae8783430.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    login = next(c for c in chunks if c.title.endswith("로그인"))
    dash = next(c for c in chunks if c.title.endswith("선택"))
    assert login.image_refs == ()                  # 로그인 섹션엔 이미지 없음
    assert dash.image_refs == ("img/dash.png",)    # 대시보드 섹션에만 이미지
    assert login.section_id != dash.section_id      # 섹션 분리


def test_same_section_long_split_shares_section_id(tmp_path: Path):
    big = "한국어 본문 데이터입니다 " * 400  # _MAX_CHARS(3000) 초과
    text = f"# 페이지\n\n## 섹션 A\n\n{big}\n\n## 섹션 B\n\n짧은 본문\n"
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    a = [c for c in chunks if "섹션 A" in c.title]
    b = [c for c in chunks if "섹션 B" in c.title]
    assert len(a) >= 2                              # 길이 분할됨
    assert len({c.section_id for c in a}) == 1      # 같은 섹션은 section_id 공유
    assert a[0].section_id != b[0].section_id       # 다른 섹션은 분리


def test_meaningful_preamble_becomes_chunk(tmp_path: Path):
    text = (
        "# 페이지 제목\n\n인트로 본문입니다.\n\n![](img/intro.png)\n\n"
        "## 섹션 A\n\n본문 A\n\n## 섹션 B\n\n본문 B\n"
    )
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    pre = next(c for c in chunks if "img/intro.png" in c.image_refs)
    assert "인트로 본문" in pre.text


def test_title_only_preamble_is_skipped(tmp_path: Path):
    text = "# 제목만\n\n## 섹션 A\n\n본문 A\n\n## 섹션 B\n\n본문 B\n"
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert len(chunks) == 2  # 제목만 있는 preamble은 청크가 안 생김


def test_single_heading_page_stays_one_chunk(tmp_path: Path):
    text = "# 페이지\n\n## 유일 섹션\n\n본문 짧음\n"
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert len(chunks) == 1  # 헤딩 1개면 분할하지 않음(과편화 방지)


def test_empty_heading_text_gets_fallback_title(tmp_path: Path):
    # 헤딩 텍스트가 장식(**)뿐이면 _clean_heading 후 빈 문자열 → 폴백 제목으로 대체.
    text = "# 페이지\n\n## **\n\n본문 A\n\n## 섹션 B\n\n본문 B\n"
    p = tmp_path / "페이지 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert not any(c.title.endswith("— ") for c in chunks)  # 깨진 제목 없음
    assert any(c.title.endswith("섹션 1") for c in chunks)   # 폴백 적용


def test_markdown_chunks_share_doc_title_and_increment_seq(tmp_path: Path):
    text = ("# 퀴즈 개요\n\n인트로\n\n![](img/a.png)\n\n"
            "## 섹션 A\n\n본문 A\n\n## 섹션 B\n\n본문 B\n")
    p = tmp_path / "퀴즈 개요 abcdef1234567890.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert all(c.doc_title == "퀴즈 개요" for c in chunks)
    seqs = [c.seq for c in chunks]
    assert seqs == list(range(len(chunks)))


def test_csv_chunks_have_doc_title_and_seq(tmp_path: Path):
    p = tmp_path / "FAQ.csv"
    pd.DataFrame({"FAQ": ["q1", "q2"], "메뉴명": ["a", "b"]}).to_csv(p, index=False)
    chunks = chunk_csv_file(p, doc_set="faq")
    assert chunks[0].doc_title and chunks[1].seq == 1
