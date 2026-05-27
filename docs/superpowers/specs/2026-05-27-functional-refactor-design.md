# 함수형 리팩터링 설계 문서

- 작성일: 2026-05-27
- 상태: 초안 → 사용자 리뷰 대기
- 목표: 코드 일관성과 가독성을 위한 실용 FP 스타일 통일 + 파일 구조 정리

## 1. 동기

현재 21개 파일·1132 LOC 의 코드베이스는 모듈별로 스타일이 달라 흐름 파악이 어렵다.

- `db/dao.py` 는 `class Database` 로 sqlite3 를 감쌈
- `index/embed.py` 는 `class Embedder` 로 SentenceTransformer 를 감쌈
- `generation/pipeline.py` 는 `class RagEngine` 이 embedder/chroma/bm25/ollama 클라이언트를 다 들고 retrieve 와 stream_chat 까지 수행
- `ingest/cli.py` 는 명령형 main() 안에 [1/5]~[5/5] 진행 print 와 실제 처리가 섞여 있음
- 환경변수 (`os.environ`) 가 모듈마다 직접 접근됨 (`embed.py`, `pipeline.py`, `backend.py` 등 분산)
- 데이터 타입이 흩어져 있음: `Chunk` 는 `retrieval/types.py`, "context" 는 `pipeline.py` 안의 dict, "event" 는 dict, "source" 는 dict

문제는 파일 크기가 아니라 **스타일·경계의 비일관성**. 사용자가 "전반적으로 일관성 부족" 으로 진단한 부분과 일치.

## 2. 비목표 (Non-goals)

- 외부 API/동작 변경 없음 (모든 엔드포인트·페이로드·테스트 결과 동일)
- 성능 최적화 아님 (별 작업)
- 새 기능 추가 아님
- 아키텍처 결정 변경 없음 (BGE-M3 + ChromaDB + BM25 + Ollama 그대로)
- Docker 이미지/배포 흐름 영향 없음 (entry point 동일)

## 3. 스타일 헌법

모든 파일이 따르는 규약 6 항.

### 3.1 모듈 헤더 순서
```
1) imports
2) 이 모듈이 정의하는 타입 (frozen dataclass)
3) 순수 함수 (입력 → 출력, 부수효과 없음)
4) 부수효과 함수 (DB write / HTTP / 파일 IO) — 분명히 명시
```

### 3.2 데이터는 frozen dataclass
- dict 기반 객체 전부 명명된 `@dataclass(frozen=True)` 로
- 횡단 타입은 루트 `types.py` 1개 파일에 모음

### 3.3 동작은 모듈 함수
- 클래스 메서드 X. wrapper class X.
- 상태·연결을 첫 인자로 받음: `func(state, *, kwargs)`

### 3.4 wrapper 클래스 금지
- `sqlite3`, `SentenceTransformer`, `chromadb.Client` 등 외부 라이브러리는 그대로 사용
- 우리 코드가 또 한 겹 감싸지 않음

### 3.5 부수효과는 가장자리에만
- DB 쓰기·HTTP·파일 IO 는 `backend.py` 핸들러 / CLI 진입점에서만
- 핵심 로직 모듈은 순수 함수 위주

### 3.6 환경변수는 `config.py` 1회
- `os.environ` 직접 접근은 `config.py` 내부에서만
- 다른 모듈은 `AppConfig` (frozen dc) 를 인자로 받음

## 4. 파일 구조

### 4.1 신규 6개

| 경로 | 책임 |
|------|------|
| `config.py` | env 로딩 1회, `AppConfig` (frozen dc) 정의 |
| `types.py` | 횡단 데이터 타입: `Chunk`, `Source`, `Retrieval`, `ChatEvent` 등 |
| `ingest/pipeline.py` | `run_ingest(config) -> IngestResult` — 현재 cli.py 의 main() 로직 추출 |
| `index/vector_store.py` | Chroma 헬퍼 (`get_chroma_client`, `upsert_chunks`, `query_embed`) — 현 `embed.py` 에서 분리 |
| `retrieval/search.py` | `hybrid_search(state, query) -> Retrieval` — 현 `RagEngine.retrieve` 로직 |
| `rag/state.py` | `RagState` (frozen dc) + `load_rag_state(config) -> RagState` |

### 4.2 리네임 3개

| 변경 전 | 변경 후 | 이유 |
|---------|---------|------|
| `db/dao.py` | `db/store.py` | Database 클래스 제거 후 "DAO" 명칭 부정확. 모듈 함수 모음으로 의미 변경 |
| `index/bm25_index.py` | `index/bm25.py` | "_index" 접미 군더더기 |
| `generation/pipeline.py` | `generation/stream.py` | RagEngine 제거 후 남는 책임이 "응답 스트리밍" 이라 더 명확 |

### 4.3 클래스 3개 제거

| 클래스 | 새 형태 |
|--------|---------|
| `db.dao.Database` | `db/store.py` 의 모듈 함수: `init_schema`, `new_session`, `get_session`, `add_turn`, `add_feedback`, `feedback_for`, `purge_session`. 모두 `db_path: Path` 를 첫 인자로 받음 |
| `index.embed.Embedder` | `index/embed.py` 의 `load_embedder(model_name)` + `encode_texts(model, texts)` |
| `generation.pipeline.RagEngine` | `rag/state.py` 의 `RagState` (frozen dc: embedder, chroma, bm25, ollama_host, ollama_model) + 모듈 함수들 |

### 4.4 변경 없음 (이미 순수 함수)

`ingest/extract.py`, `ingest/preprocess.py`, `ingest/chunk.py`, `retrieval/hybrid.py`, `generation/persona.py`, `generation/filters.py`, `generation/guardrail.py`, `db/schema.py`

## 5. 횡단 타입 정의 (`types.py`)

```python
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
    section_path: tuple[str, ...] = ()       # list → tuple (frozen-friendly)
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
    url: str


@dataclass(frozen=True)
class Retrieval:
    chunks: tuple[Chunk, ...]
    top_score: Score


@dataclass(frozen=True)
class ChatEvent:
    """ /chat SSE 스트림에 흘려보내는 단위 이벤트.

    type 별 의미:
      - text: delta 가 채워짐 (스트리밍 토큰 일부, streaming_clean 만 적용)
      - text_final: text 가 채워짐 (스트림 종료 시 풀 클린업 결과로 교체)
      - done: images, sources, score 가 채워짐 (검색 메타데이터)
      - turn_id: turn_id 가 채워짐 (DB 저장 후 클라이언트가 피드백 호출에 사용)
    """
    type: Literal["text", "text_final", "done", "turn_id"]
    delta: str = ""
    text: str = ""
    images: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    score: Score = 0.0
    turn_id: int | None = None
```

## 6. RagState 정의 (`rag/state.py`)

```python
from dataclasses import dataclass

from chromadb.api import ClientAPI
from sentence_transformers import SentenceTransformer

from config import AppConfig
from index.bm25 import BM25Pack, load_bm25
from index.embed import load_embedder
from index.vector_store import get_chroma_client


@dataclass(frozen=True)
class RagState:
    embedder: SentenceTransformer
    chroma: ClientAPI
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

## 7. AppConfig 정의 (`config.py`)

```python
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

## 8. 핵심 함수 시그니처 (after)

```python
# db/store.py
def init_schema(db_path: Path) -> None
def new_session(db_path: Path, *, consent_version: str, user_label: str | None) -> str
def get_session(db_path: Path, session_id: str) -> dict | None
def add_turn(db_path: Path, *, session_id: str, query: str, response: str,
             retrieved_sources: list[Source], retrieved_score: float | None,
             latency_ms: int | None) -> int
def add_feedback(db_path: Path, *, turn_id: int, rating: int, comment: str | None) -> None
def feedback_for(db_path: Path, turn_id: int) -> list[dict]
def purge_session(db_path: Path, session_id: str) -> None

# index/embed.py
def load_embedder(model_name: str) -> SentenceTransformer
def encode_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]

# index/vector_store.py
def get_chroma_client(persist_dir: Path) -> ClientAPI
def upsert_chunks(client: ClientAPI, model: SentenceTransformer, chunks: list[Chunk]) -> None
def query_embed(client: ClientAPI, model: SentenceTransformer, query: str, k: int) -> list[tuple[ChunkId, Score]]

# index/bm25.py (변경 없음 — 이미 함수형)
def build_bm25(chunks: list[Chunk]) -> BM25Pack
def save_bm25(pack: BM25Pack, path: Path) -> None
def load_bm25(path: Path) -> BM25Pack
def query_bm25(pack: BM25Pack, query: str, k: int) -> list[tuple[ChunkId, Score]]

# retrieval/search.py
def hybrid_search(state: RagState, query: str, *, k: int = TOP_K) -> Retrieval

# generation/stream.py
async def stream_response(state: RagState, query: str) -> AsyncIterator[ChatEvent]

# ingest/pipeline.py
@dataclass(frozen=True)
class IngestResult:
    chunk_count: int
    image_count: int

def run_ingest(config: AppConfig) -> IngestResult
```

## 9. backend.py 슬림화

현재 145 LOC. 변경 후 약 100 LOC. 핸들러 안의 nonlocal 누적 + SSE serialize 가 별도 헬퍼로 분리.

```python
# backend.py 골자 (after)
from config import load_config
from db import store
from rag.state import load_rag_state
from generation.stream import stream_response

config = load_config()
store.init_schema(config.logs_db_path)
_state: RagState | None = None  # lifespan 에서 채움

@app.post("/chat")
async def chat(body: ChatBody):
    if not store.get_session(config.logs_db_path, body.session_id):
        raise HTTPException(403, "동의 후 사용 가능합니다")
    return StreamingResponse(
        _chat_sse(body),
        media_type="text/event-stream",
    )

async def _chat_sse(body: ChatBody):
    started = time.time()
    events: list[ChatEvent] = []
    async for evt in stream_response(_state, body.query):
        events.append(evt)
        yield _serialize_sse(evt)
    turn_id = _log_turn(body, events, started)
    yield _serialize_sse(ChatEvent(type="turn_id", ...))  # 또는 별도 dict
```

`_chat_sse` 안의 핵심 로직(누적·로깅)을 추출해 `_log_turn` 으로 분리. nonlocal 변수 사라짐.

## 10. 테스트 영향

```
tests/test_dao.py           → tests/test_store.py    (임포트 + API 호출 형식 변경)
tests/test_chunk.py         → 변경 X (Chunk dc 의 list→tuple 변경 따라 assert 만 조정)
tests/test_bm25_index.py    → tests/test_bm25.py     (임포트 경로만 변경)
tests/test_hybrid.py        → 변경 X
tests/test_filters.py       → 변경 X
tests/test_preprocess.py    → 변경 X
tests/test_guardrail.py     → 변경 X
tests/test_extract.py       → 변경 X
```

새 테스트 추가 가능 영역 (선택, 작업 범위 밖):
- `test_config.py` (env 디폴트 + override)
- `test_search.py` (hybrid_search 통합 테스트)
- `test_state.py` (load_rag_state mocking)

본 리팩터링에서는 **임포트 갱신만**. 신규 테스트 추가는 별도 작업.

## 11. 작업 순서 (개략)

writing-plans 단계에서 구체화하되 의존성 그래프상 다음 순서로 진행해야 함:

1. `types.py` + `config.py` 생성 (다른 모듈이 임포트할 토대)
2. `index/embed.py` 함수화 + `index/vector_store.py` 분리
3. `index/bm25_index.py` → `bm25.py` 리네임
4. `db/dao.py` → `db/store.py` 변환
5. `rag/state.py` 생성
6. `retrieval/search.py` 생성 (RagEngine.retrieve 로직 이식)
7. `generation/pipeline.py` → `generation/stream.py` 변환 (RagEngine.stream_chat 로직 이식)
8. `ingest/cli.py` → `ingest/pipeline.py` + 얇은 cli.py 로 분리
9. `backend.py` 새 모듈로 임포트 전환
10. 테스트 임포트 갱신 + 전체 통과 확인
11. 동작 확인 (ingest → 서버 부팅 → /chat 라이브 테스트)

각 단계는 독립 커밋 가능. 한 단계 끝낼 때마다 테스트 그린 유지.

## 12. 진행 중 위험·완화책

| 위험 | 완화 |
|------|------|
| 임포트 순환 (config → state → 모듈 → config) | config 는 무엇도 임포트하지 않음. types 도 무엇도 임포트하지 않음. 단방향 의존성 유지 |
| Chunk dc 가 frozen + tuple 로 바뀌면서 기존 코드의 `c.image_refs.append(...)` 등 깨짐 | grep 으로 모든 사용처 확인 후 list comprehension / `+` 연산자로 변경 |
| 테스트 임포트 깨짐 | 각 모듈 변환 직후 해당 테스트 즉시 갱신·통과 확인 |
| backend.py 의 lifespan/state 로딩 타이밍 변경 | 기존 startup hook 유지, 내부 `_state` 변수만 RagState 로 교체 |

## 13. 결정 사항 정리

- 방향: 실용 FP (Approach A) — frozen dc + 모듈 함수 + 단일 거대 상태(RagState) 만 객체로
- 클래스 제거: Database, Embedder, RagEngine
- 횡단 타입 모으기: `types.py`
- 환경변수 단일 진입점: `config.py`
- 신규 디렉터리: `rag/`
- 외부 동작·테스트 결과 100% 동일 유지
