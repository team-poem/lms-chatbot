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


def test_converts_polite_request_endings_to_declarative():
    """부탁·청유 종결('~해 주십시오' 등)을 평서형으로. 페르소나 규칙 2 안전망."""
    assert "주십시오" not in clean_response("삭제하지 않도록 유의해 주십시오.")
    assert "주세요" not in clean_response("출결 상황을 확인해 주세요.")
    assert "바랍니다" not in clean_response("내용을 참고하여 주시기 바랍니다.")
    # '~해 주십시오' -> '~합니다'
    assert "확인합니다" in clean_response("다음 사항을 확인해 주십시오.")
    # 보조용언형 '<동사>주십시오' -> '~주면 됩니다'
    out = clean_response("재변환 버튼을 눌러주시기 바랍니다.")
    assert "바랍니다" not in out


def test_removes_kyosunim_honorific_inline():
    """본문 중간의 '교수님' 호칭도 제거 (규칙 1). 첫 문장 운두언이 아닌 경우 포함."""
    out = clean_response("퀴즈 자동 제출 경우는 다음과 같습니다. 1. 교수님께서 시간을 제한한 경우입니다.")
    assert "교수님" not in out
    assert "시간을 제한한 경우" in out


def test_removes_bullet_markers_keeps_numbered():
    """글머리 기호('- ', '• ')는 제거, 숫자 리스트는 보존 (규칙 3)."""
    out = clean_response("설정 방법:\n- 안드로이드: 알림 켜기\n- 아이폰: 알림 켜기")
    assert "- 안드로이드" not in out
    assert "안드로이드: 알림 켜기" in out
    # 숫자 리스트는 유지
    assert clean_response("1. 첫째\n2. 둘째") == "1. 첫째\n2. 둘째"


def test_polite_normalization_does_not_corrupt_normal_text():
    """평서형 정상 문장은 변형하지 않는다 (오변환 방지)."""
    for s in [
        "마감일과 이용 종료일을 동일하게 설정합니다.",
        "값을 미리 주의해서 입력합니다.",
        "메뉴를 눌러 이동합니다.",
    ]:
        assert clean_response(s) == s
