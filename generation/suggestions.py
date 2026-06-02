"""역량/가이드 문의·범위 내 주제 선언에 대한 안내 응답.

retrieval 게이트 *이전*의 결정적 사전 분기에서 사용한다. 토픽 택소노미를 단일
출처(_TOPICS)로 두고, 전체 도움말(build_help_reply)과 주제별 안내(build_topic_reply)를
같은 데이터에서 렌더한다. FAQ 가 바뀌면 이 파일의 _TOPICS 만 고치면 된다.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    emoji: str
    name: str
    keywords: tuple[str, ...]   # match_topic(주제 선언) 감지용
    examples: tuple[str, ...]   # 사용자에게 보여줄 예시 질문


_TOPICS: tuple[Topic, ...] = (
    Topic("📚", "강의 운영",
          ("강의 운영", "강의운영", "주차학습", "과목 복사", "과목복사", "수업계획서", "콘텐츠"),
          ("지난 학기 과목을 복사하려면 어떻게 하나요?", "주차학습에 강의를 어떻게 등록하나요?")),
    Topic("📝", "과제·평가",
          ("과제",),
          ("과제 점수가 학생에게 안 보여요", "과제 일괄 다운로드가 안 돼요")),
    Topic("🧪", "퀴즈·시험",
          ("퀴즈", "시험", "문제은행", "응시"),
          ("퀴즈가 자동으로 제출됐어요", "시험 후 특정 학생에게 재응시를 줄 수 있나요?")),
    Topic("✅", "출결",
          ("출석", "출결", "전자출결"),
          ("출석했는데 결석으로 처리됐어요", "전자출결은 어떻게 하나요?")),
    Topic("🏅", "성적",
          ("성적", "채점", "평가", "점수"),
          ("재채점 옵션이 보이지 않아요", "대면시험 점수를 LMS로 알려줄 수 있나요?")),
    Topic("👥", "수강생·알림",
          ("수강생", "수강신청", "알림", "공지"),
          ("수강신청했는데 과목에 학생이 없어요", "앱 푸시 알림이 안 와요")),
)


def _render_topic(t: Topic) -> str:
    lines = [f"{t.emoji} {t.name}"]
    lines += [f'  · "{ex}"' for ex in t.examples]
    return "\n".join(lines)


def build_help_reply() -> str:
    """역량/가이드 문의 응답: 전체 카테고리 + 예시 리스트업."""
    body = "\n".join(_render_topic(t) for t in _TOPICS)
    return (
        "안녕하세요! 아래 주제로 도와드릴 수 있어요. 예시처럼 편하게 질문해 주세요:\n\n"
        f"{body}\n\n"
        "원하는 주제나 비슷한 질문을 입력해 주세요."
    )
