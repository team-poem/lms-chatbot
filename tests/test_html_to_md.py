"""Notion HTML → Markdown 변환. 다운스트림과 맞물리는 지점이 회귀 표적이다.

이 변환기가 조용히 어긋나면 인덱싱은 성공하는데 검색 품질만 나빠진다 — 그래서
'변환이 됐다'가 아니라 '다음 단계가 기대하는 형식으로 됐다'를 본다.
"""
from __future__ import annotations

from ingest.chunk import extract_image_refs
from ingest.html_to_md import convert_html_files, html_to_markdown
from ingest.preprocess import clean_markdown

PROPERTY_PAGE = """
<html><body><article><header>
<h1 class="page-title">출결이 안 보입니다</h1>
<table class="properties"><tbody>
<tr class="property-row"><th><span class="icon"><img src="https://app.notion.com/icons/x.svg"/></span>메뉴명</th><td><span>출결</span></td></tr>
<tr class="property-row"><th>연번</th><td>43</td></tr>
</tbody></table></header>
<div class="page-body"><p>🙋 <strong>문의사항</strong> : 출결이 보이지 않습니다.</p>
<ul><li>조건 확인하기</li></ul>
<p>① 확인<br/>② 재확인</p></div></article></body></html>
"""


def test_properties_become_meta_lines_that_preprocess_strips():
    """속성 표는 md 표가 아니라 `키: 값` 라인이어야 한다.

    preprocess._META_HEADER_RE 가 라인 시작 기준으로 지우기 때문이다. md 표로
    나가면 '메뉴명|출결' 같은 분류 메타가 답변 본문에 그대로 노출된다(#24)."""
    md = html_to_markdown(PROPERTY_PAGE)
    assert "메뉴명: 출결" in md
    assert "연번: 43" in md

    cleaned = clean_markdown(md)
    assert "메뉴명" not in cleaned
    assert "연번" not in cleaned
    # 본문은 살아남아야 한다.
    assert "출결이 보이지 않습니다" in cleaned


def test_title_becomes_h1():
    # chunk_markdown_file 이 헤딩으로 섹션을 나눈다. 헤딩이 없으면 청킹이 무너진다.
    assert html_to_markdown(PROPERTY_PAGE).lstrip().startswith("# 출결이 안 보입니다")


def test_list_and_linebreaks_survive():
    md = html_to_markdown(PROPERTY_PAGE)
    assert "- 조건 확인하기" in md
    assert "① 확인\n② 재확인" in md


def test_local_image_becomes_md_ref_with_encoded_path():
    """이미지 경로는 URL 인코딩된 원본 그대로여야 한다 —
    pipeline._rewrite_image_refs 가 unquote 해서 assets 매핑에 대조한다."""
    html = '<p><img src="%EC%88%98%EC%A0%95/Untitled.png"/></p>'
    md = html_to_markdown(html)
    assert extract_image_refs(md) == ["%EC%88%98%EC%A0%95/Untitled.png"]


def test_external_images_are_dropped():
    """Notion 속성 아이콘 같은 외부 URL 은 로컬 자산이 아니라 매핑에 없다.
    남기면 깨진 참조만 늘어난다."""
    md = html_to_markdown('<p><img src="https://app.notion.com/icons/x.svg"/>본문</p>')
    assert extract_image_refs(md) == []
    assert "본문" in md


def test_entities_are_unescaped_once():
    # 두 번 풀면 본문의 리터럴 '&amp;' 가 '&' 로 잘못 접힌다.
    assert "'공개'" in html_to_markdown("<p>&#x27;공개&#x27;</p>")
    assert "&" in html_to_markdown("<p>A &amp;amp; B</p>")


def test_script_and_style_content_dropped():
    md = html_to_markdown("<html><head><style>p{color:red}</style></head><body><p>본문</p></body></html>")
    assert "color" not in md
    assert "본문" in md


def test_convert_skips_existing_markdown(tmp_path):
    """진짜 Markdown export 가 함께 있으면 그쪽이 원본이다. 덮어쓰면 품질이 떨어진다."""
    (tmp_path / "a.html").write_text("<p>변환본</p>", encoding="utf-8")
    (tmp_path / "a.md").write_text("원본 md\n", encoding="utf-8")
    (tmp_path / "b.html").write_text("<p>새로 변환</p>", encoding="utf-8")

    made = convert_html_files(tmp_path)

    assert made == 1
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "원본 md\n"
    assert "새로 변환" in (tmp_path / "b.md").read_text(encoding="utf-8")


def test_convert_is_idempotent(tmp_path):
    (tmp_path / "a.html").write_text("<p>본문</p>", encoding="utf-8")
    assert convert_html_files(tmp_path) == 1
    assert convert_html_files(tmp_path) == 0
