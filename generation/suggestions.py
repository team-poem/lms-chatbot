"""역량/가이드 문의·범위 내 주제 선언에 대한 안내 응답.

retrieval 게이트 *이전*의 결정적 사전 분기에서 사용한다. 토픽 택소노미를 단일
출처(_TOPICS)로 두고, 전체 도움말(build_help_reply)과 주제별 안내(build_topic_reply)를
같은 데이터에서 렌더한다. FAQ 가 바뀌면 이 파일의 _TOPICS 만 고치면 된다.
"""
from __future__ import annotations
import re
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


def build_topic_reply(topic_name: str) -> str:
    """범위 내 주제 선언 응답: 해당 주제 예시 + 구체 질문 유도."""
    t = next((t for t in _TOPICS if t.name == topic_name), None)
    if t is None:                      # 방어적: 알 수 없는 토픽이면 전체 도움말로 폴백
        return build_help_reply()
    examples = "\n".join(f'  · "{ex}"' for ex in t.examples)
    return (
        f"{t.emoji} {t.name} 관련해서 이런 점들을 도와드릴 수 있어요:\n\n"
        f"{examples}\n\n"
        "구체적으로 어떤 점이 궁금하신가요? 위 예시처럼 질문해 주세요."
    )


# 주제 선언 감지: 토픽 키워드 + 의도 표현이 있고, 구체 질문 신호가 없을 때만 발화.
_INTENT_RE = re.compile(r"문의|질문|여쭤|물어보|관련(?:해서|해|이)?|대해|궁금")
# 구체 질문/문제 신호가 있으면 '선언'이 아니라 '진짜 질문' → 게이트로 보낸다.
# '인데'(문의인데 <문제>)와 '안 <동사>' 부정형을 포함해 버그 보고가 토픽으로 가로채이지 않게 한다.
_CONCRETE_RE = re.compile(
    r"어떻게|어떡|방법|하나요|할까요|되나요|있나요|입니까|어디|언제|왜|얼마|몇|"
    r"가능한가|안\s*돼|안\s*되|안\s*보|안\s+[가-힣]|인데|오류|에러|실패|처리|떴|뜨는|뜨면"
)


def match_topic(query: str) -> str | None:
    """범위 내 주제 선언이면 토픽명을 반환, 아니면 None (보수적 발화)."""
    q = query.strip()
    if not q or _CONCRETE_RE.search(q):
        return None
    if not _INTENT_RE.search(q):
        return None
    for t in _TOPICS:
        if any(kw in q for kw in t.keywords):
            return t.name
    return None
