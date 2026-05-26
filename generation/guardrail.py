"""챗봇 자체에 대한 메타 질문 및 프롬프트 인젝션 시도를 사전에 차단.

retrieval 호출 전에 입력 질의를 검사. 명백한 메타 질문이면 정형 응답을 반환하고
LLM 까지 가지 않도록 한다 (LLM 이 시스템 프롬프트를 어기더라도 안전).
"""
from __future__ import annotations
import re


META_REPLY = "본 챗봇은 LMS 사용법 안내만 제공합니다. 다른 질문은 응답드리지 않습니다."


# 페르소나·시스템·모델 정보를 캐내려는 시도
_META_PATTERNS = [
    # 시스템/프롬프트 노출 시도
    r"(?:system\s*prompt|시스템\s*프롬프트|프롬프트.*?(?:보여|알려|출력|공개|뭐|무엇))",
    r"(?:ignore|disregard|forget).*(?:previous|prior|above|이전|위의)\s*(?:instruction|prompt|rule)",
    # 챗봇/AI 정체에 대한 질문
    r"(?:너|당신|챗봇|봇|에이전트|AI).{0,10}(?:정체|소개|뭐(?:야|냐|니|예요|입니까)|누구|누가|어떻게\s*만들|어떤\s*(?:모델|기술|LLM|AI|인공지능))",
    r"(?:너|당신|챗봇|봇).{0,10}(?:누가\s*만들|개발|제작)",
    # 사용 모델·기술 묻기
    r"(?:어떤|무슨|어느|뭐|뭣|어떠한|뭘|어떤걸).{0,6}(?:모델|LLM|언어\s*모델|AI|인공지능|기술|엔진).{0,15}(?:사용|쓰|기반|돌아가|운영)?",
    r"(?:어떤|무슨|뭐|뭣).{0,4}(?:모델|LLM|AI)\s*(?:이|예요|입니까|이야|이니|이세요|이세요?)",
    r"(?:gemma|gpt|claude|llama|qwen|ollama|RAG|벡터|임베딩|chroma)",
    r"(?:학습\s*데이터|훈련\s*데이터|training\s*data)",
    r"(?:내부|동작|구조|원리|알고리즘|아키텍처).{0,10}(?:공개|알려|설명|보여|어떻게|뭐|무엇)",
    # jailbreak 시도
    r"(?:roleplay|역할\s*놀이|pretend|척\s*해|척\s*하)",
    r"(?:jailbreak|탈옥|DAN|do\s*anything)",
]
_META_RES = [re.compile(p, flags=re.IGNORECASE) for p in _META_PATTERNS]


def is_meta_question(query: str) -> bool:
    q = query.strip()
    if not q:
        return False
    for r in _META_RES:
        if r.search(q):
            return True
    return False
