from ingest.preprocess import clean_markdown, strip_emoji


def test_strip_emoji_removes_decoration():
    assert strip_emoji("🟠 글로벌 탐색 메뉴") == " 글로벌 탐색 메뉴"
    assert strip_emoji("퀴즈 개요 (📄)") == "퀴즈 개요 ()"


def test_strip_emoji_keeps_ascii():
    assert strip_emoji("LMS FAQ") == "LMS FAQ"


def test_clean_markdown_removes_callout_wrappers():
    src = "<aside>\n💡 화면 오른쪽 위에 위치한 검색 버튼\n</aside>"
    out = clean_markdown(src)
    assert "<aside>" not in out
    assert "</aside>" not in out
    assert "검색 버튼" in out
    assert "💡" not in out


def test_clean_markdown_strips_inline_emoji_marker_in_heading():
    src = "## 🔖 시험 및 설문"
    out = clean_markdown(src)
    assert out.strip().startswith("## ")
    assert "🔖" not in out


def test_clean_markdown_preserves_image_links():
    src = "본문\n\n![캡션](images/abc.png)\n\n다음 단락"
    out = clean_markdown(src)
    assert "![캡션](images/abc.png)" in out


def test_clean_markdown_strips_external_links_keeps_text():
    src = "참고는 [퀴즈 개요](https://www.notion.so/abc) 페이지."
    out = clean_markdown(src)
    assert "퀴즈 개요" in out
    assert "https://" not in out


def test_clean_markdown_drops_lone_hr_lines():
    src = "본문 1\n\n---\n\n본문 2"
    out = clean_markdown(src)
    assert "---" not in out
    assert "본문 1" in out
    assert "본문 2" in out


def test_clean_markdown_collapses_blank_lines():
    src = "줄1\n\n\n\n\n줄2"
    out = clean_markdown(src)
    assert "\n\n\n" not in out
