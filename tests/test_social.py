from __future__ import annotations

from generation.guardrail import is_meta_question, is_social_chitchat


def test_detects_greetings():
    assert is_social_chitchat("안녕하세여")
    assert is_social_chitchat("ㅎㅇ")
    assert is_social_chitchat("안녕하세요")
    assert is_social_chitchat("하이")


def test_detects_thanks_and_farewell():
    assert is_social_chitchat("고마워요 도움이 됐어요!")
    assert is_social_chitchat("감사합니다")
    assert is_social_chitchat("수고하세요~")


def test_detects_capability_questions():
    assert is_social_chitchat("뭐 할 수 있어?")
    assert is_social_chitchat("무엇을 도와줄 수 있나요?")
    assert is_social_chitchat("어떤 기능이 있나요")


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
