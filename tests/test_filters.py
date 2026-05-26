from generation.filters import clean_response


def test_strips_emoji_from_response():
    assert clean_response("좋습니다 🙂 다음과 같습니다.") == "좋습니다  다음과 같습니다."


def test_removes_bold_markup():
    assert "**" not in clean_response("**중요**: 다음 절차입니다")


def test_removes_italic_markup():
    out = clean_response("*강조* 부분")
    assert "*" not in out
    assert "강조" in out


def test_removes_headings():
    out = clean_response("# 제목\n본문")
    assert not out.startswith("#")
    assert "본문" in out


def test_keeps_numbered_lists():
    text = "1. 첫째\n2. 둘째"
    assert clean_response(text) == text
