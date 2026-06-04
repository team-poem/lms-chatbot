from __future__ import annotations

from generation.suggestions import (
    build_help_reply,
    build_topic_reply,
    match_topic,
    topic_for_fallback,
)


def test_topic_for_fallback_catches_broad_topic_questions():
    # 게이트가 거절할 포괄 질문이라도 범위 내 주제어가 있으면 토픽명을 돌려준다
    # (의도·구체 신호와 무관 — 막다른 거절 대신 주제 안내로 폴백시키기 위함).
    assert topic_for_fallback("강의 운영은 어떻게 하나요?") == "강의 운영"
    assert topic_for_fallback("강의 운영은 어떻게 하나여?") == "강의 운영"  # 오타·구어체
    assert topic_for_fallback("과제 점수가 안 보여요") == "과제·평가"


def test_topic_for_fallback_silent_when_out_of_scope():
    assert topic_for_fallback("오늘 점심 뭐 먹지?") is None
    assert topic_for_fallback("주식 추천해줘") is None
    assert topic_for_fallback("") is None


def test_topic_for_fallback_catches_login():
    # "로그인 안됨"은 임베딩 바닥(0.593<0.60)에 걸려 게이트가 거절하지만,
    # 로그인 토픽 폴백으로 실제 로그인 FAQ를 안내해야 한다(하드 거절 X).
    assert topic_for_fallback("로그인 안됨") == "로그인·접속"
    assert topic_for_fallback("접속이 안돼요") == "로그인·접속"
    reply = build_topic_reply("로그인·접속")
    assert "로그인" in reply


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


def test_topic_reply_scopes_to_topic():
    reply = build_topic_reply("강의 운영")
    assert "강의 운영" in reply
    assert "과목을 복사" in reply     # 강의 운영 예시 포함
    assert "출석" not in reply        # 다른 토픽 예시는 미포함
    assert "궁금" in reply            # 구체 질문 유도 문구


def test_topic_reply_unknown_falls_back_to_help():
    assert build_topic_reply("없는토픽") == build_help_reply()


def test_match_topic_fires_on_declaration():
    assert match_topic("강의 운영 관련해서 문의하고 싶어요") == "강의 운영"
    assert match_topic("과제 관련 질문 있어요") == "과제·평가"
    assert match_topic("출결 쪽 궁금한 게 있는데요") == "출결"


def test_match_topic_silent_on_concrete_questions():
    # 구체 질문/문제는 토픽 키워드가 있어도 게이트로(None) 보낸다.
    assert match_topic("출석했는데 결석으로 처리됐어요") is None
    assert match_topic("과제 점수가 학생에게 안 보여요") is None
    assert match_topic("지난 학기 과목을 복사하려면 어떻게 하나요?") is None


def test_match_topic_silent_without_intent():
    # 의도 표현 없이 토픽 단어만으로는 발화하지 않는다.
    assert match_topic("강의 운영") is None
    assert match_topic("퀴즈") is None
    assert match_topic("")  is None


def test_match_topic_silent_on_complaint_after_intent():
    # "X 관련 문의인데 <문제>": 진짜 버그 보고가 토픽 응답으로 가로채이면 안 된다(→ 게이트).
    assert match_topic("공지 관련 문의인데 알림이 안 와요") is None
    assert match_topic("성적 관련 문의인데 안 나와요") is None
    assert match_topic("과제 관련 문의인데 문제가 생겼어요") is None
    assert match_topic("출결 관련 문의인데 안 찍혔어요") is None


def test_match_topic_fires_despite_munje_eunhaeng_keyword():
    # '문제'를 _CONCRETE 에 넣지 않았으므로 '문제은행'(퀴즈·시험 키워드) 선언은 정상 발화.
    assert match_topic("문제은행 관련 문의드려요") == "퀴즈·시험"
