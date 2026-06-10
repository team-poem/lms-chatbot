from ingest.preprocess import clean_markdown, strip_emoji, strip_empty_parens


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


def test_clean_markdown_strips_faq_metaheader():
    """FAQ DATABASE md의 메뉴명/시기/연번/태그 메타헤더 4행은 제거하고,
    제목(# ...)과 답변 본문은 보존한다 (#24 메타데이터 누출 수정)."""
    src = (
        "# 앱 푸시 알림이 너무 많이 오는데 어떻게 해야 하나요?\n\n"
        "메뉴명: 모바일 앱\n시기: 2.학기중\n연번: 1\n태그: 알림\n\n"
        " **답변** : 알림은 [계정] - [알림] 메뉴에서 수신 여부를 설정할 수 있습니다."
    )
    out = clean_markdown(src)
    for label in ("메뉴명:", "시기:", "연번:", "태그:"):
        assert label not in out, f"{label} 메타헤더가 제거되지 않음"
    assert "# 앱 푸시 알림이 너무 많이 오는데 어떻게 해야 하나요?" in out
    assert "[계정] - [알림] 메뉴" in out


def test_clean_markdown_keeps_colon_lines_in_body():
    """메타헤더 4종 라벨이 아닌 본문의 '단어: 값' 줄은 보존한다
    (과도하게 넓은 '^\\w+:' 삭제 방지)."""
    src = "# 제목\n\n예: 학기초에 진행합니다\nURL: https 안내\n참고: 추가 설명"
    out = clean_markdown(src)
    assert "예: 학기초에 진행합니다" in out
    assert "참고: 추가 설명" in out


def test_clean_markdown_metaheader_idempotent_for_guides():
    """메타헤더가 없는 일반 가이드 md는 메타헤더 제거 로직에 영향받지 않는다."""
    src = "# 퀴즈 출제\n\n1. 시험 메뉴로 이동합니다.\n2. 문제를 추가합니다."
    out = clean_markdown(src)
    assert "퀴즈 출제" in out
    assert "시험 메뉴로 이동합니다" in out
    assert "문제를 추가합니다" in out


def test_clean_markdown_drops_empty_text_links():
    """빈 텍스트 링크 '[](url)'는 표시 텍스트가 없으므로 통째로 제거한다.
    (Notion이 첨부 이미지를 [](media-cdn...) 형태로 내보내 본문에 URL이 남는 문제)"""
    src = "원인 설명\n\n[](https://media-cdn.atlassian.com/file/abc/image/cdn?x=1)\n\n조치 방법"
    out = clean_markdown(src)
    assert "media-cdn" not in out
    assert "https://" not in out
    assert "원인 설명" in out
    assert "조치 방법" in out


def test_clean_markdown_keeps_real_image_links():
    """실제 이미지 마크다운 '![](path)'는 빈 텍스트 링크 제거에 영향받지 않는다."""
    src = "본문\n\n![](/assets/screen.png)\n\n다음"
    out = clean_markdown(src)
    assert "![](/assets/screen.png)" in out


def test_strip_empty_parens_removes_and_pads():
    # (📄) 장식이 이모지 제거 후 남긴 빈 괄호 — 공백 하나로 치환된다
    assert strip_empty_parens("제목 ( ) 끝") == "제목 끝"
    assert strip_empty_parens("제목()") == "제목 "
    assert strip_empty_parens("그대로") == "그대로"
    # 내용 있는 괄호는 보존 — 실제 제목의 괄호를 건드리면 안 된다
    assert strip_empty_parens("출결 상태 수동 변경(학습 인정 처리)") == "출결 상태 수동 변경(학습 인정 처리)"
