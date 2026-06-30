"""관련성 게이트. 점수 1위 문서가 정규화 점수상 높아도 매뉴얼 밖 질문일 수 있다
(예: '주차장 어디'가 '과목 복사' 문서에 임베딩 0.57로 매칭 → 환각 '1층'). 임베딩
바닥으론 못 거른다(실제 질문보다 높게 나오기도 함). 대신 gemma 에게 "이 문서가
질문에 답하나?"를 이진으로 묻는다 — 5개 중 고르기(재랭킹)는 4b 가 못했지만, 단일
문서 예/아니오 판정은 신뢰도가 높다(실측 분리 양호)."""
from __future__ import annotations

from generation import ollama
from tuning import RELEVANCE_OPTIONS, RELEVANCE_TIMEOUT_S

_PROMPT = (
    "질문: {q}\n\n문서 제목: {title}\n문서 내용: {text}\n\n"
    "이 문서가 위 질문에 대한 답을 담고 있습니까? '예' 또는 '아니오' 한 단어로만 답하십시오."
)


def build_prompt(query: str, title: str, text: str) -> str:
    return _PROMPT.format(q=query, title=title, text=text[:400])


def parse_verdict(reply: str) -> bool | None:
    """'아니오' → False, '예' → True, 그 외 → None(모호 — 호출부가 통과시킴)."""
    r = reply.strip()
    if "아니오" in r:
        return False
    if "예" in r:
        return True
    return None


async def doc_answers_question(
    host: str, model: str, query: str, title: str, text: str, *,
    timeout: float = RELEVANCE_TIMEOUT_S,
) -> bool | None:
    """1위 문서가 질문에 답하는가. LLM 호출/파싱 실패 시 None(통과 — 답을 막지 않음)."""
    messages = [{"role": "user", "content": build_prompt(query, title, text)}]
    try:
        reply = await ollama.chat(
            host, model, messages, options=RELEVANCE_OPTIONS, timeout=timeout
        )
    except Exception:
        return None
    return parse_verdict(reply)
