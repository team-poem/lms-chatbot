from generation.relevance import build_prompt, parse_verdict


def test_parse_verdict_yes():
    assert parse_verdict("예") is True
    assert parse_verdict("예.") is True


def test_parse_verdict_no():
    assert parse_verdict("아니오") is False
    assert parse_verdict("아니오, 관련 없습니다") is False


def test_parse_verdict_ambiguous_is_none():
    assert parse_verdict("잘 모르겠습니다") is None
    assert parse_verdict("") is None


def test_build_prompt_includes_query_title_and_snippet():
    p = build_prompt("주차장 어디?", "과목 복사", "지난 학기 과목을 복사하는 방법입니다.")
    assert "주차장 어디?" in p
    assert "과목 복사" in p
    assert "예" in p and "아니오" in p  # 응답 형식 지시 포함
