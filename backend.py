from __future__ import annotations
import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app_types import ChatEvent, Source
from config import load_config
from db import store
from generation.catalog import catalog_as_dict
from generation.guide import build_guide
from generation.stream import stream_response
from index.vector_store import get_collection
from rag.state import RagState, load_rag_state
from retrieval.search import _chunk_from_meta


CONSENT_VERSION = "2026-05-26-v1"

config = load_config()
store.init_schema(config.logs_db_path)
_state: RagState | None = None


def _serialize_sse(evt: ChatEvent | dict) -> str:
    """ChatEvent | dict → SSE 라인."""
    if is_dataclass(evt):
        payload: dict = {}
        for k, v in asdict(evt).items():
            if k == "sources":
                payload[k] = [asdict(s) if is_dataclass(s) else s for s in evt.sources]
            elif k == "images":
                payload[k] = list(evt.images)
            else:
                payload[k] = v
    else:
        payload = evt
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_state_sync() -> None:
    global _state
    _state = load_rag_state(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] RagState 사전 로드 시작 (BGE-M3, 약 10~20초)...", flush=True)
    t0 = time.time()
    await asyncio.to_thread(_build_state_sync)
    print(f"[startup] RagState 준비 완료 ({time.time() - t0:.1f}s)", flush=True)
    yield


app = FastAPI(title="LMS 챗봇", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
if config.assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(config.assets_dir)), name="assets")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/privacy")
def privacy_page():
    return FileResponse("static/privacy.html")


@app.get("/health")
def health():
    return {"ok": True, "consent_version": CONSENT_VERSION}


@app.get("/catalog")
async def catalog():
    return catalog_as_dict()


@app.get("/guide")
async def guide(doc: str = Query(...)):
    if _state is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    coll = get_collection(_state.chroma)
    res = coll.get(where={"doc_title": doc}, include=["documents", "metadatas"])
    chunks = [
        _chunk_from_meta(cid, d, m)
        for cid, d, m in zip(res["ids"], res["documents"], res["metadatas"])
    ]
    result = build_guide(chunks, doc)
    if result is None:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    return result


class ConsentBody(BaseModel):
    user_label: str | None = None


@app.post("/consent")
def consent(body: ConsentBody):
    sid = store.new_session(
        config.logs_db_path,
        consent_version=CONSENT_VERSION,
        user_label=body.user_label,
    )
    return {"session_id": sid, "consent_version": CONSENT_VERSION}


class ChatBody(BaseModel):
    session_id: str
    query: str


@app.post("/chat")
async def chat(body: ChatBody):
    if not store.get_session(config.logs_db_path, body.session_id):
        raise HTTPException(status_code=403, detail="동의 후 사용 가능합니다")
    if _state is None:
        raise HTTPException(status_code=503, detail="서버 초기화 중입니다")
    return StreamingResponse(_chat_sse(body), media_type="text/event-stream")


async def _chat_sse(body: ChatBody):
    started = time.time()
    final_text = ""
    sources: tuple[Source, ...] = ()
    score = 0.0
    text_parts: list[str] = []

    async for evt in stream_response(_state, body.query):
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


class PurgeBody(BaseModel):
    session_id: str


@app.post("/purge")
def purge(body: PurgeBody):
    store.purge_session(config.logs_db_path, body.session_id)
    return {"ok": True}
