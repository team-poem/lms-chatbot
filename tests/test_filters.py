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


def test_strips_kyosunim_preamble():
    out = clean_response("교수님, 문의하신 내용은 잘 이해했습니다. 퀴즈는 다음과 같이 출제합니다.")
    assert "교수님" not in out
    assert "이해했습니다" not in out
    assert out.startswith("퀴즈는")


def test_strips_apology_preamble():
    out = clean_response("로그인 문제로 불편하시더라도, 우선 안내해 드립니다. 다음 절차를 진행하십시오.")
    assert "불편" not in out
    assert "안내" not in out.split("\n")[0][:20]
    assert "다음 절차" in out


def test_strips_multiple_preambles_in_sequence():
    out = clean_response("안녕하세요. 교수님, 다음과 같이 안내드립니다. 본 절차로 진행하시면 됩니다.")
    assert "안녕" not in out
    assert "교수님" not in out
    assert out.startswith("본 절차")


def test_keeps_substantive_response():
    text = "공지사항 작성은 공지 메뉴에서 가능합니다. 1. 공지 메뉴 진입 2. 작성 클릭"
    assert clean_response(text) == text
