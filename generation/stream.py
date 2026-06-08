from __future__ import annotations
import json
import re
from typing import AsyncIterator

import httpx

from app_types import ChatEvent, Source
from generation.filters import clean_response, streaming_clean
from generation.guardrail import is_meta_question
from generation.persona import build_prompt
from generation.relevance import doc_answers_question
from index.vector_store import get_collection
from rag.state import RagState
from retrieval.search import hybrid_search


SCORE_THRESHOLD = 0.25
# 원시 임베딩 유사도 절대 바닥. 매뉴얼 밖 질문(다크모드·날씨 등)은 무관 문서가
# 정규화 점수론 높게 잡혀 환각을 유발한다. 실측 분리: 매뉴얼 내 질문 최저 ~0.55,
# 명백한 헛질문 ~0.50 이하 → 0.50. (과거 0.60은 실제 질문도 막아 폐기됨.)
ABS_EMBED_FLOOR = 0.50
# 강한 매칭 기준. 이 이상이면 검색이 확실히 맞춘 것이라 LLM 관련성 게이트를 건너뛰고
# 무조건 답한다 — gemma:4b 게이트가 정확히 매칭된 FAQ(임베딩 0.72+)조차 오판해 추천
# 질문을 막은 사례가 있었다. 실측: 진짜 FAQ ≥0.72, 헛질문 ≤0.57 → 0.65에서 분리.
# 게이트는 애매 구간(0.50~0.65, 예: '주차장' 0.57)에서만 작동시킨다.
ABS_EMBED_CONFIDENT = 0.65
RELEVANCE_FLOOR = 0.30
RELEVANCE_RATIO = 0.60
# 컨텍스트로 LLM에 넘기는 청크 수 상한. 1위(정답) 외에 의미적으로 유사하지만
# 다른 주제의 청크가 섞여 답변을 오염시키는 것을 막는다(#39). 1위는 항상 포함.
MAX_CONTEXT_CHUNKS = 5
# 폴백 답변(매뉴얼 밖) 식별 표지 — 게이트·생성 양쪽 폴백 문구에 공통으로 들어간다.
# 답변에 이 문구가 있으면 이미지·출처를 붙이지 않는다.
_FALLBACK_MARK = "확인되지 않는 질문입니다"

# CMS 직접 언급 신호. 자유 입력은 이 신호가 있을 때만 CMS 로 스코핑하고, 그 외엔
# LMS 로 하드 고정한다 — LMS 질문(대다수)에 CMS 문서가 섞이지 않게. 'CMS'/'Cloud
# Editor' 처럼 LMS 와 혼동될 일 없는 표현만 넣는다('콘텐츠'는 LMS 에서도 흔해 제외).
_CMS_TRIGGERS = ("cms", "cloud editor", "클라우드 에디터")


def _route_manual(query: str) -> str:
    """자유 입력 질문의 매뉴얼 스코프. 기본 LMS, CMS 직접 언급 시에만 CMS."""
    q = query.lower()
    return "CMS" if any(t in q for t in _CMS_TRIGGERS) else "LMS"


_FAQ_LABEL_RE = re.compile(r"\*{0,2}\s*답변\s*\*{0,2}\s*[:：]\s*")
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _faq_answer(text: str) -> str:
    """FAQ 문서 본문에서 '답변' 텍스트만 추출한다. FAQ 는 사람이 작성한 정답이라
    gemma 로 재생성하면 질문 되풀이·원인 누락 등 손실이 생겨, 원문을 그대로 쓴다.
    제목('# 질문') 줄·'답변 :' 라벨·이미지 마크다운(이미지는 별도 영역)을 제거한다."""
    body = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    body = _MD_IMG_RE.sub("", body)
    body = _FAQ_LABEL_RE.sub("", body, count=1)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _qna_fallback_msg(qna_contact: str = "") -> str:
    """매뉴얼(준비된 답변)에서 근거를 못 찾은 질문에 대한 안내. persona 규칙 5의
    문장과 동일하게 맞춘다(게이트·생성 양쪽 폴백이 같은 문구). 'e-Class QnA 게시판'
    문구는 프론트가 게시판 URL 하이퍼링크로 렌더하므로 여기엔 URL을 넣지 않는다."""
    contact = f"{qna_contact} 또는 " if qna_contact else ""
    return (
        "준비된 매뉴얼 답변에서 확인되지 않는 질문입니다. "
        f"{contact}e-Class QnA 게시판으로 문의 부탁드립니다."
    )


def _is_relevant(score: float, top_score: float) -> bool:
    """1위 대비 비율 + 절대 점수 둘 다 통과해야 진짜 연관."""
    return score >= RELEVANCE_FLOOR and score >= top_score * RELEVANCE_RATIO


def _doc_images(
    state: RagState, doc_title: str, fallback_items, limit: int = 5, *, manual: str = ""
) -> list[str]:
    """1순위 문서(doc_title)의 모든 섹션 이미지를 seq 순서로 모은다(중복 제거, 상한).
    컨텍스트 청크에만 의존할 때 생기는 누락을 막는다. 조회 실패/빈 결과면 컨텍스트
    청크(fallback_items)의 이미지로 대체한다. manual 지정 시 동명 문서가 다른
    매뉴얼에 있어도 섞이지 않게 함께 필터한다."""
    refs: list[str] = []
    try:
        if doc_title:
            where = {"doc_title": doc_title}
            if manual:
                where = {"$and": [{"doc_title": doc_title}, {"manual": manual}]}
            res = get_collection(state.chroma).get(
                where=where, include=["metadatas"]
            )
            metas = list(res.get("metadatas") or [])
            metas.sort(key=lambda m: int(m.get("seq", 0) or 0))
            for m in metas:
                for img in (m.get("image_refs") or "").split(","):
                    if img and img not in refs:
                        refs.append(img)
    except Exception:
        refs = []
    if not refs:
        for it in fallback_items:
            for img in it.chunk.image_refs:
                if img and img not in refs:
                    refs.append(img)
    return refs[:limit]


async def stream_response(
    state: RagState, query: str, *, manual: str | None = None
) -> AsyncIterator[ChatEvent]:
    if is_meta_question(query):
        # 챗봇 자체/범위 밖 질문도 매뉴얼 밖 질문과 동일하게 QnA 안내로 통일한다.
        msg = _qna_fallback_msg(state.qna_contact)
        yield ChatEvent(type="text", delta=msg)
        yield ChatEvent(type="text_final", text=msg)
        yield ChatEvent(type="done")
        return

    # 매뉴얼 스코프: 네비 클릭은 manual 을 명시(CMS 문서 → 'CMS'), 자유 입력은
    # 직접 언급 라우팅(기본 LMS). 검색이 매뉴얼 단위로 하드 격리된다.
    scope = manual if manual else _route_manual(query)
    retrieval = hybrid_search(state, query, manual=scope)
    top_score = retrieval.top_score
    # 매뉴얼에 근거가 없으면(절대 임베딩 유사도 바닥 미달 또는 정규화 점수 바닥 미달)
    # 답을 지어내지 않고 QnA 안내로 폴백한다.
    if retrieval.max_embed_sim < ABS_EMBED_FLOOR or top_score < SCORE_THRESHOLD:
        msg = _qna_fallback_msg(state.qna_contact)
        yield ChatEvent(type="text", delta=msg)
        yield ChatEvent(type="text_final", text=msg)
        yield ChatEvent(type="done", score=top_score)
        return

    # 컨텍스트: 점수 1위 + 1위 대비 충분히 가까운 형제. 임베딩(BGE-M3)이 강해 점수
    # 1위가 대체로 정답이다. (gemma:4b 재랭킹은 정답 문서를 오히려 버리는 등 신뢰도가
    # 낮아 제거 — 선별은 점수에 맡기고, gemma 는 생성만 한다.)
    items = retrieval.items
    relevant = (items[0],) + tuple(
        it for it in items[1:] if _is_relevant(it.score, top_score)
    )

    # 단일 문서 답변(1 질문 : 1 매뉴얼 문서): 1위 청크가 속한 문서의 청크만 남긴다.
    # 한 질문은 한 문서가 답하게 해서 곁가지 다른 문서가 출처·이미지로 섞이는 것을
    # 막는다(예: '응시 이력 조회'에 '퀴즈 통계 조회하기'가 딸려오는 것 차단). 같은
    # 문서의 여러 섹션(출결현황 조회의 하위 섹션 등)은 함께 유지돼 답이 완결된다.
    primary_doc = relevant[0].chunk.doc_title or relevant[0].chunk.source
    relevant = tuple(
        it for it in relevant
        if (it.chunk.doc_title or it.chunk.source) == primary_doc
    )
    relevant = relevant[:MAX_CONTEXT_CHUNKS]

    # 관련성 게이트: 점수 1위가 정규화상 높아도 매뉴얼 밖 질문일 수 있다(예: '주차장'이
    # '과목 복사' 문서에 0.57로 매칭). 임베딩 바닥으론 못 거른다. 단 강한 매칭
    # (임베딩 ≥ ABS_EMBED_CONFIDENT)은 검색이 확실히 맞춘 것이라 게이트를 건너뛴다 —
    # 애매 구간에서만 1위 문서가 실제로 답하는지 gemma 이진 판정을 받아 '아니오'면
    # 폴백한다. (LLM 오류 시 None → 통과: 답을 막지 않는다.)
    primary = relevant[0].chunk
    if retrieval.max_embed_sim < ABS_EMBED_CONFIDENT and await doc_answers_question(
        state.ollama_host, state.ollama_model, query, primary.title, primary.text
    ) is False:
        msg = _qna_fallback_msg(state.qna_contact)
        yield ChatEvent(type="text", delta=msg)
        yield ChatEvent(type="text_final", text=msg)
        yield ChatEvent(type="done", score=top_score)
        return

    # FAQ 직출력: 추천 질문 등 FAQ 문서는 사람이 쓴 정답을 그대로 내보낸다(gemma
    # 우회). gemma:4b 가 짧은 FAQ 정답을 질문 되풀이·원인 누락으로 망가뜨리던 문제를
    # 차단한다. 가이드 문서는 길어 종전대로 gemma 가 생성한다.
    if primary.doc_set == "faq":
        answer = _faq_answer(primary.text)
        yield ChatEvent(type="text", delta=answer)
        yield ChatEvent(type="text_final", text=answer)
        imgs = _doc_images(state, primary.doc_title, relevant, manual=primary.manual)
        sources: tuple[Source, ...] = ()
        if primary.doc_title and not primary.doc_title.startswith("FAQ —"):
            sources = (Source(title=primary.doc_title, url=primary.notion_url or ""),)
        yield ChatEvent(
            type="done", images=tuple(imgs), sources=sources, score=top_score
        )
        return

    messages = build_prompt(
        query,
        [{"title": it.chunk.title, "text": it.chunk.text} for it in relevant],
    )
    url = f"{state.ollama_host}/api/chat"
    payload = {
        "model": state.ollama_model,
        "messages": messages,
        "stream": True,
        "options": {"num_ctx": 8192, "temperature": 0.2},
    }

    raw_buf = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
        async with client.stream("POST", url, json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                delta = obj.get("message", {}).get("content", "")
                if delta:
                    raw_buf += delta
                    yield ChatEvent(type="text", delta=streaming_clean(delta))
                if obj.get("done"):
                    break

    answer = clean_response(raw_buf)
    yield ChatEvent(type="text_final", text=answer)

    # gemma 가 (관련성 게이트를 통과한 문서로도) 답을 못 찾아 폴백 문구를 생성한 경우:
    # 엉뚱한 문서의 이미지·출처를 붙이지 않는다.
    if _FALLBACK_MARK in answer:
        yield ChatEvent(type="done", score=top_score)
        return

    # 이미지 (상위 5장): 1순위 문서의 '모든 섹션'에서 seq 순으로 모은다. 컨텍스트에
    # 든 청크에만 의존하면 이미지가 검색 top-k 밖 섹션에 있을 때 누락된다(예: 성적
    # 메뉴). 단일 문서 기준이라 다른 문서 이미지 누수는 없다.
    seen_imgs = _doc_images(state, primary.doc_title, relevant, manual=primary.manual)

    # 출처: 1 질문 : 1 매뉴얼 문서 — 답에 쓴 문서를 한 건만 노출한다(섹션 단위가 아닌
    # 문서 단위 제목·링크). 'FAQ —'(답변 없는 CSV) 접두는 출처로 쓰지 않는다.
    sources: tuple[Source, ...] = ()
    if primary.doc_title and not primary.doc_title.startswith("FAQ —"):
        sources = (Source(title=primary.doc_title, url=primary.notion_url or ""),)

    yield ChatEvent(
        type="done",
        images=tuple(seen_imgs),
        sources=sources,
        score=top_score,
    )
