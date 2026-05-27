# Functional Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec `2026-05-27-functional-refactor-design.md` 의 실용 FP 리팩터링 적용. Database/Embedder/RagEngine 3개 클래스 제거, 횡단 데이터 타입을 `types.py` 1개로, env 단일 진입점 `config.py`, RagState frozen dc + 모듈 함수. 외부 동작·테스트 결과 100% 보존.

**Architecture:** 의존성 그래프 역방향 진행 (토대 → 잎). `types.py`/`config.py` 가장 먼저 (다른 모듈이 임포트할 토대), 그다음 `index/` → `db/` → `rag/` → `retrieval/` → `generation/` → `backend.py` 순. 각 Task 끝나면 전체 테스트 통과 유지. 외부에서 보면 동작 변화 0.

**Tech Stack:** Python 3.11+, frozen dataclasses, FastAPI, sqlite3, chromadb, sentence-transformers, rank-bm25, pytest.

---

## File Structure (after)

```
backend.py                    # 얇은 핸들러만
config.py                     # NEW
types.py                      # NEW (Chunk, Source, Retrieval, ChatEvent)

db/
  schema.py                   # 변경 X
  store.py                    # RENAME (was dao.py): 순수 함수

ingest/
  extract.py                  # 변경 X
  preprocess.py               # 변경 X
  chunk.py                    # tuple 화 (image_refs 등)
  pipeline.py                 # NEW (run_ingest)
  cli.py                      # 얇은 진입점

index/
  embed.py                    # 함수만 (load_embedder, encode_texts)
  vector_store.py             # NEW (Chroma 헬퍼)
  bm25.py                     # RENAME (was bm25_index.py)

retrieval/
  hybrid.py                   # 변경 X
  search.py                   # NEW (hybrid_search)
  cli.py                      # 임포트만 갱신

generation/
  persona.py                  # 변경 X
  filters.py                  # 변경 X
  guardrail.py                # 변경 X
  stream.py                   # RENAME (was pipeline.py): stream_response 함수

rag/
  __init__.py                 # NEW
  state.py                    # NEW (RagState + load_rag_state)

tests/
  test_store.py               # RENAME (was test_dao.py)
  test_bm25.py                # RENAME (was test_bm25_index.py)
  나머지 8개 — 임포트만 갱신
```

---

## Task 1: `types.py` — 횡단 데이터 타입

**Files:**
- Create: `types.py`

- [ ] **Step 1: types.py 작성**

```python
# types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


DocSet = Literal["guide", "faq"]
ChunkId = str
Score = float


@dataclass(frozen=True)
class Chunk:
    chunk_id: ChunkId
    text: str
    source: str
    doc_set: DocSet
    title: str
    section_path: tuple[str, ...] = ()
    image_refs: tuple[str, ...] = ()
    csv_refs: tuple[str, ...] = ()
    notion_url: str = ""


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: Score
    bm25_score: Score
    embed_score: Score


@dataclass(frozen=True)
class Source:
    title: str
    url: str = ""


@dataclass(frozen=True)
class Retrieval:
    chunks: tuple[Chunk, ...]
    top_score: Score


@dataclass(frozen=True)
class ChatEvent:
    """ /chat SSE 스트림 단위 이벤트.
      text: delta 채워짐 (스트리밍 토큰 일부)
      text_final: text 채워짐 (스트림 종료 시 풀 클린업 결과)
      done: images, sources, score 채워짐
      turn_id: turn_id 채워짐 (DB 저장 후 클라이언트 피드백용)
    """
    type: Literal["text", "text_final", "done", "turn_id"]
    delta: str = ""
    text: str = ""
    images: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    score: Score = 0.0
    turn_id: int | None = None
```

- [ ] **Step 2: import 검증**

```bash
.venv/bin/python -c "from types import Chunk, Source, Retrieval, ChatEvent; print('ok', Chunk('a','b','c','guide','d'))"
```

이때 stdlib `types` 와 충돌 우려 있음. 검증 결과 ImportError 또는 attribute 오류 나오면 다음 step 으로 이름 변경 (보통 stdlib `types` 가 먼저 잡힘).

- [ ] **Step 3: 충돌 시 우회 — `app_types.py` 로 변경**

stdlib `types` 와 충돌이 확인되면 파일명을 `app_types.py` 로 바꾸고 본 계획서 전반의 `from types import ...` 를 `from app_types import ...` 로 일괄 변경. (대안: PYTHONPATH 우선순위 트릭 — 비추천. 명시적 이름이 안전.)

```bash
mv types.py app_types.py
# 이후 모든 Task 에서 'from types import' → 'from app_types import'
```

- [ ] **Step 4: 커밋**

```bash
git add types.py 2>/dev/null || git add app_types.py
git commit -m "Task 1: cross-cutting types module (Chunk, Source, Retrieval, ChatEvent)"
```

---

## Task 2: `config.py` — env 로딩 단일 진입점

**Files:**
- Create: `config.py`

- [ ] **Step 1: config.py 작성**

```python
# config.py
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    ollama_host: str
    ollama_model: str
    embed_model: str
    chroma_dir: Path
    bm25_path: Path
    logs_db_path: Path
    assets_dir: Path
    raw_dir: Path
    port: int


def load_config() -> AppConfig:
    load_dotenv()
    return AppConfig(
        ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "gemma3:4b"),
        embed_model=os.environ.get("EMBED_MODEL", "BAAI/bge-m3"),
        chroma_dir=Path(os.environ.get("CHROMA_DIR", "./data/chroma")),
        bm25_path=Path(os.environ.get("BM25_PATH", "./data/bm25.pkl")),
        logs_db_path=Path(os.environ.get("LOGS_DB_PATH", "./data/chat_logs.db")),
        assets_dir=Path(os.environ.get("ASSETS_DIR", "./data/assets")),
        raw_dir=Path(os.environ.get("RAW_DIR", "./data/raw")),
        port=int(os.environ.get("PORT", "8080")),
    )
```

- [ ] **Step 2: 검증**

```bash
.venv/bin/python -c "from config import load_config; c=load_config(); print(c.ollama_model, c.chroma_dir)"
```
Expected: `gemma3:4b ./data/chroma` 또는 `.env` 값.

- [ ] **Step 3: 커밋**

```bash
git add config.py
git commit -m "Task 2: AppConfig + load_config() single env entry"
```

---

## Task 3: `index/bm25.py` — bm25_index.py 리네임 + Chunk 타입 갱신

**Files:**
- Rename: `index/bm25_index.py` → `index/bm25.py`
- Modify: `index/bm25.py` (Chunk 임포트 경로 변경)

- [ ] **Step 1: 파일 리네임 (git mv)**

```bash
git mv index/bm25_index.py index/bm25.py
```

- [ ] **Step 2: Chunk 임포트 경로 변경**

`index/bm25.py` 의 임포트:
```python
# 변경 전
from retrieval.types import Chunk

# 변경 후
from app_types import Chunk
```

(types vs app_types 는 Task 1 결과에 따름)

- [ ] **Step 3: 테스트 파일 리네임 + 임포트 갱신**

```bash
git mv tests/test_bm25_index.py tests/test_bm25.py
```

`tests/test_bm25.py`:
```python
# 변경 전
from index.bm25_index import build_bm25, save_bm25, load_bm25, query_bm25
from retrieval.types import Chunk

# 변경 후
from index.bm25 import build_bm25, save_bm25, load_bm25, query_bm25
from app_types import Chunk
```

- [ ] **Step 4: 테스트 실행**

```bash
.venv/bin/pytest tests/test_bm25.py -v
```
Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add -A
git commit -m "Task 3: rename bm25_index → bm25, switch to app_types"
```

---

## Task 4: `index/embed.py` — Embedder 클래스 제거 + vector_store.py 분리

**Files:**
- Modify: `index/embed.py`
- Create: `index/vector_store.py`

- [ ] **Step 1: 새 `index/embed.py` 작성 (함수만)**

```python
# index/embed.py
from __future__ import annotations
import os

from sentence_transformers import SentenceTransformer


_MAX_SEQ_LEN = 1024  # CPU 추론 안전선


def load_embedder(model_name: str | None = None) -> SentenceTransformer:
    name = model_name or os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
    model = SentenceTransformer(name)
    model.max_seq_length = _MAX_SEQ_LEN
    return model


def encode_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    vecs = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=4,
    )
    return [v.tolist() for v in vecs]
```

- [ ] **Step 2: 새 `index/vector_store.py` 작성**

```python
# index/vector_store.py
from __future__ import annotations
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from app_types import Chunk
from index.embed import encode_texts


_COLLECTION = "lms_chunks"


def get_chroma_client(persist_dir: Path):
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def upsert_chunks(client, model: SentenceTransformer, chunks: list[Chunk]) -> None:
    coll = client.get_or_create_collection(_COLLECTION)
    if not chunks:
        return
    ids = [c.chunk_id for c in chunks]
    docs = [c.text for c in chunks]
    metas = [{
        "source": c.source,
        "doc_set": c.doc_set,
        "title": c.title,
        "section_path": " > ".join(c.section_path),
        "image_refs": ",".join(c.image_refs),
        "notion_url": c.notion_url,
    } for c in chunks]
    vecs = encode_texts(model, docs)
    coll.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)


def query_embed(client, model: SentenceTransformer, query: str, k: int = 20) -> list[tuple[str, float]]:
    coll = client.get_or_create_collection(_COLLECTION)
    qvec = encode_texts(model, [query])[0]
    res = coll.query(query_embeddings=[qvec], n_results=k)
    ids = res["ids"][0]
    dists = res["distances"][0]
    return [(i, max(0.0, 1.0 - d / 2.0)) for i, d in zip(ids, dists)]


def get_collection(client):
    return client.get_or_create_collection(_COLLECTION)
```

- [ ] **Step 3: 검증 (임포트만)**

```bash
.venv/bin/python -c "from index.embed import load_embedder, encode_texts; from index.vector_store import get_chroma_client, upsert_chunks, query_embed; print('ok')"
```

- [ ] **Step 4: 커밋**

```bash
git add index/embed.py index/vector_store.py
git commit -m "Task 4: drop Embedder class, split vector_store.py from embed.py"
```

---

## Task 5: `db/store.py` — Database 클래스를 모듈 함수로

**Files:**
- Rename: `db/dao.py` → `db/store.py`
- Modify: `db/store.py` (클래스 제거)
- Rename: `tests/test_dao.py` → `tests/test_store.py`
- Modify: `tests/test_store.py` (API 호출 형식 변경)

- [ ] **Step 1: 파일 리네임**

```bash
git mv db/dao.py db/store.py
git mv tests/test_dao.py tests/test_store.py
```

- [ ] **Step 2: `db/store.py` 전체 재작성**

```python
# db/store.py
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from db.schema import SCHEMA


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(db_path: Path) -> None:
    with _conn(db_path) as c:
        c.executescript(SCHEMA)


def new_session(db_path: Path, *, consent_version: str, user_label: str | None) -> str:
    sid = uuid.uuid4().hex
    ts = _now()
    with _conn(db_path) as c:
        c.execute(
            "INSERT INTO sessions(session_id, created_at, consent_version, consent_at, user_label) "
            "VALUES (?,?,?,?,?)",
            (sid, ts, consent_version, ts, user_label),
        )
    return sid


def get_session(db_path: Path, session_id: str) -> dict | None:
    with _conn(db_path) as c:
        r = c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(r) if r else None


def add_turn(db_path: Path, *, session_id: str, query: str, response: str,
             retrieved_sources: list, retrieved_score: float | None,
             latency_ms: int | None) -> int:
    with _conn(db_path) as c:
        cur = c.execute(
            "INSERT INTO turns(session_id, created_at, query, response, retrieved_sources, "
            "retrieved_score, latency_ms) VALUES (?,?,?,?,?,?,?)",
            (session_id, _now(), query, response,
             json.dumps(retrieved_sources, ensure_ascii=False, default=lambda o: o.__dict__),
             retrieved_score, latency_ms),
        )
        return int(cur.lastrowid)


def add_feedback(db_path: Path, *, turn_id: int, rating: int, comment: str | None) -> None:
    with _conn(db_path) as c:
        c.execute(
            "INSERT INTO feedback(turn_id, rating, comment, created_at) VALUES (?,?,?,?)",
            (turn_id, rating, comment, _now()),
        )


def feedback_for(db_path: Path, turn_id: int) -> list[dict]:
    with _conn(db_path) as c:
        rs = c.execute("SELECT * FROM feedback WHERE turn_id = ?", (turn_id,)).fetchall()
        return [dict(r) for r in rs]


def purge_session(db_path: Path, session_id: str) -> None:
    with _conn(db_path) as c:
        c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
```

- [ ] **Step 3: `tests/test_store.py` 전체 재작성**

```python
# tests/test_store.py
from pathlib import Path

from db import store


def test_consent_and_session_roundtrip(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label="강민")
    s = store.get_session(db_path, sid)
    assert s["consent_version"] == "v1"
    assert s["user_label"] == "강민"


def test_turn_and_feedback(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    tid = store.add_turn(
        db_path,
        session_id=sid, query="퀴즈?", response="이렇게.",
        retrieved_sources=["퀴즈 개요"], retrieved_score=0.7, latency_ms=420,
    )
    assert tid > 0
    store.add_feedback(db_path, turn_id=tid, rating=3, comment="도움됨")
    fs = store.feedback_for(db_path, tid)
    assert fs[0]["rating"] == 3
    assert fs[0]["comment"] == "도움됨"


def test_purge_session(tmp_path: Path):
    db_path = tmp_path / "t.db"
    store.init_schema(db_path)
    sid = store.new_session(db_path, consent_version="v1", user_label=None)
    tid = store.add_turn(db_path, session_id=sid, query="q", response="r",
                         retrieved_sources=[], retrieved_score=0.0, latency_ms=0)
    store.add_feedback(db_path, turn_id=tid, rating=2, comment=None)
    store.purge_session(db_path, sid)
    assert store.get_session(db_path, sid) is None
    assert store.feedback_for(db_path, tid) == []
```

- [ ] **Step 4: 테스트 실행**

```bash
.venv/bin/pytest tests/test_store.py -v
```
Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add -A
git commit -m "Task 5: db.store module functions (drop Database class)"
```

---

## Task 6: `retrieval/types.py` 삭제 + 임포트 정리

**Files:**
- Delete: `retrieval/types.py`
- Modify: 이 파일을 임포트하던 모든 곳 (이미 위 Task 들에서 처리)

- [ ] **Step 1: 사용처 확인**

```bash
grep -rn "from retrieval.types" --include="*.py" . | grep -v ".venv"
```
Expected: 0 hits (앞서 Task 1~5에서 모두 갱신됨). 만약 hits 있으면 해당 파일도 `from app_types import ...` 로 갱신.

- [ ] **Step 2: 삭제**

```bash
git rm retrieval/types.py
```

- [ ] **Step 3: 전체 테스트 확인 (회귀 X)**

```bash
.venv/bin/pytest -q
```
Expected: 모든 기존 테스트 통과 (chunk 테스트는 아직 list 사용 중일 수 있어 깨질 가능성 — 다음 Task 에서 처리).

만약 `test_chunk.py` 가 실패하면 Task 7 진행 시 함께 수정. 우선 다른 테스트 통과만 확인.

- [ ] **Step 4: 커밋**

```bash
git add -A
git commit -m "Task 6: drop retrieval/types.py (types moved to app_types)"
```

---

## Task 7: `ingest/chunk.py` — Chunk tuple 화 적응

**Files:**
- Modify: `ingest/chunk.py`
- Modify: `tests/test_chunk.py`

- [ ] **Step 1: `ingest/chunk.py` 임포트 + Chunk 생성 부분 수정**

기존 `Chunk(..., section_path=list(section_path), image_refs=extract_image_refs(text))` 부분을 tuple 로 변환.

```python
# 임포트
from app_types import Chunk, DocSet

# extract_image_refs 는 list 반환하므로 tuple() 로 감쌈
def _emit(prefix: str, base_title: str, body: str) -> list[Chunk]:
    out: list[Chunk] = []
    parts = _split_long(body)
    for j, part in enumerate(parts):
        suffix = "" if len(parts) == 1 else f" ({j + 1}/{len(parts)})"
        out.append(
            Chunk(
                chunk_id=_hash_id(source, prefix, str(j)),
                text=part,
                source=source,
                doc_set=doc_set,
                title=base_title + suffix,
                section_path=tuple(section_path),
                image_refs=tuple(extract_image_refs(part)),
                notion_url=notion_url,
            )
        )
    return out
```

같은 식으로 `chunk_csv_file` 의 Chunk 생성에도 `csv_refs=(source,)` 적용.

- [ ] **Step 2: `tests/test_chunk.py` 임포트 + assert 형식 갱신**

```python
# 임포트 변경
from ingest.chunk import chunk_markdown_file, chunk_csv_file, extract_image_refs

# extract_image_refs 는 list 반환 그대로 — 함수 자체는 미변경. assert 는 그대로.
# chunk.image_refs 비교는 tuple 로:
def test_chunk_markdown_small_returns_single(tmp_path: Path):
    ...
    assert c.image_refs == ("img/q.png",)        # was ["img/q.png"]
    assert c.section_path == ("시험 및 설문",)   # was ["시험 및 설문"]
    ...
```

전체 test_chunk.py 의 assert 형태를 list 에서 tuple 로 변경. 검색 `["...` → `("...,)` 일일이 확인.

- [ ] **Step 3: 테스트 실행**

```bash
.venv/bin/pytest tests/test_chunk.py -v
```
Expected: 8 passed.

- [ ] **Step 4: 커밋**

```bash
git add ingest/chunk.py tests/test_chunk.py
git commit -m "Task 7: adapt ingest/chunk.py + tests to frozen Chunk (tuple fields)"
```

---

## Task 8: `rag/state.py` + `__init__.py` — RagState 정의

**Files:**
- Create: `rag/__init__.py`
- Create: `rag/state.py`

- [ ] **Step 1: 디렉터리 + __init__.py**

```bash
mkdir -p rag
touch rag/__init__.py
```

- [ ] **Step 2: `rag/state.py` 작성**

```python
# rag/state.py
from __future__ import annotations
from dataclasses import dataclass

from sentence_transformers import SentenceTransformer

from config import AppConfig
from index.bm25 import BM25Pack, load_bm25
from index.embed import load_embedder
from index.vector_store import get_chroma_client


@dataclass(frozen=True)
class RagState:
    embedder: SentenceTransformer
    chroma: object  # chromadb.api.ClientAPI — 외부 타입 직접 노출 회피
    bm25: BM25Pack
    ollama_host: str
    ollama_model: str


def load_rag_state(config: AppConfig) -> RagState:
    return RagState(
        embedder=load_embedder(config.embed_model),
        chroma=get_chroma_client(config.chroma_dir),
        bm25=load_bm25(config.bm25_path),
        ollama_host=config.ollama_host,
        ollama_model=config.ollama_model,
    )
```

- [ ] **Step 3: 검증 (임포트만)**

```bash
.venv/bin/python -c "from rag.state import RagState, load_rag_state; print('ok')"
```

- [ ] **Step 4: 커밋**

```bash
git add rag/__init__.py rag/state.py
git commit -m "Task 8: rag.state with RagState frozen dc + load_rag_state(config)"
```

---

## Task 9: `retrieval/search.py` — hybrid_search 함수

**Files:**
- Create: `retrieval/search.py`

- [ ] **Step 1: 작성**

```python
# retrieval/search.py
from __future__ import annotations

from app_types import Chunk, Retrieval
from index.bm25 import query_bm25
from index.vector_store import get_collection, query_embed
from rag.state import RagState
from retrieval.hybrid import combine_scores


TOP_K = 5
EMBED_K = 20
BM25_K = 20


def hybrid_search(state: RagState, query: str, *, k: int = TOP_K) -> Retrieval:
    bm = dict(query_bm25(state.bm25, query, k=BM25_K))
    emb = dict(query_embed(state.chroma, state.embedder, query, k=EMBED_K))
    merged = combine_scores(bm, emb, k=k)
    if not merged:
        return Retrieval(chunks=(), top_score=0.0)

    coll = get_collection(state.chroma)
    ids = [cid for cid, _ in merged]
    res = coll.get(ids=ids, include=["documents", "metadatas"])
    meta_by_id = {i: (d, m) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])}

    chunks: list[Chunk] = []
    for cid, _ in merged:
        if cid not in meta_by_id:
            continue
        doc, meta = meta_by_id[cid]
        section_path = tuple(p for p in (meta.get("section_path") or "").split(" > ") if p)
        image_refs = tuple(s for s in (meta.get("image_refs") or "").split(",") if s)
        chunks.append(Chunk(
            chunk_id=cid,
            text=doc,
            source=meta.get("source", ""),
            doc_set=meta.get("doc_set", "guide"),
            title=meta.get("title", ""),
            section_path=section_path,
            image_refs=image_refs,
            notion_url=meta.get("notion_url", "") or "",
        ))
    return Retrieval(chunks=tuple(chunks), top_score=merged[0][1])
```

- [ ] **Step 2: 검증**

```bash
.venv/bin/python -c "from retrieval.search import hybrid_search, TOP_K; print('ok', TOP_K)"
```

- [ ] **Step 3: 커밋**

```bash
git add retrieval/search.py
git commit -m "Task 9: retrieval.search.hybrid_search(state, query) -> Retrieval"
```

---

## Task 10: `generation/stream.py` — RagEngine.stream_chat → 함수

**Files:**
- Rename: `generation/pipeline.py` → `generation/stream.py`
- Modify: `generation/stream.py` (RagEngine 제거, stream_response 함수로)

- [ ] **Step 1: 리네임**

```bash
git mv generation/pipeline.py generation/stream.py
```

- [ ] **Step 2: 전체 재작성**

```python
# generation/stream.py
from __future__ import annotations
import json
from typing import AsyncIterator

import httpx

from app_types import ChatEvent, Source
from generation.filters import clean_response, streaming_clean
from generation.guardrail import META_REPLY, is_meta_question
from generation.persona import build_prompt
from rag.state import RagState
from retrieval.search import hybrid_search, TOP_K


SCORE_THRESHOLD = 0.25
RELEVANCE_FLOOR = 0.30
RELEVANCE_RATIO = 0.50
NO_GUIDE_MSG = "해당 내용은 현재 가이드에서 확인이 어렵습니다. 교육혁신처 교수학습개발센터로 문의 부탁드립니다."


def _is_relevant(score: float, top_score: float) -> bool:
    return score >= RELEVANCE_FLOOR and score >= top_score * RELEVANCE_RATIO


async def stream_response(state: RagState, query: str) -> AsyncIterator[ChatEvent]:
    if is_meta_question(query):
        yield ChatEvent(type="text", delta=META_REPLY)
        yield ChatEvent(type="text_final", text=META_REPLY)
        yield ChatEvent(type="done")
        return

    retrieval = hybrid_search(state, query)
    if retrieval.top_score < SCORE_THRESHOLD:
        yield ChatEvent(type="text", delta=NO_GUIDE_MSG)
        yield ChatEvent(type="text_final", text=NO_GUIDE_MSG)
        yield ChatEvent(type="done", score=retrieval.top_score)
        return

    chunks = retrieval.chunks
    top_score = retrieval.top_score

    # 컨텍스트: 1위는 항상, 나머지는 임계 통과만
    if chunks:
        # 점수는 검색기에서 사라졌으므로 retrieval 결과 순서를 신뢰 (이미 정렬됨)
        # 1위 무조건 포함. 2위부터: 우리는 통합 점수가 없어 보수적으로 포함
        relevant_ctx = list(chunks[:TOP_K])
    else:
        relevant_ctx = []

    messages = build_prompt(query, [{"title": c.title, "text": c.text} for c in relevant_ctx])
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

    yield ChatEvent(type="text_final", text=clean_response(raw_buf))

    # 이미지 (상위 5개)
    seen_imgs: list[str] = []
    for c in relevant_ctx:
        for img in c.image_refs:
            if img and img not in seen_imgs:
                seen_imgs.append(img)
        if len(seen_imgs) >= 5:
            break

    # 출처 (top-3, FAQ — 제외)
    sources: list[Source] = []
    seen_titles: set[str] = set()
    for c in relevant_ctx:
        t = c.title
        if not t or t in seen_titles:
            continue
        if t.startswith("FAQ —"):
            continue
        sources.append(Source(title=t, url=c.notion_url or ""))
        seen_titles.add(t)
        if len(sources) >= 3:
            break

    yield ChatEvent(
        type="done",
        images=tuple(seen_imgs[:5]),
        sources=tuple(sources),
        score=top_score,
    )
```

**주의**: 현재 코드의 `_is_relevant` 임계 필터는 컨텍스트의 score 가 있어야 가능한데, `hybrid_search` 의 `Retrieval.chunks` 는 점수를 떨어뜨림. 만약 임계 필터를 유지하고 싶으면 `Retrieval` 에 점수 같이 담거나 별도 함수 반환. **본 Task 에서는 TOP_K 까지 그대로 받는 단순 동작으로 시작** — 회귀 동작 약간 변할 수 있음 (top 5 모두 컨텍스트). 다음 Task 후 라이브 테스트에서 검증 후 보강.

- [ ] **Step 3: 검증 (임포트만)**

```bash
.venv/bin/python -c "from generation.stream import stream_response, ChatEvent; print('ok')"
```

- [ ] **Step 4: 커밋**

```bash
git add -A
git commit -m "Task 10: generation.stream.stream_response (RagEngine.stream_chat → function)"
```

---

## Task 11: `retrieval/search.py` 에 임계 필터 + 점수 보존 강화

**Files:**
- Modify: `app_types.py` (Retrieval 에 chunks 와 점수를 묶은 형태로)
- Modify: `retrieval/search.py`
- Modify: `generation/stream.py`

이전 동작(임계 필터)을 정확히 보존하려면 검색이 점수도 넘겨야 함.

- [ ] **Step 1: `app_types.py` Retrieval 확장**

기존 `Retrieval` 을 다음으로 교체:

```python
@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: Score


@dataclass(frozen=True)
class Retrieval:
    items: tuple[ScoredChunk, ...]
    top_score: Score
```

- [ ] **Step 2: `retrieval/search.py` 갱신**

```python
# 변경 부분
from app_types import Chunk, Retrieval, ScoredChunk
...

def hybrid_search(state: RagState, query: str, *, k: int = TOP_K) -> Retrieval:
    bm = dict(query_bm25(state.bm25, query, k=BM25_K))
    emb = dict(query_embed(state.chroma, state.embedder, query, k=EMBED_K))
    merged = combine_scores(bm, emb, k=k)
    if not merged:
        return Retrieval(items=(), top_score=0.0)

    coll = get_collection(state.chroma)
    ids = [cid for cid, _ in merged]
    res = coll.get(ids=ids, include=["documents", "metadatas"])
    meta_by_id = {i: (d, m) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])}

    items: list[ScoredChunk] = []
    for cid, score in merged:
        if cid not in meta_by_id:
            continue
        doc, meta = meta_by_id[cid]
        section_path = tuple(p for p in (meta.get("section_path") or "").split(" > ") if p)
        image_refs = tuple(s for s in (meta.get("image_refs") or "").split(",") if s)
        chunk = Chunk(
            chunk_id=cid,
            text=doc,
            source=meta.get("source", ""),
            doc_set=meta.get("doc_set", "guide"),
            title=meta.get("title", ""),
            section_path=section_path,
            image_refs=image_refs,
            notion_url=meta.get("notion_url", "") or "",
        )
        items.append(ScoredChunk(chunk=chunk, score=score))
    return Retrieval(items=tuple(items), top_score=merged[0][1])
```

- [ ] **Step 3: `generation/stream.py` 의 relevant_ctx 부분 갱신**

```python
# 변경 부분
retrieval = hybrid_search(state, query)
top_score = retrieval.top_score
if top_score < SCORE_THRESHOLD:
    ...

# 1위 무조건 + 나머지는 임계 통과
relevant_items = [retrieval.items[0]] + [
    it for it in retrieval.items[1:] if _is_relevant(it.score, top_score)
] if retrieval.items else []

messages = build_prompt(query, [{"title": it.chunk.title, "text": it.chunk.text} for it in relevant_items])

# 이미지 / 출처 도 relevant_items 의 chunk 에서
for it in relevant_items:
    for img in it.chunk.image_refs:
        ...
```

전체 stream_response 함수가 `relevant_ctx` 대신 `relevant_items` 사용하도록 일괄 변경.

- [ ] **Step 4: 검증**

```bash
.venv/bin/python -c "from retrieval.search import hybrid_search; from generation.stream import stream_response; print('ok')"
```

- [ ] **Step 5: 커밋**

```bash
git add -A
git commit -m "Task 11: preserve threshold filter via ScoredChunk + Retrieval.items"
```

---

## Task 12: `ingest/cli.py` 분리 — pipeline.py + 얇은 cli.py

**Files:**
- Create: `ingest/pipeline.py`
- Modify: `ingest/cli.py` (얇은 진입점)

- [ ] **Step 1: `ingest/pipeline.py` 작성**

```python
# ingest/pipeline.py
from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from app_types import Chunk
from config import AppConfig
from index.bm25 import build_bm25, save_bm25
from index.embed import load_embedder
from index.vector_store import get_chroma_client, upsert_chunks
from ingest.chunk import chunk_csv_file, chunk_markdown_file
from ingest.extract import (collect_csv, collect_images, collect_markdown,
                            copy_assets, unzip_all_recursive)
from ingest.preprocess import clean_markdown


@dataclass(frozen=True)
class IngestResult:
    chunk_count: int
    image_count: int


def _section_path_from(rel_path: Path) -> tuple[str, ...]:
    return tuple(p for p in rel_path.parts[:-1] if p not in ("", "."))


def _detect_doc_set(rel_path: Path) -> str:
    blob = " ".join(p.lower() for p in rel_path.parts)
    return "faq" if "faq" in blob else "guide"


def _rewrite_image_refs(chunk: Chunk, mapping: dict[str, str], raw_dir: Path) -> Chunk:
    new_refs: list[str] = []
    new_text = chunk.text
    for ref in chunk.image_refs:
        decoded = unquote(ref)
        src_dir = Path(chunk.source).parent
        abs_path = (src_dir / decoded).resolve()
        try:
            rel_to_raw = str(abs_path.relative_to(raw_dir.resolve()))
        except ValueError:
            continue
        if rel_to_raw in mapping:
            url = mapping[rel_to_raw]
            new_text = new_text.replace(f"({ref})", f"({url})")
            new_text = new_text.replace(f"({decoded})", f"({url})")
            new_refs.append(url)
    # frozen dc → 새 인스턴스
    from dataclasses import replace
    return replace(chunk, text=new_text, image_refs=tuple(new_refs))


def run_ingest(config: AppConfig, *, log=print) -> IngestResult:
    raw_dir = config.raw_dir
    assets_dir = config.assets_dir
    chroma_dir = config.chroma_dir
    bm25_path = config.bm25_path

    log(f"[1/5] zip 재귀 풀기: {raw_dir}")
    unzip_all_recursive(raw_dir)

    log("[2/5] assets 복사")
    images = collect_images(raw_dir)
    img_mapping = copy_assets(images, raw_dir, assets_dir)
    log(f"    이미지 {len(img_mapping)}개")

    log("[3/5] 청크 생성")
    all_chunks: list[Chunk] = []
    for md in collect_markdown(raw_dir):
        rel = md.relative_to(raw_dir)
        doc_set = _detect_doc_set(rel)
        section_path = list(_section_path_from(rel))
        text = clean_markdown(md.read_text(encoding="utf-8"))
        md.write_text(text, encoding="utf-8")
        for c in chunk_markdown_file(md, doc_set=doc_set, section_path=section_path):
            all_chunks.append(_rewrite_image_refs(c, img_mapping, raw_dir))
    for csv in collect_csv(raw_dir):
        doc_set = _detect_doc_set(csv.relative_to(raw_dir))
        all_chunks.extend(chunk_csv_file(csv, doc_set=doc_set))
    log(f"    총 청크: {len(all_chunks)}")

    if not all_chunks:
        log("청크가 0개입니다. data/raw 에 Notion export 가 있는지 확인하세요.")
        return IngestResult(chunk_count=0, image_count=len(img_mapping))

    log(f"[4/5] 임베딩 + ChromaDB ({chroma_dir})")
    embedder = load_embedder(config.embed_model)
    client = get_chroma_client(chroma_dir)
    upsert_chunks(client, embedder, all_chunks)

    log(f"[5/5] BM25 인덱스 저장 ({bm25_path})")
    pack = build_bm25(all_chunks)
    save_bm25(pack, bm25_path)

    log("완료")
    return IngestResult(chunk_count=len(all_chunks), image_count=len(img_mapping))
```

- [ ] **Step 2: `ingest/cli.py` 얇게 재작성**

```python
# ingest/cli.py
from __future__ import annotations
import argparse
import sys

from config import load_config
from ingest.pipeline import run_ingest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)  # 현재는 옵션 없음 — env 로 제어
    config = load_config()
    result = run_ingest(config)
    return 0 if result.chunk_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

(기존의 --raw/--assets/--chroma/--bm25 옵션은 사용 사례 거의 없어 제거. env 로 충분. 필요 시 재추가 가능.)

- [ ] **Step 3: 임포트 검증**

```bash
.venv/bin/python -c "from ingest.pipeline import run_ingest, IngestResult; from ingest.cli import main; print('ok')"
```

- [ ] **Step 4: 커밋**

```bash
git add ingest/pipeline.py ingest/cli.py
git commit -m "Task 12: split ingest.pipeline.run_ingest from thin ingest.cli"
```

---

## Task 13: `retrieval/cli.py` 갱신

**Files:**
- Modify: `retrieval/cli.py`

- [ ] **Step 1: 갱신 (config + RagState 사용)**

```python
# retrieval/cli.py
"""검색 단독 동작 확인용 CLI. Ollama 없이도 인덱스 품질 검증 가능.

사용: .venv/bin/python -m retrieval.cli "퀴즈 출제하는 방법"
"""
from __future__ import annotations
import argparse

from config import load_config
from rag.state import load_rag_state
from retrieval.search import hybrid_search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+", help="검색할 질의")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args(argv)

    query = " ".join(args.query)
    print(f"질의: {query}\n")

    config = load_config()
    state = load_rag_state(config)
    retrieval = hybrid_search(state, query, k=args.k)

    if not retrieval.items:
        print("검색 결과 없음")
        return 1

    for rank, it in enumerate(retrieval.items, 1):
        snippet = it.chunk.text[:160].replace("\n", " ")
        print(f"[{rank}] score={it.score:.3f}  title={it.chunk.title}")
        print(f"    {snippet}...")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 검증**

```bash
.venv/bin/python -c "from retrieval.cli import main; print('ok')"
```

- [ ] **Step 3: 커밋**

```bash
git add retrieval/cli.py
git commit -m "Task 13: retrieval.cli uses load_config + load_rag_state"
```

---

## Task 14: `backend.py` 슬림화

**Files:**
- Modify: `backend.py`

- [ ] **Step 1: 재작성**

```python
# backend.py
from __future__ import annotations
import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app_types import ChatEvent, Source
from config import load_config
from db import store
from generation.stream import stream_response
from rag.state import RagState, load_rag_state


CONSENT_VERSION = "2026-05-26-v1"

config = load_config()
store.init_schema(config.logs_db_path)
_state: RagState | None = None


def _serialize_sse(evt) -> str:
    """ChatEvent | dict → SSE 라인."""
    if isinstance(evt, ChatEvent):
        payload = asdict(evt)
        # Source dc → dict 변환
        payload["sources"] = [asdict(s) for s in evt.sources]
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
    images: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    score = 0.0
    text_parts: list[str] = []

    async for evt in stream_response(_state, body.query):
        if evt.type == "text":
            text_parts.append(evt.delta)
        elif evt.type == "text_final":
            final_text = evt.text
        elif evt.type == "done":
            images, sources, score = evt.images, evt.sources, evt.score
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


class PurgeBody(BaseModel):
    session_id: str


@app.post("/purge")
def purge(body: PurgeBody):
    store.purge_session(config.logs_db_path, body.session_id)
    return {"ok": True}
```

- [ ] **Step 2: 임포트 검증**

```bash
.venv/bin/python -c "import backend; print('ok', backend.app)"
```

- [ ] **Step 3: 커밋**

```bash
git add backend.py
git commit -m "Task 14: slim backend.py — uses config/store/state modules"
```

---

## Task 15: 전체 테스트 + 라이브 검증

**Files:** (검증만)

- [ ] **Step 1: 전체 pytest**

```bash
.venv/bin/pytest -v
```
Expected: 41+ passed (5 store + 8 chunk + 2 bm25 + 3 hybrid + 5 filters + 8 preprocess + 2 extract + 7+ guardrail = 약 40)

만약 임포트 오류면 grep 으로 잔존 `from retrieval.types` 또는 `from db.dao` 또는 `from index.bm25_index` 또는 `from generation.pipeline` 찾아 갱신.

```bash
grep -rn "from retrieval.types\|from db.dao\|from index.bm25_index\|from generation.pipeline" --include="*.py" . | grep -v ".venv"
```

- [ ] **Step 2: 인덱스 재빌드 (Chunk 메타 살짝 변경됐을 가능성)**

```bash
rm -rf data/chroma data/bm25.pkl
.venv/bin/python -m ingest.cli
```
Expected: `완료` 출력.

- [ ] **Step 3: retrieval CLI 스모크**

```bash
.venv/bin/python -m retrieval.cli "퀴즈 무작위 출제"
```
Expected: 상위 결과들이 퀴즈 관련.

- [ ] **Step 4: 백엔드 부팅 + /health + /chat 라이브 테스트**

```bash
lsof -ti :8080 | xargs -r kill -9 2>/dev/null
.venv/bin/uvicorn backend:app --host 127.0.0.1 --port 8080 --log-level warning &
SERVER_PID=$!
sleep 20  # RagState 로드 대기
curl -s http://localhost:8080/health
SID=$(curl -s -X POST http://localhost:8080/consent -H 'content-type: application/json' -d '{}' | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s -N -X POST http://localhost:8080/chat -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"query\":\"공지사항 작성\"}" | head -50
kill $SERVER_PID
```
Expected: SSE 이벤트 흘러나옴, 응답이 공지사항 관련.

- [ ] **Step 5: 최종 커밋 (필요 시 잔여 수정)**

```bash
git add -A
git status   # 깨끗하면 통과
git log --oneline -20
```

---

## Self-review

### Spec coverage
- 3.1 모듈 헤더 순서 → 작업 내 각 모듈 구현 시 본 순서 따름 (Task 4, 5, 9, 10, 12 등)
- 3.2 데이터는 frozen dc → Task 1 (types) + Chunk tuple 화 Task 7
- 3.3 동작은 모듈 함수 → Database/Embedder/RagEngine 제거 Task 4/5/10
- 3.4 wrapper 클래스 금지 → Embedder/Database 제거 + Chroma 직접 사용 (Task 4/5)
- 3.5 부수효과는 가장자리 → backend.py(Task 14) + ingest/cli(Task 12) 가 진입점, 나머지 순수
- 3.6 env 단일 진입점 → Task 2 config.py + 다른 모듈은 AppConfig 받음 (Task 8, 10, 12, 13, 14)
- 4.1 신규 6: types(T1), config(T2), ingest/pipeline(T12), vector_store(T4), retrieval/search(T9), rag/state(T8) ✓
- 4.2 리네임 3: bm25_index→bm25(T3), dao→store(T5), pipeline→stream(T10) ✓
- 4.3 클래스 3 제거: Embedder(T4), Database(T5), RagEngine(T10) ✓
- 5 types.py 내용 → Task 1 ✓
- 6 RagState → Task 8 ✓
- 7 AppConfig → Task 2 ✓
- 8 함수 시그니처 → Task 4/5/9/10/12 ✓
- 9 backend.py 슬림화 → Task 14 ✓
- 10 테스트 영향: test_dao→test_store(T5), test_bm25_index→test_bm25(T3), test_chunk(T7), 나머지 임포트 갱신 (T15 회귀에서 잡힘) ✓
- 11 작업 순서 11단계 → 본 plan 15 task 로 분해 (split steps + 검증 task)
- 12 위험: 임포트 순환은 단방향 의존성으로 회피 (config 토대, types 토대), Chunk tuple→`replace()` (T12), 테스트 임포트 즉시 갱신 (각 Task), lifespan 유지 (T14) ✓

### Placeholder scan
- Task 7 의 "검색 `["...` → `("...,)` 일일이 확인" — vague, 보강
- Task 15 의 grep 명령은 구체적 ✓
- "TBD" / "TODO" 없음 ✓

### Type consistency
- `Chunk` 필드 `section_path`, `image_refs`, `csv_refs` 가 spec 5 절·Task 1·Task 7 모두 `tuple[str, ...]` 로 일관 ✓
- `Retrieval` 정의가 Task 9 와 Task 11 사이에서 `chunks` → `items: tuple[ScoredChunk, ...]` 로 진화하므로 임포트 사이트가 모두 Task 11 에서 갱신되어야 함. retrieval/search.py 가 Task 11 에서 수정되고 generation/stream.py 도 Task 11 에서 수정됨 ✓
- `store.add_turn` 의 `retrieved_sources` 인자가 `list[Source]` 인지 `list[str]` 인지 — Task 5 는 `list` 로 두고 default JSON 직렬화 lambda 로 Source 도 받게 함. backend.py Task 14 는 `list(sources)` (Source list) 로 호출 ✓

### Scope check
단일 리팩터링 프로젝트. 분리 불필요.

### Ambiguity fix
Task 7 의 "list assert → tuple assert" 부분 명확화:

기존 테스트 코드의 list literal `[...]` 을 tuple literal `(...,)` 로 변경. 예:
- `assert c.image_refs == ["img/q.png"]` → `assert c.image_refs == ("img/q.png",)`
- `assert chunks[0].section_path == ["시험 및 설문"]` → `assert chunks[0].section_path == ("시험 및 설문",)`
- 단원소 tuple 은 반드시 trailing comma 필요

`extract_image_refs` 함수 자체는 list 반환 유지 (chunk 생성 시 `tuple(...)` 로 감쌈). 그래서 `test_extract_image_refs_*` 의 list assert 는 변경 X.
