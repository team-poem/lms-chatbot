from __future__ import annotations

from generation.guardrail import is_help_request, is_meta_question, is_social_chitchat


def test_detects_greetings():
    assert is_social_chitchat("안녕하세여")
    assert is_social_chitchat("ㅎㅇ")
    assert is_social_chitchat("안녕하세요")
    assert is_social_chitchat("하이")


def test_detects_thanks_and_farewell():
    assert is_social_chitchat("고마워요 도움이 됐어요!")
    assert is_social_chitchat("감사합니다")
    assert is_social_chitchat("수고하세요~")


def test_capability_questions_route_to_help_not_social():
    # 역량 문의는 이제 social(짧은 인사)이 아니라 help(리치 리스트업)로 간다.
    for q in ("뭐 할 수 있어?", "무엇을 도와줄 수 있나요?", "어떤 기능이 있나요"):
        assert is_help_request(q)
        assert not is_social_chitchat(q)


def test_help_request_detects_guide_inquiries():
    # 2026-06-02 제보 트랜스크립트의 거절된 입력들
    assert is_help_request("어떤걸 가이드 받을수잇죠?")
    assert is_help_request("아니 그래도 가이드 받을껄 보고싶은데여")
    assert is_help_request("어떤걸 도와주실수 있는데여?")


def test_help_request_ignores_real_questions_and_topic_declarations():
    assert not is_help_request("과제 제출은 어떻게 하나요?")
    assert not is_help_request("출석했는데 결석으로 처리됐어요")
    # 주제 선언은 help 가 아니라 topic 경로로 가야 한다.
    assert not is_help_request("강의 운영 관련 문의하고 싶어요")


def test_does_not_catch_real_questions_with_a_greeting_prefix():
    # 인사 + 실제 질문이 섞이면 일반 답변 경로로 가야 한다(소셜로 가로채지 않음).
    assert not is_social_chitchat("안녕하세요 과제 제출은 어떻게 하나요?")
    assert not is_social_chitchat("퀴즈 출제 방법 알려주세요")
    assert not is_social_chitchat("출석 어떻게 관리하나요")
    assert not is_social_chitchat("성적표 다운로드 방법 정말 감사한데 어디서 하나요")


def test_social_and_meta_are_disjoint_for_model_questions():
    # 모델/시스템 질문은 소셜이 아니라 메타(거절) 경로.
    assert not is_social_chitchat("어떤 모델을 사용하나요?")
    assert is_meta_question("어떤 모델을 사용하나요?")


def test_help_request_ignores_domain_noun_questions():
    # '안내/도움말'이 도메인 명사로 쓰인 진짜 질문은 help 가 아님(→ RAG/게이트).
    assert not is_help_request("강의 안내 자료가 안 보여요")
    assert not is_help_request("성적 안내문 양식 알려주세요")
    assert not is_help_request("과제 안내 사항 다시 보고 싶어요")
    assert not is_help_request("도움말 탭이 어디 있어요?")
    assert not is_help_request("공지 안내문은 어디서 보여요?")


def test_help_request_detects_more_capability_phrasings():
    assert is_help_request("도움받을 수 있는 주제가 뭐가 있나요?")
    assert is_help_request("어떤 걸 안내받을 수 있나요?")
