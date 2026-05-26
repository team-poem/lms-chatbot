from __future__ import annotations
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db.dao import Database


load_dotenv()

CONSENT_VERSION = "2026-05-26-v1"
ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", "./data/assets"))
LOGS_DB_PATH = Path(os.environ.get("LOGS_DB_PATH", "./data/chat_logs.db"))

app = FastAPI(title="LMS 챗봇")
db = Database(LOGS_DB_PATH)
db.init()
_engine = None


def get_engine():
    """RagEngine 지연 초기화. 임포트 자체가 무거우므로 첫 요청 시 로드."""
    global _engine
    if _engine is None:
        from generation.pipeline import RagEngine
        _engine = RagEngine()
    return _engine


app.mount("/static", StaticFiles(directory="static"), name="static")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/privacy")
def privacy_page():
    return FileResponse("static/privacy.html")


@app.get("/health")
def health():
    return {"ok": True, "consent_version": CONSENT_VERSION}


class ConsentBody(BaseModel):
    user_label: str | None = None


@app.post("/consent")
def consent(body: ConsentBody):
    sid = db.new_session(consent_version=CONSENT_VERSION, user_label=body.user_label)
    return {"session_id": sid, "consent_version": CONSENT_VERSION}


class ChatBody(BaseModel):
    session_id: str
    query: str


@app.post("/chat")
async def chat(body: ChatBody):
    if not db.get_session(body.session_id):
        raise HTTPException(status_code=403, detail="동의 후 사용 가능합니다")

    eng = get_engine()
    started = time.time()
    response_text_parts: list[str] = []
    final_images: list[str] = []
    final_sources: list[str] = []
    final_score: float = 0.0

    async def gen():
        nonlocal final_images, final_sources, final_score
        async for evt in eng.stream_chat(body.query):
            if evt.get("type") == "text":
                response_text_parts.append(evt["delta"])
            elif evt.get("type") == "done":
                final_images = evt.get("images", [])
                final_sources = evt.get("sources", [])
                final_score = evt.get("score", 0.0)
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

        latency_ms = int((time.time() - started) * 1000)
        full = "".join(response_text_parts)
        turn_id = db.add_turn(
            session_id=body.session_id,
            query=body.query,
            response=full,
            retrieved_sources=final_sources,
            retrieved_score=final_score,
            latency_ms=latency_ms,
        )
        yield f"data: {json.dumps({'type': 'turn_id', 'turn_id': turn_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


class FeedbackBody(BaseModel):
    turn_id: int
    rating: int
    comment: str | None = None


@app.post("/feedback")
def feedback(body: FeedbackBody):
    if body.rating not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="rating은 1~3")
    db.add_feedback(turn_id=body.turn_id, rating=body.rating, comment=body.comment)
    return {"ok": True}


class PurgeBody(BaseModel):
    session_id: str


@app.post("/purge")
def purge(body: PurgeBody):
    db.purge_session(body.session_id)
    return {"ok": True}
