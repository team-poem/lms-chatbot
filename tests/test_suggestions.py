from __future__ import annotations

from generation.suggestions import build_help_reply


def test_help_reply_lists_all_categories():
    reply = build_help_reply()
    for name in ("강의 운영", "과제·평가", "퀴즈·시험", "출결", "성적", "수강생·알림"):
        assert name in reply


def test_help_reply_contains_example_questions_in_quotes():
    reply = build_help_reply()
    assert '"과제 점수가 학생에게 안 보여요"' in reply
    assert '"퀴즈가 자동으로 제출됐어요"' in reply


def test_help_reply_has_invitation_footer():
    reply = build_help_reply()
    assert "원하는 주제나 비슷한 질문을 입력해 주세요" in reply
