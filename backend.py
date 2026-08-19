from __future__ import annotations
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app_types import ChatEvent, Source
from config import load_config
from db import store
from generation.catalog import build_catalog
from generation.faq import sample_for_entry, sample_questions
from generation.nodes import build_registry, card_of, entry_payload, find_related
from generation.stream import stream_response
from rag.state import RagState, load_rag_state
from ratelimit import Limits, RateLimiter, client_ip
from retrieval.search import hybrid_search


# 라이브 배포본(2026-07-16)과 맞춘다 — 프론트가 이 값을 localStorage 에 저장해
# 동의 여부를 판단하므로, 낮추면 이미 동의한 사용자가 모달을 다시 보게 된다.
# v2 = Gemini API 처리위탁·국외이전 고지 반영본(static/privacy.html 5항).
CONSENT_VERSION = "2026-07-16-v2"

config = load_config()

# /chat 은 호출마다 Gemini 과금이고 /consent 는 인증 없이 세션을 발급한다.
# 공개 배포에서 이 상한이 유일한 비용 방어선이다(설계 근거는 ratelimit.py).
limiter = RateLimiter(
    Limits(
        chat_per_session=config.rl_chat_per_session,
        consent_per_ip_hour=config.rl_consent_per_ip_hour,
        chat_per_day=config.rl_chat_per_day,
    )
)


def _too_many(decision) -> HTTPException:
    headers = {"Retry-After": str(decision.retry_after)} if decision.retry_after else None
    return HTTPException(status_code=429, detail=decision.reason, headers=headers)


def _serialize_sse(evt: ChatEvent | dict) -> str:
    """ChatEvent | dict → SSE 라인. asdict 가 중첩 dataclass·tuple 을 재귀
    변환하고 json.dumps 가 tuple 을 배열로 직렬화한다 (tests/test_sse.py 로 고정)."""
    payload = asdict(evt) if is_dataclass(evt) else evt
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_schema(config.logs_db_path)
    print("[startup] RagState 사전 로드 시작 (BGE-M3, 약 10~20초)...", flush=True)
    t0 = time.time()
    app.state.rag = await asyncio.to_thread(load_rag_state, config)
    print(f"[startup] RagState 준비 완료 ({time.time() - t0:.1f}s)", flush=True)
    app.state.nodes = await asyncio.to_thread(
        build_registry, app.state.rag, overlay_path=config.nodes_overlay_path
    )
    print(f"[startup] 노드 레지스트리 {len(app.state.nodes.by_id)}개", flush=True)
    yield


app = FastAPI(title="LMS 챗봇", lifespan=lifespan)


# 프론트엔드 자산 캐시 — 두 겹으로 막는다.
#
# **문제.** StaticFiles 와 FileResponse 는 ETag·Last-Modified 만 붙이고 Cache-Control 을
# 붙이지 않는다. Cache-Control 이 없으면 브라우저는 휴리스틱 캐싱을 한다 —
# Last-Modified 로부터 지난 시간의 10% 정도를 임의로 신선하다고 보고 서버에 묻지도
# 않는다. 그래서 배포를 해도 이미 방문한 사용자는 옛 자산을 계속 쓴다.
#
# 단순히 '옛 화면이 보인다'로 끝나지 않는다. HTML 은 갱신됐는데 JS 만 캐시에서 오면
# **페이지가 통째로 죽는다** — 2026-08-19 실측: 옛 main.js 가 새 HTML 에 없는 `#agree`
# 에 addEventListener 를 걸다 TypeError 로 모듈이 중단됐고, 추천 질문·세션 발급·입력창
# 활성화가 전부 실행되지 않았다.
#
# **1겹: 경로에 빌드 해시.** index.html 이 `/static/<sha>/js/main.js` 를 참조하면 배포
# 마다 URL 이 달라져 캐시가 원천적으로 안 맞는다. `?v=` 쿼리로는 부족하다 — main.js 가
# `./ui.js` 를 상대경로로 import 하는데 거기엔 쿼리가 안 붙어 옛 ui.js 가 그대로 온다.
# 경로 접두라야 상대 import 까지 같은 버전으로 따라온다.
#
# **2겹: no-cache.** index.html 자신은 버전을 붙일 곳이 없으므로 매번 재검증한다.
# 내용이 같으면 304(본문 0B)라 비용은 조건부 요청 한 번이다.
#
# /assets(매뉴얼 이미지)는 제외한다 — 수가 많고 거의 바뀌지 않아 캐시가 이득이다.
BUILD_SHA = os.environ.get("BUILD_SHA", "dev")
STATIC_PREFIX = f"/static/{BUILD_SHA[:12]}"


@app.middleware("http")
async def revalidate_html(request: Request, call_next):
    resp = await call_next(request)
    if request.url.path in ("/", "/privacy"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# 버전 경로를 먼저 등록한다(Starlette 는 등록 순서로 매칭한다). 버전 없는 /static 은
# 캐시에 남은 옛 HTML 이 찾아올 수 있으므로 함께 남겨 둔다.
app.mount(STATIC_PREFIX, StaticFiles(directory="static"), name="static_versioned")
app.mount("/static", StaticFiles(directory="static"), name="static")
if config.assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(config.assets_dir)), name="assets")


@app.get("/")
def index():
    """index.html 의 자산 경로에 빌드 해시를 끼워 넣어 내보낸다.

    매 요청 파일을 읽는다 — 홈 요청 자체는 드물고(무거운 자산은 캐시된다),
    개발 중 --reload 로 고친 내용이 바로 반영되는 편이 낫다."""
    html = Path("static/index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace('"/static/', f'"{STATIC_PREFIX}/'))


@app.get("/privacy")
def privacy_page():
    return FileResponse("static/privacy.html")


@app.get("/health")
def health():
    # qna_board_url 은 프론트가 폴백 답변의 'e-Class QnA 게시판' 문구를 하이퍼링크로
    # 걸 때 쓴다(로드 시 1회 조회).
    return {
        "ok": True,
        # 배포된 것이 어느 커밋인지 밖에서 바로 확인할 수 있게 한다.
        # 2026-08-12: 라이브 코드가 레포의 어느 브랜치와도 일치하지 않는 것을
        # 발견했는데, 이 값이 없어서 공개 엔드포인트를 하나씩 찔러 계보를 추정해야
        # 했다(/entry 404 → PR#15 이전). 빌드 시 주입되며 없으면 "unknown".
        "build": os.environ.get("BUILD_SHA", "unknown"),
        "consent_version": CONSENT_VERSION,
        "qna_board_url": config.qna_board_url,
    }


@app.get("/faq")
def faq(n: int | None = Query(None, ge=1, le=12)):
    """첫 진입 화면에 노출할 FAQ 질문을 랜덤으로 반환한다. n 미지정 시 5~7개."""
    questions = sample_questions(n) if n is not None else sample_for_entry()
    return {"questions": questions}


@app.get("/catalog")
def catalog():
    """가이드 네비게이션 트리. 매뉴얼별 대분류 → 하위 문서(2·3뎁스). 노션 매뉴얼
    목차에서 파싱한다. CMS 문서를 누를 때 manual='CMS' 스코프로 질문을 보내야
    LMS 검색에 섞이지 않으므로, manual 키도 함께 내려준다."""
    return {
        "manuals": [
            {
                "name": m.name,
                "title": m.title,
                "categories": [
                    {"name": c.name, "docs": list(c.docs)} for c in m.categories
                ],
            }
            for m in build_catalog()
        ]
    }


@app.get("/entry")
def entry(request: Request):
    """첫 화면: 환영 + 카테고리 + 추천 FAQ + 빠른 링크. 공개(세션 불필요)."""
    reg = getattr(request.app.state, "nodes", None)
    if reg is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    return entry_payload(reg, build_catalog())


@app.get("/answer/{node_id}")
def answer(node_id: str, request: Request):
    """노드의 확정 답변 카드. 재검색·게이트·LLM 없음. 미존재 404."""
    reg = getattr(request.app.state, "nodes", None)
    if reg is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    node = reg.by_id.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="없는 항목입니다")
    return asdict(card_of(node))


@app.get("/search")
def search(request: Request, q: str = Query(..., min_length=1)):
    """자유 입력 → 가장 가까운 노드 추천(생성 없음). 공개."""
    reg = getattr(request.app.state, "nodes", None)
    state = getattr(request.app.state, "rag", None)
    if reg is None or state is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    refs = find_related(hybrid_search(state, q).items, reg.by_id)
    return {"candidates": [{"id": r.id, "label": r.label} for r in refs]}


class ConsentBody(BaseModel):
    user_label: str | None = None


@app.post("/consent")
def consent(body: ConsentBody, request: Request):
    decision = limiter.check_consent(client_ip(request))
    if not decision.allowed:
        raise _too_many(decision)
    sid = store.new_session(
        config.logs_db_path,
        consent_version=CONSENT_VERSION,
        user_label=body.user_label,
    )
    return {"session_id": sid, "consent_version": CONSENT_VERSION}


class ChatBody(BaseModel):
    session_id: str
    query: str
    # 가이드 네비에서 CMS 문서를 누를 때 'CMS' 로 지정 → CMS 스코프 검색. 미지정 시
    # 서버가 질문 내용으로 라우팅(기본 LMS). LMS 네비/FAQ 클릭은 굳이 안 보내도 됨.
    manual: str | None = None


@app.post("/chat")
async def chat(body: ChatBody, request: Request):
    if not store.get_session(config.logs_db_path, body.session_id):
        raise HTTPException(status_code=403, detail="동의 후 사용 가능합니다")
    # 503(초기화 중)을 상한보다 먼저 본다 — 여기서 돌려보내는 요청은 Gemini 를
    # 한 번도 부르지 않으므로 쿼터를 깎으면 안 된다. 부팅 직후 요청이 몰리면
    # 헛되이 일일 상한을 태우게 된다.
    state = getattr(request.app.state, "rag", None)
    if state is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    # 이 지점을 통과하면 실제로 Gemini 과금이 일어난다.
    decision = limiter.check_chat(body.session_id)
    if not decision.allowed:
        raise _too_many(decision)
    return StreamingResponse(_chat_sse(state, body), media_type="text/event-stream")


async def _chat_sse(state: RagState, body: ChatBody):
    started = time.time()
    final_text = ""
    sources: tuple[Source, ...] = ()
    score = 0.0
    text_parts: list[str] = []

    async for evt in stream_response(state, body.query, manual=body.manual):
        if evt.type == "text":
            text_parts.append(evt.delta)
        elif evt.type == "text_final":
            final_text = evt.text
        elif evt.type == "done":
            sources = evt.sources
            score = evt.score
        yield _serialize_sse(evt)

    latency_ms = int((time.time() - started) * 1000)
    full = final_text if final_text else "".join(text_parts)
    turn_id = store.add_turn(
        config.logs_db_path,
        session_id=body.session_id,
        query=body.query,
        response=full,
        retrieved_sources=list(sources),
        retrieved_score=score,
        latency_ms=latency_ms,
    )
    yield _serialize_sse(ChatEvent(type="turn_id", turn_id=turn_id))


class FeedbackBody(BaseModel):
    turn_id: int
    rating: int
    comment: str | None = None


@app.post("/feedback")
def feedback(body: FeedbackBody):
    if body.rating not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="rating은 1~3")
    store.add_feedback(
        config.logs_db_path,
        turn_id=body.turn_id,
        rating=body.rating,
        comment=body.comment,
    )
    return {"ok": True}


def _require_admin(provided: str | None) -> None:
    """관리자 토큰 검증. 토큰 미설정 시 엔드포인트 자체를 숨긴다(404)."""
    expected = config.admin_token
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/admin/logs")
def admin_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    format: str = Query("json"),
    x_admin_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    """대화 기록 조회/내보내기. X-Admin-Token 헤더 또는 ?token= 으로 인증."""
    _require_admin(x_admin_token or token)
    turns = store.list_turns(config.logs_db_path, limit=limit, offset=offset)
    if format == "csv":
        return Response(
            content=store.turns_to_csv(turns),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=chat_logs.csv"},
        )
    return {
        "total": store.count_turns(config.logs_db_path),
        "limit": limit,
        "offset": offset,
        "turns": turns,
    }


@app.get("/admin/usage")
def admin_usage(
    x_admin_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    """오늘의 /chat 호출 수와 상한. 상한만 걸어두고 소진 여부를 볼 수단이 없으면
    비용 사고를 사후에도 모른다. 카운터는 메모리라 재시작하면 0 이다."""
    _require_admin(x_admin_token or token)
    return limiter.snapshot()


class PurgeBody(BaseModel):
    session_id: str


@app.post("/purge")
def purge(body: PurgeBody):
    store.purge_session(config.logs_db_path, body.session_id)
    limiter.forget_session(body.session_id)
    return {"ok": True}
