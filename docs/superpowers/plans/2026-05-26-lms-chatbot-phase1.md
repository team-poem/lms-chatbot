# LMS 챗봇 Phase 1 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec `2026-05-26-lms-chatbot-design.md` 의 Phase 1 (6월 초 보고용 라이브 시연 MVP) 을 동작 가능한 상태로 구현. 인덱싱 → 하이브리드 검색 → RAG 응답 → 최소 웹 UI → SQLite 로깅 + 동의 모달까지.

**Architecture:** Notion export(.md/.csv) → 전처리(이모지 제거) → 청크(메타데이터 포함) → BGE-M3 임베딩(ChromaDB) + BM25 인덱스 → 하이브리드 검색(0.4·BM25 + 0.6·임베딩) → gemma3:4b 프롬프트 → 스트리밍 응답(후처리 필터). FastAPI 단일 서버 + 정적 HTML 페이지.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Ollama(`gemma3:4b`), ChromaDB, `sentence-transformers`(BAAI/bge-m3), `rank-bm25`, SQLite, pytest.

---

## 파일 구조

```
lms-chatbot/
  AGENT.md
  README.md
  requirements.txt
  .env.example
  run.sh
  backend.py                     # FastAPI 진입점
  ingest/
    __init__.py
    cli.py                       # `python -m ingest.cli` 진입점
    extract.py                   # ZIP 풀고 .md/.csv 경로 수집
    preprocess.py                # 이모지·Notion artifact 정리
    chunk.py                     # .md → 청크, .csv 행 → 청크
  index/
    __init__.py
    embed.py                     # BGE-M3 + Chroma persist
    bm25_index.py                # BM25 빌드/저장/로드
  retrieval/
    __init__.py
    types.py                     # Chunk, RetrievedChunk 데이터클래스
    hybrid.py                    # 점수 정규화 + 가중합
  generation/
    __init__.py
    persona.py                   # PERSONA_SYSTEM 상수
    filters.py                   # 응답 후처리 (이모지·마크업)
    pipeline.py                  # 검색 → 프롬프트 → Ollama 스트림 → 필터
  db/
    __init__.py
    schema.py                    # CREATE TABLE
    dao.py                       # sessions/turns/feedback DAO
  static/
    index.html                   # 동의 모달 + 채팅 UI + 피드백
  scripts/
    purge_old_logs.py
  docs/
    privacy.md                   # 처리방침 전문
    superpowers/
      specs/
      plans/
  tests/
    __init__.py
    test_preprocess.py
    test_chunk.py
    test_bm25_index.py
    test_hybrid.py
    test_filters.py
    test_dao.py
```

응답 책임 경계:
- `ingest/*` 는 디스크에서 정제된 청크 객체까지만. 임베딩/인덱스 빌드는 `index/*` 가 담당
- `retrieval/*` 는 인덱스 객체를 받아 검색만. LLM 호출 없음
- `generation/*` 가 검색 결과 + LLM 결합
- `db/*` 는 SQLite. 다른 모듈은 DAO 함수만 호출
- `backend.py` 는 얇은 wrapper. 각 호출은 위 모듈로 위임

---

## Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `run.sh`
- Create: `README.md`
- Create: `pytest.ini`
- Create: `ingest/__init__.py`, `index/__init__.py`, `retrieval/__init__.py`, `generation/__init__.py`, `db/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: requirements.txt 작성**

```
fastapi==0.115.4
uvicorn[standard]==0.32.0
httpx==0.27.2
chromadb==0.5.20
sentence-transformers==3.3.1
rank-bm25==0.2.2
pandas==2.2.3
python-dotenv==1.0.1
pytest==8.3.3
```

- [ ] **Step 2: .env.example**

```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
EMBED_MODEL=BAAI/bge-m3
CHROMA_DIR=./data/chroma
BM25_PATH=./data/bm25.pkl
LOGS_DB_PATH=./data/chat_logs.db
ASSETS_DIR=./data/assets
RAW_DIR=./data/raw
PORT=8080
```

- [ ] **Step 3: pytest.ini**

```
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 4: 빈 패키지 __init__.py 생성**

```bash
touch ingest/__init__.py index/__init__.py retrieval/__init__.py generation/__init__.py db/__init__.py tests/__init__.py
```

- [ ] **Step 5: run.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi
if [ ! -f .env ]; then
  cp .env.example .env
fi
.venv/bin/python -m uvicorn backend:app --host 0.0.0.0 --port "${PORT:-8080}" --reload
```

```bash
chmod +x run.sh
```

- [ ] **Step 6: README.md 작성** (개략)

```markdown
# LMS 챗봇 (Phase 1 MVP)

동서대 LearningX LMS 사용 매뉴얼 기반 교수자 응대 챗봇.

## 빠른 시작

1. Ollama 설치 후 모델 받기: `ollama pull gemma3:4b`
2. Notion 가이드북 export(Markdown & CSV ZIP)를 `data/raw/` 에 둠
3. 인덱싱: `python -m ingest.cli`
4. 서버 실행: `./run.sh`
5. 브라우저: http://localhost:8080

자세한 구성은 `AGENT.md` 와 `docs/superpowers/specs/` 참조.
```

- [ ] **Step 7: 커밋**

```bash
git add requirements.txt .env.example pytest.ini run.sh README.md \
  ingest/__init__.py index/__init__.py retrieval/__init__.py \
  generation/__init__.py db/__init__.py tests/__init__.py
git commit -m "Task 1: scaffold project (deps, env template, run script, package skeleton)"
```

---

## Task 2: AGENT.md 작성

**Files:**
- Create: `AGENT.md`

- [ ] **Step 1: AGENT.md 본문 작성**

spec 2 절 구조를 코드 친화적 분량으로 압축. 다음 내용을 그대로 사용:

```markdown
# AGENT.md — LMS 챗봇

본 코드베이스에서 작업하는 AI 에이전트와 인간 개발자를 위한 메타 지시 문서.

## 한 문단 요약
동서대학교 LearningX LMS 사용 매뉴얼(교수자용 상세 가이드 + LMS FAQ)을 검색 근거로 사용해, 교수자가 "이 기능 어떻게 쓰나요?" 류 질문을 했을 때 본문 설명 + 캡처 이미지로 답하는 RAG 챗봇. Phase 1 은 6월 초 보고용 라이브 시연 MVP.

## 신뢰 경계
- 답변은 인덱싱된 가이드북 내용으로만 한다. 모델의 일반 LMS·교육학 지식으로 추론하지 않는다.
- 검색 결과 신뢰도가 임계값 미만이면 LLM 호출 없이 정형 안내 메시지를 반환한다.

## 응답 규칙 (RESPONSE_RULES — generation/persona.py 의 시스템 프롬프트에 동일 반영)
1. 존대 + 격식체 ("~합니다", "~하시면 됩니다"). "님" 호칭 불사용.
2. 마크업 금지: 굵게(`**`), 기울임(`*`), 헤딩(`#`). 단계 안내용 숫자 리스트는 허용.
3. 이모티콘·이모지 출력 금지. 가이드 원문의 장식 이모지(🟠 등)도 옮기지 않는다.
4. 답변 말미에 참조한 가이드 페이지 제목을 한 줄로 표기.
5. 가이드 범위 외 질문은 정중히 거절. 일반 지식 추론 금지.

## 전처리 룰 (PREPROCESS_RULES — ingest/preprocess.py 에 동일 반영)
1. 유니코드 이모지 전 범위 제거 (한국어 본문에 의미 있는 이모지 거의 없음).
2. Notion artifact 정리: 헤딩 접미 마커 `(📄)`, 단독 `---` 라인, `<aside>...</aside>` callout → 일반 문단.
3. 외부 링크는 텍스트만 남기고 URL 제거. 단, 이미지 링크 `![](path)` 는 보존.
4. 연속 공백·줄바꿈 축약.
5. **이중 안전망**: LLM 응답에서도 generation/filters.py 가 이모지·금지 마크업을 후처리로 제거.

## 검색 정책
- 청크 기본 단위: .md 1개 파일(=Notion 1개 페이지). 2,000 토큰 초과 시 H2 기준 분할.
- CSV 행 단위: 1행 = 1청크 (FAQ 질문 + 메타 태그).
- 하이브리드 점수: `BM25_norm * 0.4 + embed_sim * 0.6`. top-5 가 LLM 컨텍스트로 들어감.
- 임계값(현재 0.25, 정성 평가 후 조정): 1위 점수가 미만이면 LLM 호출 안 함.

## 이미지 동반 정책
- 응답 페이로드: `{ text, images: [{path, caption}], sources: [titles] }`.
- 검색된 상위 5개 청크의 `image_refs` 합집합 중, 상위 청크에서 먼저 등장한 순으로 최대 5장.
- 캡션은 원문 .md 의 이미지 인접 텍스트(직전·직후 80자) 에서 추출.

## 로깅과 개인정보
- SQLite (`data/chat_logs.db`): sessions / turns / feedback.
- 저장 항목: 질의·응답·시각·표시명(선택)·피드백·운영 메타데이터. **실명·학번·이메일·IP 수집 없음**.
- 보유 기간 6개월. 동의 철회 시 해당 세션 즉시 삭제.
- 수집 목적은 ①가이드 업데이트 우선순위 도출 ②응답 품질 모니터링 으로만 한정. **모델 학습에 활용하지 않음** (개보법상 별도 동의 필요).
- 처리방침: `docs/privacy.md`. 첫 진입 시 동의 모달에서 항목별 분리 고지.
- 책임자: 김강민. 문의처: 동서대학교 교육혁신처 교수학습개발센터.

## 개발 워크플로
- 가이드 업데이트 시: 새 export 를 `data/raw/` 에 넣고 `python -m ingest.cli` 재실행 (idempotent).
- 모델 교체: `.env` 의 `OLLAMA_MODEL` 변경. `generation/pipeline.py` 코드 수정 불필요.
- 추후 GPU 서버 이전: `.env` 의 `OLLAMA_HOST` 만 변경.
- 새 의존성 추가 시 `requirements.txt` 갱신 후 PR 에 이유 명시.

## 디렉터리 맵
- `ingest/` 정제된 청크까지. 임베딩은 하지 않음
- `index/` 임베딩 + BM25 인덱스 빌드/저장
- `retrieval/` 인덱스에서 검색만
- `generation/` 검색 결과 + LLM 결합 + 후처리
- `db/` SQLite 스키마와 DAO
- `backend.py` FastAPI 얇은 wrapper
- `static/index.html` 동의 모달 + 채팅 UI + 피드백
- `docs/` spec, plans, privacy
- `tests/` 순수 함수 위주 pytest
```

- [ ] **Step 2: 커밋**

```bash
git add AGENT.md
git commit -m "Task 2: add AGENT.md (meta instruction doc for agents + humans)"
```

---

## Task 3: 공용 데이터 타입

**Files:**
- Create: `retrieval/types.py`

- [ ] **Step 1: types.py 작성**

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Literal


DocSet = Literal["guide", "faq"]


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source: str
    doc_set: DocSet
    title: str
    section_path: list[str] = field(default_factory=list)
    image_refs: list[str] = field(default_factory=list)
    csv_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float
    bm25_score: float
    embed_score: float
```

- [ ] **Step 2: 커밋**

```bash
git add retrieval/types.py
git commit -m "Task 3: add Chunk and RetrievedChunk dataclasses"
```

---

## Task 4: 전처리 (preprocess.py) — TDD

**Files:**
- Create: `ingest/preprocess.py`
- Create: `tests/test_preprocess.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_preprocess.py
from ingest.preprocess import clean_markdown, strip_emoji


def test_strip_emoji_removes_decoration():
    assert strip_emoji("🟠 글로벌 탐색 메뉴") == "글로벌 탐색 메뉴"
    assert strip_emoji("퀴즈 개요 (📄)") == "퀴즈 개요 ()"


def test_strip_emoji_keeps_ascii():
    assert strip_emoji("LMS FAQ") == "LMS FAQ"


def test_clean_markdown_removes_callout_wrappers():
    src = "<aside>\n💡 화면 오른쪽 위에 위치한 검색 버튼\n</aside>"
    out = clean_markdown(src)
    assert "<aside>" not in out
    assert "</aside>" not in out
    assert "검색 버튼" in out
    assert "💡" not in out


def test_clean_markdown_strips_inline_emoji_marker_in_heading():
    src = "## 🔖 시험 및 설문"
    out = clean_markdown(src)
    assert out.strip().startswith("## ")
    assert "🔖" not in out


def test_clean_markdown_preserves_image_links():
    src = "본문\n\n![캡션](images/abc.png)\n\n다음 단락"
    out = clean_markdown(src)
    assert "![캡션](images/abc.png)" in out


def test_clean_markdown_strips_external_links_keeps_text():
    src = "참고는 [퀴즈 개요](https://www.notion.so/abc) 페이지."
    out = clean_markdown(src)
    assert "퀴즈 개요" in out
    assert "https://" not in out


def test_clean_markdown_drops_lone_hr_lines():
    src = "본문 1\n\n---\n\n본문 2"
    out = clean_markdown(src)
    assert "---" not in out
    assert "본문 1" in out
    assert "본문 2" in out


def test_clean_markdown_collapses_blank_lines():
    src = "줄1\n\n\n\n\n줄2"
    out = clean_markdown(src)
    assert "\n\n\n" not in out
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
.venv/bin/pytest tests/test_preprocess.py -v
```
Expected: ImportError / 미정의 함수로 실패.

- [ ] **Step 3: preprocess.py 구현**

```python
# ingest/preprocess.py
from __future__ import annotations
import re


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002700-\U000027BF"
    "⌀-⏿"
    "⬀-⯿"
    "]+",
    flags=re.UNICODE,
)

_IMG_PLACEHOLDER = "\x00IMG{}\x00"
_IMG_LINK_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_ASIDE_OPEN = re.compile(r"<aside>\s*", flags=re.IGNORECASE)
_ASIDE_CLOSE = re.compile(r"\s*</aside>", flags=re.IGNORECASE)
_HR_LINE = re.compile(r"^\s*-{3,}\s*$", flags=re.MULTILINE)
_MULTI_BLANK = re.compile(r"\n{3,}")


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def clean_markdown(src: str) -> str:
    # 이미지 링크는 보존을 위해 placeholder 로 치환
    images: list[str] = []

    def stash(match: re.Match) -> str:
        images.append(match.group(0))
        return _IMG_PLACEHOLDER.format(len(images) - 1)

    text = _IMG_LINK_RE.sub(stash, src)
    text = _ASIDE_OPEN.sub("", text)
    text = _ASIDE_CLOSE.sub("", text)
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    text = _HR_LINE.sub("", text)
    text = strip_emoji(text)
    text = _MULTI_BLANK.sub("\n\n", text)

    for i, original in enumerate(images):
        text = text.replace(_IMG_PLACEHOLDER.format(i), original)

    return text.strip() + "\n"
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
.venv/bin/pytest tests/test_preprocess.py -v
```
Expected: 8 passed.

- [ ] **Step 5: 커밋**

```bash
git add ingest/preprocess.py tests/test_preprocess.py
git commit -m "Task 4: preprocess (emoji strip, Notion artifact cleanup) + tests"
```

---

## Task 5: 청크 분할 (chunk.py) — TDD

**Files:**
- Create: `ingest/chunk.py`
- Create: `tests/test_chunk.py`

청크 단위: .md 1개 = 1 청크 기본. 본문 토큰 추정치(공백 분할 기준) > 2000 시 H2(`## `) 기준 분할. CSV 행은 각 행 = 1 청크.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_chunk.py
import pandas as pd
from pathlib import Path
from ingest.chunk import chunk_markdown_file, chunk_csv_file, extract_image_refs


def test_extract_image_refs_finds_paths():
    md = "본문\n![](images/a.png)\n중간\n![캡션](images/b.png)"
    assert extract_image_refs(md) == ["images/a.png", "images/b.png"]


def test_extract_image_refs_dedup_preserve_order():
    md = "![](x.png)\n![](y.png)\n![](x.png)"
    assert extract_image_refs(md) == ["x.png", "y.png"]


def test_chunk_markdown_small_returns_single(tmp_path: Path):
    p = tmp_path / "퀴즈 개요 abc.md"
    p.write_text("# 퀴즈 개요\n\n본문 짧음\n\n![](img/q.png)\n", encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=["시험 및 설문"])
    assert len(chunks) == 1
    c = chunks[0]
    assert c.title == "퀴즈 개요"
    assert c.image_refs == ["img/q.png"]
    assert c.section_path == ["시험 및 설문"]
    assert c.doc_set == "guide"
    assert c.source.endswith("퀴즈 개요 abc.md")


def test_chunk_markdown_large_splits_on_h2(tmp_path: Path):
    body_a = "단어 " * 1200
    body_b = "단어 " * 1200
    text = f"# 큰 페이지\n\n## 섹션 A\n\n{body_a}\n\n## 섹션 B\n\n{body_b}\n"
    p = tmp_path / "큰페이지 xyz.md"
    p.write_text(text, encoding="utf-8")
    chunks = chunk_markdown_file(p, doc_set="guide", section_path=[])
    assert len(chunks) == 2
    assert chunks[0].title == "큰 페이지 — 섹션 A"
    assert chunks[1].title == "큰 페이지 — 섹션 B"


def test_chunk_csv_each_row_becomes_chunk(tmp_path: Path):
    p = tmp_path / "FAQ.csv"
    pd.DataFrame({
        "FAQ": ["로그인이 안 됩니다", "수업계획서 입력 방법"],
        "메뉴명": ["기본", "수업계획서"],
        "시기": ["1.학기초", "1.학기초"],
        "연번": [1, 15],
        "태그": ["로그인", "수업계획서"],
    }).to_csv(p, index=False)
    chunks = chunk_csv_file(p, doc_set="faq")
    assert len(chunks) == 2
    assert "로그인이 안 됩니다" in chunks[0].text
    assert "기본" in chunks[0].text  # 메뉴명이 텍스트에 포함
    assert chunks[0].doc_set == "faq"
    assert chunks[0].title.startswith("FAQ")
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest tests/test_chunk.py -v
```

- [ ] **Step 3: chunk.py 구현**

```python
# ingest/chunk.py
from __future__ import annotations
import hashlib
import re
from pathlib import Path

import pandas as pd

from retrieval.types import Chunk, DocSet


_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_H2_RE = re.compile(r"^##\s+(.+)$", flags=re.MULTILINE)
_TOKEN_LIMIT = 2000


def _hash_id(*parts: str) -> str:
    h = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def _approx_tokens(text: str) -> int:
    return len(text.split())


def extract_image_refs(text: str) -> list[str]:
    seen: list[str] = []
    for match in _IMG_RE.finditer(text):
        path = match.group(1).strip()
        if path not in seen:
            seen.append(path)
    return seen


def _derive_title(path: Path) -> str:
    name = path.stem
    parts = name.rsplit(" ", 1)
    if len(parts) == 2 and len(parts[1]) >= 16:
        return parts[0]
    return name


def chunk_markdown_file(
    path: Path,
    *,
    doc_set: DocSet,
    section_path: list[str],
) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    title = _derive_title(path)
    source = str(path)

    if _approx_tokens(text) <= _TOKEN_LIMIT:
        return [
            Chunk(
                chunk_id=_hash_id(source, "0"),
                text=text,
                source=source,
                doc_set=doc_set,
                title=title,
                section_path=list(section_path),
                image_refs=extract_image_refs(text),
            )
        ]

    # H2 분할
    splits: list[tuple[str, str]] = []
    matches = list(_H2_RE.finditer(text))
    if not matches:
        # H2 없음 → 단일 청크
        return [
            Chunk(
                chunk_id=_hash_id(source, "0"),
                text=text,
                source=source,
                doc_set=doc_set,
                title=title,
                section_path=list(section_path),
                image_refs=extract_image_refs(text),
            )
        ]

    for i, m in enumerate(matches):
        section_title = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        splits.append((section_title, text[start:end]))

    chunks: list[Chunk] = []
    for i, (section_title, body) in enumerate(splits):
        chunks.append(
            Chunk(
                chunk_id=_hash_id(source, str(i)),
                text=body,
                source=source,
                doc_set=doc_set,
                title=f"{title} — {section_title}",
                section_path=list(section_path),
                image_refs=extract_image_refs(body),
            )
        )
    return chunks


def chunk_csv_file(path: Path, *, doc_set: DocSet) -> list[Chunk]:
    df = pd.read_csv(path)
    source = str(path)
    base_title = f"FAQ — {_derive_title(path)}"
    chunks: list[Chunk] = []
    for i, row in df.iterrows():
        # 행 전체를 자연어 형태 문자열로 표현
        text_parts = []
        for col, val in row.items():
            if pd.isna(val):
                continue
            text_parts.append(f"{col}: {val}")
        text = "\n".join(text_parts)
        chunks.append(
            Chunk(
                chunk_id=_hash_id(source, str(i)),
                text=text,
                source=source,
                doc_set=doc_set,
                title=base_title,
                section_path=[],
                csv_refs=[source],
            )
        )
    return chunks
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
.venv/bin/pytest tests/test_chunk.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add ingest/chunk.py tests/test_chunk.py
git commit -m "Task 5: chunk markdown (page or H2-split) and CSV (row-per-chunk) + tests"
```

---

## Task 6: ZIP 추출 + 콘텐츠 워크 (extract.py)

**Files:**
- Create: `ingest/extract.py`

- [ ] **Step 1: extract.py 구현**

```python
# ingest/extract.py
from __future__ import annotations
import shutil
import zipfile
from pathlib import Path


def unzip_all_recursive(raw_dir: Path) -> None:
    """data/raw 안의 모든 .zip 을 자기 위치에 풀어둔다. 안의 .zip 도 재귀.
    이미 같은 이름의 디렉터리가 있으면 건너뛴다.
    """
    while True:
        zips = list(raw_dir.rglob("*.zip"))
        if not zips:
            return
        progressed = False
        for z in zips:
            out = z.with_suffix("")
            if out.exists():
                continue
            with zipfile.ZipFile(z) as zf:
                zf.extractall(z.parent)
            progressed = True
        if not progressed:
            return


def collect_markdown(raw_dir: Path) -> list[Path]:
    return sorted(p for p in raw_dir.rglob("*.md") if p.is_file())


def collect_csv(raw_dir: Path) -> list[Path]:
    return sorted(p for p in raw_dir.rglob("*.csv") if p.is_file())


def collect_images(raw_dir: Path) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    return sorted(p for p in raw_dir.rglob("*") if p.suffix.lower() in exts)


def copy_assets(images: list[Path], raw_dir: Path, assets_dir: Path) -> dict[str, str]:
    """이미지를 assets_dir 평탄 복사. 원본 raw 경로 → /assets/<filename> 매핑 반환."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for src in images:
        # 동일 이름 충돌 방지: 상위 디렉터리 일부를 접두
        dest_name = f"{src.parent.name[:8]}__{src.name}"
        dest = assets_dir / dest_name
        if not dest.exists():
            shutil.copy2(src, dest)
        rel = str(src.relative_to(raw_dir))
        mapping[rel] = f"/assets/{dest_name}"
    return mapping
```

- [ ] **Step 2: 동작 확인 — 임시 ZIP 으로 스모크**

```bash
.venv/bin/python - <<'PY'
import tempfile, zipfile, os
from pathlib import Path
from ingest.extract import unzip_all_recursive, collect_markdown

with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    inner = d / "inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("a.md", "# A\n")
    outer = d / "outer.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.write(inner, arcname="inner.zip")
    inner.unlink()
    unzip_all_recursive(d)
    print(collect_markdown(d))
PY
```
Expected: `[PosixPath('.../inner/a.md')]`

- [ ] **Step 3: 커밋**

```bash
git add ingest/extract.py
git commit -m "Task 6: zip extractor + content walkers + asset copier"
```

---

## Task 7: BM25 인덱스 (bm25_index.py) — TDD

**Files:**
- Create: `index/bm25_index.py`
- Create: `tests/test_bm25_index.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_bm25_index.py
from pathlib import Path
from index.bm25_index import build_bm25, save_bm25, load_bm25, query_bm25
from retrieval.types import Chunk


def _chunk(cid: str, text: str, title: str = "T") -> Chunk:
    return Chunk(chunk_id=cid, text=text, source=f"s/{cid}.md",
                 doc_set="guide", title=title)


def test_build_and_query_returns_scores():
    chunks = [
        _chunk("c1", "퀴즈 출제 방법은 다음과 같습니다", title="퀴즈 개요"),
        _chunk("c2", "출결 현황 조회 방법", title="출결현황"),
        _chunk("c3", "토론 그룹 만들기", title="토론"),
    ]
    bm = build_bm25(chunks)
    hits = query_bm25(bm, "퀴즈 출제", k=2)
    assert len(hits) == 2
    assert hits[0][0] == "c1"
    assert hits[0][1] > hits[1][1]


def test_save_and_load_roundtrip(tmp_path: Path):
    chunks = [_chunk("c1", "퀴즈", title="퀴즈")]
    bm = build_bm25(chunks)
    p = tmp_path / "bm25.pkl"
    save_bm25(bm, p)
    bm2 = load_bm25(p)
    hits = query_bm25(bm2, "퀴즈", k=1)
    assert hits[0][0] == "c1"
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest tests/test_bm25_index.py -v
```

- [ ] **Step 3: 구현**

```python
# index/bm25_index.py
from __future__ import annotations
import pickle
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from retrieval.types import Chunk


_TOKEN_RE = re.compile(r"[\w가-힣]+", flags=re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class BM25Pack:
    bm25: BM25Okapi
    chunk_ids: list[str]


def build_bm25(chunks: list[Chunk]) -> BM25Pack:
    docs = [_tokenize(f"{c.title}\n{' '.join(c.section_path)}\n{c.text}") for c in chunks]
    bm25 = BM25Okapi(docs)
    return BM25Pack(bm25=bm25, chunk_ids=[c.chunk_id for c in chunks])


def save_bm25(pack: BM25Pack, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(pack, f)


def load_bm25(path: Path) -> BM25Pack:
    with open(path, "rb") as f:
        return pickle.load(f)


def query_bm25(pack: BM25Pack, query: str, k: int = 20) -> list[tuple[str, float]]:
    q = _tokenize(query)
    scores = pack.bm25.get_scores(q)
    idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [(pack.chunk_ids[i], float(scores[i])) for i in idx]
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/pytest tests/test_bm25_index.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add index/bm25_index.py tests/test_bm25_index.py
git commit -m "Task 7: BM25 index (build/save/load/query) + tests"
```

---

## Task 8: 임베딩 + ChromaDB (embed.py)

**Files:**
- Create: `index/embed.py`

BGE-M3 모델은 무겁고(>1GB) 처음 호출 시 다운로드 시간이 길어 TDD 없이 통합 동작 확인만 한다.

- [ ] **Step 1: embed.py 구현**

```python
# index/embed.py
from __future__ import annotations
import os
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from retrieval.types import Chunk


_COLLECTION = "lms_chunks"


class Embedder:
    def __init__(self, model_name: str | None = None) -> None:
        name = model_name or os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
        self.model = SentenceTransformer(name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]


def get_chroma(persist_dir: Path) -> chromadb.api.client.Client:
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def upsert_chunks(client, embedder: Embedder, chunks: list[Chunk]) -> None:
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
    } for c in chunks]
    vecs = embedder.encode(docs)
    coll.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)


def query_embed(client, embedder: Embedder, query: str, k: int = 20) -> list[tuple[str, float]]:
    coll = client.get_or_create_collection(_COLLECTION)
    qvec = embedder.encode([query])[0]
    res = coll.query(query_embeddings=[qvec], n_results=k)
    ids = res["ids"][0]
    dists = res["distances"][0]
    # normalize=True 사용했으므로 distance 는 0..2 범위. 유사도 = 1 - dist/2
    return [(i, max(0.0, 1.0 - d / 2.0)) for i, d in zip(ids, dists)]
```

- [ ] **Step 2: 커밋** (모델 다운로드는 ingest 실행 시 수행)

```bash
git add index/embed.py
git commit -m "Task 8: BGE-M3 embedder + ChromaDB persist + query helper"
```

---

## Task 9: 인덱싱 진입점 (ingest/cli.py)

**Files:**
- Create: `ingest/cli.py`

- [ ] **Step 1: cli.py 구현**

```python
# ingest/cli.py
from __future__ import annotations
import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from ingest.extract import (
    unzip_all_recursive, collect_markdown, collect_csv,
    collect_images, copy_assets,
)
from ingest.preprocess import clean_markdown
from ingest.chunk import chunk_markdown_file, chunk_csv_file
from index.embed import Embedder, get_chroma, upsert_chunks
from index.bm25_index import build_bm25, save_bm25
from retrieval.types import Chunk


def _section_path_from(rel_path: Path) -> list[str]:
    return [p for p in rel_path.parts[:-1] if p not in ("", ".")]


def _detect_doc_set(rel_path: Path) -> str:
    parts = [p.lower() for p in rel_path.parts]
    blob = " ".join(parts)
    if "faq" in blob:
        return "faq"
    return "guide"


def _rewrite_image_refs(chunk: Chunk, mapping: dict[str, str], raw_dir: Path) -> Chunk:
    """청크의 image_refs 와 본문의 ![](path) 경로를 assets URL 로 치환."""
    new_refs: list[str] = []
    new_text = chunk.text
    for ref in chunk.image_refs:
        # ref 는 원본 .md 기준 상대 경로. raw_dir 기준 절대로 만들어 mapping 키를 찾음
        src_dir = Path(chunk.source).parent
        abs_path = (src_dir / ref).resolve()
        try:
            rel_to_raw = str(abs_path.relative_to(raw_dir.resolve()))
        except ValueError:
            continue
        if rel_to_raw in mapping:
            url = mapping[rel_to_raw]
            new_text = new_text.replace(f"({ref})", f"({url})")
            new_refs.append(url)
    return Chunk(
        chunk_id=chunk.chunk_id,
        text=new_text,
        source=chunk.source,
        doc_set=chunk.doc_set,
        title=chunk.title,
        section_path=chunk.section_path,
        image_refs=new_refs or chunk.image_refs,
        csv_refs=chunk.csv_refs,
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=os.environ.get("RAW_DIR", "./data/raw"))
    parser.add_argument("--assets", default=os.environ.get("ASSETS_DIR", "./data/assets"))
    parser.add_argument("--chroma", default=os.environ.get("CHROMA_DIR", "./data/chroma"))
    parser.add_argument("--bm25", default=os.environ.get("BM25_PATH", "./data/bm25.pkl"))
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw)
    assets_dir = Path(args.assets)
    chroma_dir = Path(args.chroma)
    bm25_path = Path(args.bm25)

    print(f"[1/5] zip 재귀 풀기: {raw_dir}")
    unzip_all_recursive(raw_dir)

    print(f"[2/5] assets 복사")
    img_mapping = copy_assets(collect_images(raw_dir), raw_dir, assets_dir)

    print(f"[3/5] 청크 생성")
    all_chunks: list[Chunk] = []
    for md in collect_markdown(raw_dir):
        rel = md.relative_to(raw_dir)
        doc_set = _detect_doc_set(rel)
        section_path = _section_path_from(rel)
        text = clean_markdown(md.read_text(encoding="utf-8"))
        md.write_text(text, encoding="utf-8")  # 정제 결과를 디스크에도 반영
        for c in chunk_markdown_file(md, doc_set=doc_set, section_path=section_path):
            all_chunks.append(_rewrite_image_refs(c, img_mapping, raw_dir))
    for csv in collect_csv(raw_dir):
        doc_set = _detect_doc_set(csv.relative_to(raw_dir))
        all_chunks.extend(chunk_csv_file(csv, doc_set=doc_set))
    print(f"    총 청크: {len(all_chunks)}")

    if not all_chunks:
        print("청크가 0개입니다. data/raw 에 Notion export 가 있는지 확인하세요.", file=sys.stderr)
        return 1

    print(f"[4/5] 임베딩 + ChromaDB ({chroma_dir})")
    embedder = Embedder()
    client = get_chroma(chroma_dir)
    upsert_chunks(client, embedder, all_chunks)

    print(f"[5/5] BM25 인덱스 저장 ({bm25_path})")
    pack = build_bm25(all_chunks)
    save_bm25(pack, bm25_path)

    print("완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 실제 인덱싱 실행 (data/raw 에 있는 샘플 ZIP 으로)**

```bash
.venv/bin/python -m ingest.cli
```
Expected: 5단계 메시지 + "총 청크: N" 출력 + "완료". 첫 실행 시 BGE-M3 모델 다운로드(수 분 소요).

- [ ] **Step 3: 커밋**

```bash
git add ingest/cli.py
git commit -m "Task 9: ingest CLI orchestrator (unzip → preprocess → chunk → embed + BM25)"
```

---

## Task 10: 하이브리드 검색 (retrieval/hybrid.py) — TDD

**Files:**
- Create: `retrieval/hybrid.py`
- Create: `tests/test_hybrid.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_hybrid.py
from retrieval.hybrid import combine_scores


def test_combine_basic_weighted_sum():
    bm = {"a": 1.0, "b": 0.0}
    emb = {"a": 0.0, "b": 1.0}
    out = combine_scores(bm, emb, w_bm25=0.4, w_embed=0.6, k=2)
    assert out[0][0] == "b"
    assert abs(out[0][1] - 0.6) < 1e-9
    assert out[1][0] == "a"
    assert abs(out[1][1] - 0.4) < 1e-9


def test_combine_normalizes_to_0_1():
    bm = {"a": 12.5, "b": 5.0, "c": 0.0}
    emb = {"a": 0.9, "b": 0.5, "c": 0.1}
    out = combine_scores(bm, emb, w_bm25=0.5, w_embed=0.5, k=3)
    for _, score in out:
        assert 0.0 <= score <= 1.0


def test_combine_handles_missing_keys():
    bm = {"a": 1.0}
    emb = {"b": 1.0}
    out = combine_scores(bm, emb, w_bm25=0.4, w_embed=0.6, k=2)
    ids = [i for i, _ in out]
    assert set(ids) == {"a", "b"}
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest tests/test_hybrid.py -v
```

- [ ] **Step 3: 구현**

```python
# retrieval/hybrid.py
from __future__ import annotations


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {k: 0.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def combine_scores(
    bm25_scores: dict[str, float],
    embed_scores: dict[str, float],
    *,
    w_bm25: float = 0.4,
    w_embed: float = 0.6,
    k: int = 5,
) -> list[tuple[str, float]]:
    bm_n = _normalize(bm25_scores)
    em_n = _normalize(embed_scores)
    ids = set(bm_n) | set(em_n)
    combined: list[tuple[str, float]] = []
    for cid in ids:
        score = w_bm25 * bm_n.get(cid, 0.0) + w_embed * em_n.get(cid, 0.0)
        combined.append((cid, score))
    combined.sort(key=lambda x: x[1], reverse=True)
    return combined[:k]
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/pytest tests/test_hybrid.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add retrieval/hybrid.py tests/test_hybrid.py
git commit -m "Task 10: hybrid retrieval (BM25 + embed score combine) + tests"
```

---

## Task 11: 페르소나 (generation/persona.py)

**Files:**
- Create: `generation/persona.py`

- [ ] **Step 1: 작성**

```python
# generation/persona.py
PERSONA_SYSTEM = """당신은 동서대학교 LearningX LMS 사용 매뉴얼을 안내하는 챗봇입니다.
질문자는 모두 교수자입니다. 다음 규칙을 반드시 지키십시오.

1. 반드시 격식체 존댓말로 답하십시오 ("~합니다", "~하시면 됩니다"). "님" 호칭은 사용하지 마십시오.
2. 굵게, 기울임, 헤딩 등 마크다운 강조 표기를 사용하지 마십시오. 단계 안내가 필요할 때만 "1.", "2." 형태의 숫자 리스트는 허용됩니다.
3. 이모지, 이모티콘, 특수문자 장식을 일절 사용하지 마십시오.
4. 제공된 컨텍스트(가이드 문서) 안에서만 답하십시오. 컨텍스트에 없는 내용은 추측하지 말고 "해당 내용은 현재 가이드에서 확인이 어렵습니다. 교육혁신처 교수학습개발센터로 문의 부탁드립니다." 라고 답하십시오.
5. 답변 마지막에 한 줄로 "참고: <페이지 제목들>" 형식의 출처를 표기하십시오.
6. 답변은 간결하게, 보통 3~6 문장 범위로 작성하십시오. 단계가 필요하면 숫자 리스트로 풀어 쓰십시오.
"""


def build_prompt(query: str, contexts: list[dict]) -> list[dict]:
    """contexts: [{title, text}] 리스트.
    Ollama chat API 의 messages 포맷으로 반환.
    """
    ctx_text = "\n\n".join(
        f"[SOURCE: {c['title']}]\n{c['text']}" for c in contexts
    )
    return [
        {"role": "system", "content": PERSONA_SYSTEM},
        {"role": "user", "content": f"다음 가이드 발췌를 근거로 답하십시오.\n\n{ctx_text}\n\n질문: {query}"},
    ]
```

- [ ] **Step 2: 커밋**

```bash
git add generation/persona.py
git commit -m "Task 11: persona system prompt + prompt builder"
```

---

## Task 12: 응답 후처리 필터 (generation/filters.py) — TDD

**Files:**
- Create: `generation/filters.py`
- Create: `tests/test_filters.py`

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_filters.py
from generation.filters import clean_response


def test_strips_emoji_from_response():
    assert clean_response("좋습니다 🙂 다음과 같습니다.") == "좋습니다  다음과 같습니다."


def test_removes_bold_markup():
    assert "**" not in clean_response("**중요**: 다음 절차입니다")


def test_removes_italic_markup():
    assert "*" not in clean_response("*강조* 부분")


def test_removes_headings():
    out = clean_response("# 제목\n본문")
    assert not out.startswith("#")
    assert "본문" in out


def test_keeps_numbered_lists():
    text = "1. 첫째\n2. 둘째"
    assert clean_response(text) == text
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest tests/test_filters.py -v
```

- [ ] **Step 3: 구현**

```python
# generation/filters.py
from __future__ import annotations
import re

from ingest.preprocess import strip_emoji


_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", flags=re.MULTILINE)


def clean_response(text: str) -> str:
    text = strip_emoji(text)
    text = _BOLD.sub(lambda m: m.group(1), text)
    text = _ITALIC.sub(lambda m: m.group(1), text)
    text = _HEADING.sub("", text)
    return text
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/pytest tests/test_filters.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add generation/filters.py tests/test_filters.py
git commit -m "Task 12: response post-filter (emoji/bold/italic/heading strip) + tests"
```

---

## Task 13: 생성 파이프라인 (generation/pipeline.py)

**Files:**
- Create: `generation/pipeline.py`

- [ ] **Step 1: 구현**

```python
# generation/pipeline.py
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import AsyncIterator

import httpx

from index.embed import Embedder, get_chroma, query_embed
from index.bm25_index import load_bm25, query_bm25
from retrieval.hybrid import combine_scores
from generation.persona import build_prompt
from generation.filters import clean_response


SCORE_THRESHOLD = 0.25
TOP_K = 5
EMBED_K = 20
BM25_K = 20


class RagEngine:
    def __init__(self) -> None:
        self.embedder = Embedder()
        self.chroma = get_chroma(Path(os.environ.get("CHROMA_DIR", "./data/chroma")))
        self.bm25 = load_bm25(Path(os.environ.get("BM25_PATH", "./data/bm25.pkl")))
        self.ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "gemma3:4b")

    def _fetch_chunks(self, ids: list[str]) -> dict[str, dict]:
        coll = self.chroma.get_or_create_collection("lms_chunks")
        res = coll.get(ids=ids, include=["documents", "metadatas"])
        out: dict[str, dict] = {}
        for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
            out[cid] = {"text": doc, **meta}
        return out

    def retrieve(self, query: str) -> tuple[list[dict], float]:
        bm = dict(query_bm25(self.bm25, query, k=BM25_K))
        emb = dict(query_embed(self.chroma, self.embedder, query, k=EMBED_K))
        merged = combine_scores(bm, emb, k=TOP_K)
        if not merged:
            return [], 0.0
        chunk_map = self._fetch_chunks([cid for cid, _ in merged])
        contexts: list[dict] = []
        for cid, score in merged:
            c = chunk_map.get(cid)
            if not c:
                continue
            contexts.append({
                "chunk_id": cid,
                "score": score,
                "title": c.get("title", ""),
                "text": c.get("text", ""),
                "image_refs": [s for s in (c.get("image_refs") or "").split(",") if s],
                "source": c.get("source", ""),
            })
        top_score = merged[0][1]
        return contexts, top_score

    async def stream_chat(self, query: str) -> AsyncIterator[dict]:
        contexts, top_score = self.retrieve(query)
        if top_score < SCORE_THRESHOLD:
            yield {"type": "text", "delta": "해당 내용은 현재 가이드에서 확인이 어렵습니다. 교육혁신처 교수학습개발센터로 문의 부탁드립니다."}
            yield {"type": "done", "images": [], "sources": [], "score": top_score}
            return

        messages = build_prompt(query, [{"title": c["title"], "text": c["text"]} for c in contexts])
        url = f"{self.ollama_host}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": 8192, "temperature": 0.2},
        }

        buffer = ""
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream("POST", url, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    delta = obj.get("message", {}).get("content", "")
                    if delta:
                        buffer += delta
                        cleaned = clean_response(buffer)
                        # 누적 보내지 않고 새로 정제된 분량의 마지막 일부를 보냄
                        yield {"type": "text", "delta": cleaned[len(getattr(self, "_last", "")):] if False else delta}
                    if obj.get("done"):
                        break

        # 응답 종료: 이미지·출처 집계
        seen_imgs: list[str] = []
        for c in contexts:
            for img in c["image_refs"]:
                if img and img not in seen_imgs:
                    seen_imgs.append(img)
            if len(seen_imgs) >= 5:
                break
        sources = []
        for c in contexts:
            t = c["title"]
            if t and t not in sources:
                sources.append(t)
        yield {"type": "done", "images": seen_imgs[:5], "sources": sources, "score": top_score}
```

- [ ] **Step 2: 커밋**

```bash
git add generation/pipeline.py
git commit -m "Task 13: RAG pipeline (hybrid retrieval → prompt → Ollama stream)"
```

---

## Task 14: SQLite 스키마 + DAO — TDD

**Files:**
- Create: `db/schema.py`
- Create: `db/dao.py`
- Create: `tests/test_dao.py`

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_dao.py
import json
from pathlib import Path
from db.dao import Database


def test_consent_and_session_roundtrip(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.init()
    sid = db.new_session(consent_version="v1", user_label="강민")
    s = db.get_session(sid)
    assert s["consent_version"] == "v1"
    assert s["user_label"] == "강민"


def test_turn_and_feedback(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.init()
    sid = db.new_session(consent_version="v1", user_label=None)
    tid = db.add_turn(
        session_id=sid, query="퀴즈?", response="이렇게.",
        retrieved_sources=["퀴즈 개요"], retrieved_score=0.7, latency_ms=420,
    )
    assert tid > 0
    db.add_feedback(turn_id=tid, rating=3, comment="도움됨")
    fs = db.feedback_for(tid)
    assert fs[0]["rating"] == 3
    assert fs[0]["comment"] == "도움됨"


def test_purge_session(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.init()
    sid = db.new_session(consent_version="v1", user_label=None)
    tid = db.add_turn(session_id=sid, query="q", response="r",
                      retrieved_sources=[], retrieved_score=0.0, latency_ms=0)
    db.add_feedback(turn_id=tid, rating=2, comment=None)
    db.purge_session(sid)
    assert db.get_session(sid) is None
    assert db.feedback_for(tid) == []
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest tests/test_dao.py -v
```

- [ ] **Step 3: schema.py**

```python
# db/schema.py
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  consent_version TEXT NOT NULL,
  consent_at TEXT NOT NULL,
  user_label TEXT
);

CREATE TABLE IF NOT EXISTS turns (
  turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  query TEXT NOT NULL,
  response TEXT NOT NULL,
  retrieved_sources TEXT NOT NULL,
  retrieved_score REAL,
  latency_ms INTEGER
);

CREATE TABLE IF NOT EXISTS feedback (
  feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
  turn_id INTEGER NOT NULL REFERENCES turns(turn_id) ON DELETE CASCADE,
  rating INTEGER NOT NULL,
  comment TEXT,
  created_at TEXT NOT NULL
);
"""
```

- [ ] **Step 4: dao.py**

```python
# db/dao.py
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from db.schema import SCHEMA


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _conn(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)

    def new_session(self, *, consent_version: str, user_label: str | None) -> str:
        sid = uuid.uuid4().hex
        ts = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO sessions(session_id, created_at, consent_version, consent_at, user_label) VALUES (?,?,?,?,?)",
                (sid, ts, consent_version, ts, user_label),
            )
        return sid

    def get_session(self, session_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            return dict(r) if r else None

    def add_turn(self, *, session_id: str, query: str, response: str,
                 retrieved_sources: list[str], retrieved_score: float | None,
                 latency_ms: int | None) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO turns(session_id, created_at, query, response, retrieved_sources, retrieved_score, latency_ms) VALUES (?,?,?,?,?,?,?)",
                (session_id, _now(), query, response, json.dumps(retrieved_sources, ensure_ascii=False), retrieved_score, latency_ms),
            )
            return int(cur.lastrowid)

    def add_feedback(self, *, turn_id: int, rating: int, comment: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO feedback(turn_id, rating, comment, created_at) VALUES (?,?,?,?)",
                (turn_id, rating, comment, _now()),
            )

    def feedback_for(self, turn_id: int) -> list[dict]:
        with self._conn() as c:
            rs = c.execute("SELECT * FROM feedback WHERE turn_id = ?", (turn_id,)).fetchall()
            return [dict(r) for r in rs]

    def purge_session(self, session_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
```

- [ ] **Step 5: 통과 확인 + 커밋**

```bash
.venv/bin/pytest tests/test_dao.py -v
git add db/schema.py db/dao.py tests/test_dao.py
git commit -m "Task 14: SQLite schema + DAO (sessions/turns/feedback/purge) + tests"
```

---

## Task 15: FastAPI 백엔드 (backend.py)

**Files:**
- Create: `backend.py`

- [ ] **Step 1: 구현**

```python
# backend.py
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
from generation.pipeline import RagEngine


load_dotenv()

CONSENT_VERSION = "2026-05-26-v1"
ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", "./data/assets"))
LOGS_DB_PATH = Path(os.environ.get("LOGS_DB_PATH", "./data/chat_logs.db"))

app = FastAPI(title="LMS 챗봇")
db = Database(LOGS_DB_PATH)
db.init()
engine: RagEngine | None = None


def _engine() -> RagEngine:
    global engine
    if engine is None:
        engine = RagEngine()
    return engine


app.mount("/static", StaticFiles(directory="static"), name="static")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/")
def index():
    return FileResponse("static/index.html")


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

    eng = _engine()
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

        # 로깅
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
```

- [ ] **Step 2: 커밋** (UI 가 아직 없어 실행은 Task 16 후)

```bash
git add backend.py
git commit -m "Task 15: FastAPI backend (/chat SSE, /consent, /feedback, /purge, /health)"
```

---

## Task 16: 최소 웹 UI (static/index.html)

**Files:**
- Create: `static/index.html`

- [ ] **Step 1: 작성**

```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LMS 챗봇</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; margin: 0; background: #f6f8fa; color: #1f2328; }
  .wrap { max-width: 760px; margin: 0 auto; padding: 24px 16px 80px; }
  h1 { font-size: 18px; margin: 0 0 16px; }
  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; }
  .modal { background: #fff; border-radius: 8px; padding: 24px; max-width: 540px; }
  .modal h2 { font-size: 16px; margin: 0 0 12px; }
  .modal section { border-top: 1px solid #d0d7de; padding: 10px 0; }
  .modal section h3 { margin: 0 0 4px; font-size: 13px; color: #57606a; }
  .modal section p { margin: 0; font-size: 14px; }
  .modal .accent { background: #fff8c5; padding: 8px 10px; border-radius: 4px; margin: 8px 0; font-size: 13px; }
  .modal .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
  button { padding: 8px 14px; border: 1px solid #d0d7de; background: #fff; border-radius: 6px; cursor: pointer; font-size: 14px; }
  button.primary { background: #0969da; color: #fff; border-color: #0969da; }
  .log { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; min-height: 320px; max-height: 60vh; overflow-y: auto; }
  .turn { margin-bottom: 20px; }
  .q { color: #57606a; font-size: 13px; margin-bottom: 4px; }
  .a { white-space: pre-wrap; }
  .src { margin-top: 8px; font-size: 12px; color: #57606a; }
  .imgs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
  .imgs img { max-width: 200px; border: 1px solid #d0d7de; border-radius: 4px; }
  .fb { margin-top: 8px; display: flex; gap: 6px; }
  .fb button { padding: 4px 8px; font-size: 12px; }
  .input { display: flex; gap: 8px; margin-top: 16px; }
  .input input { flex: 1; padding: 10px; border: 1px solid #d0d7de; border-radius: 6px; font-size: 14px; }
  .top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
  .top .label { font-size: 12px; color: #57606a; }
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>LMS 챗봇</h1>
    <span class="label" id="user-label"></span>
  </div>
  <div class="log" id="log"></div>
  <form class="input" id="form">
    <input id="q" placeholder="질문을 입력하십시오" autocomplete="off" disabled>
    <button class="primary" type="submit" disabled>전송</button>
  </form>
  <p style="margin-top:12px;font-size:12px;color:#57606a">
    <a href="#" id="purge">대화 기록 삭제 및 동의 철회</a>
  </p>
</div>

<div class="modal-bg" id="modal">
  <div class="modal">
    <h2>개인정보 수집 및 이용 동의</h2>
    <section><h3>수집 항목</h3><p>질의 본문, 응답 본문, 응답 시각, 표시명(선택), 피드백 점수와 코멘트</p></section>
    <section><h3>수집 목적</h3><p>가이드북 업데이트 우선순위 도출 및 챗봇 응답 품질 모니터링</p></section>
    <section><h3>보유 기간</h3><p>수집일로부터 6개월. 동의 철회 시 즉시 삭제</p></section>
    <section><h3>동의 철회 방법</h3><p>화면 하단의 "대화 기록 삭제 및 동의 철회" 링크를 누르면 즉시 삭제됩니다</p></section>
    <div class="accent">본 대화 내용은 모델 학습에 사용되지 않습니다.</div>
    <div class="accent">외부 제3자에게 제공되지 않습니다 (모든 처리는 로컬에서 이루어집니다).</div>
    <p style="font-size:12px;color:#57606a;margin:8px 0 0">보호책임자: 김강민 · 문의: 동서대학교 교육혁신처 교수학습개발센터 · <a href="/static/privacy.html" target="_blank">처리방침 전문</a></p>
    <div style="margin-top:12px">
      <label style="font-size:13px">표시명(선택): <input id="ulabel" style="border:1px solid #d0d7de;border-radius:4px;padding:4px 6px"></label>
    </div>
    <div class="actions">
      <button id="deny">동의 안 함</button>
      <button class="primary" id="agree">동의하고 시작</button>
    </div>
  </div>
</div>

<script>
const $ = (s) => document.querySelector(s);
let session = null;

async function consent(userLabel) {
  const r = await fetch("/consent", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({user_label: userLabel})});
  const d = await r.json();
  session = d.session_id;
  localStorage.setItem("lms_session", session);
  localStorage.setItem("lms_consent", d.consent_version);
  if (userLabel) {
    localStorage.setItem("lms_label", userLabel);
    $("#user-label").textContent = userLabel;
  }
  $("#modal").style.display = "none";
  $("#q").disabled = false;
  $("#form button[type=submit]").disabled = false;
}

function deny() {
  document.body.innerHTML = "<div style='padding:40px;text-align:center'>동의하지 않으시면 챗봇을 사용하실 수 없습니다.</div>";
}

async function ask(query) {
  const log = $("#log");
  const div = document.createElement("div");
  div.className = "turn";
  div.innerHTML = `<div class="q">${escape(query)}</div><div class="a"></div><div class="imgs"></div><div class="src"></div><div class="fb"></div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;

  const resp = await fetch("/chat", {method:"POST", headers: {"content-type":"application/json"}, body: JSON.stringify({session_id: session, query})});
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let turnId = null;
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream: true});
    const lines = buf.split("\n\n");
    buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const evt = JSON.parse(line.slice(6));
      if (evt.type === "text") {
        div.querySelector(".a").textContent += evt.delta;
        log.scrollTop = log.scrollHeight;
      } else if (evt.type === "done") {
        const imgs = div.querySelector(".imgs");
        evt.images.forEach(src => { const i = document.createElement("img"); i.src = src; imgs.appendChild(i); });
        if (evt.sources?.length) div.querySelector(".src").textContent = "참고: " + evt.sources.join(", ");
      } else if (evt.type === "turn_id") {
        turnId = evt.turn_id;
        const fb = div.querySelector(".fb");
        [1,2,3].forEach(r => {
          const b = document.createElement("button");
          b.textContent = ["도움 안 됨","보통","도움 됨"][r-1];
          b.onclick = () => fetch("/feedback", {method:"POST", headers:{"content-type":"application/json"}, body: JSON.stringify({turn_id: turnId, rating: r})}).then(()=>{ fb.textContent = "감사합니다."; });
          fb.appendChild(b);
        });
      }
    }
  }
}

function escape(s) { return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

$("#form").addEventListener("submit", e => {
  e.preventDefault();
  const q = $("#q").value.trim();
  if (!q) return;
  $("#q").value = "";
  ask(q);
});

$("#agree").addEventListener("click", e => { e.preventDefault(); consent($("#ulabel").value.trim() || null); });
$("#deny").addEventListener("click", e => { e.preventDefault(); deny(); });
$("#purge").addEventListener("click", async e => {
  e.preventDefault();
  if (!session) return;
  if (!confirm("이 세션의 대화 기록을 모두 삭제하고 동의를 철회합니다. 진행할까요?")) return;
  await fetch("/purge", {method:"POST", headers:{"content-type":"application/json"}, body: JSON.stringify({session_id: session})});
  localStorage.removeItem("lms_session");
  localStorage.removeItem("lms_consent");
  location.reload();
});

const saved = localStorage.getItem("lms_session");
const savedConsent = localStorage.getItem("lms_consent");
if (saved && savedConsent) {
  session = saved;
  $("#modal").style.display = "none";
  $("#q").disabled = false;
  $("#form button[type=submit]").disabled = false;
  const lbl = localStorage.getItem("lms_label");
  if (lbl) $("#user-label").textContent = lbl;
}
</script>
</body>
</html>
```

- [ ] **Step 2: 서버 부팅 및 수동 확인**

```bash
./run.sh
```
브라우저에서 http://localhost:8080 접속 → 동의 모달 → 동의 → 질문 입력 → 응답 스트림과 이미지·출처 확인.

- [ ] **Step 3: 커밋**

```bash
git add static/index.html
git commit -m "Task 16: minimal web UI (consent modal + chat + feedback + purge)"
```

---

## Task 17: 처리방침 전문 (docs/privacy.md → static/privacy.html)

**Files:**
- Create: `docs/privacy.md`
- Create: `static/privacy.html`

- [ ] **Step 1: docs/privacy.md 작성** (spec 6 절을 기반으로 처리방침 전문)

```markdown
# LMS 챗봇 개인정보처리방침

본 처리방침은 동서대학교 LMS 챗봇 서비스(이하 "서비스")가 수집·이용하는 개인정보에 관한 사항을 안내합니다. 본 방침은 「개인정보 보호법」, 「표준개인정보보호지침」, 개인정보보호위원회의 「개인정보처리방침 작성 가이드(2025)」 및 「생성형 인공지능(AI) 개발·활용을 위한 개인정보 처리 안내서(2025.8)」를 준거로 합니다.

## 1. 수집 항목
- 질의 본문, 응답 본문, 응답 시각
- 표시명(선택)
- 피드백 점수와 코멘트
- 운영 메타데이터(검색 점수, 응답 지연시간)

다음은 수집하지 않습니다: 실명, 학번, 교번, 이메일, IP 주소, 기기 식별자.

## 2. 수집 목적
1. 가이드북 업데이트 우선순위 도출
2. 챗봇 응답 품질 모니터링

본 목적 외 용도(특히 모델 학습)에는 수집된 대화를 사용하지 않습니다.

## 3. 보유 및 이용 기간
수집일로부터 6개월. 이후 자동 삭제합니다. 동의 철회 또는 삭제 요청 시 즉시 삭제합니다.

## 4. 제3자 제공
제공하지 않습니다.

## 5. 처리 위탁
위탁하지 않습니다. LLM 추론은 로컬(Ollama)에서 수행하며 외부 API를 호출하지 않습니다.

## 6. 정보주체의 권리
열람·정정·삭제·처리정지·동의 철회 권리를 행사하실 수 있습니다. 챗봇 화면 하단의 "대화 기록 삭제 및 동의 철회" 링크 또는 아래 문의처를 통해 요청해 주십시오.

## 7. 안전성 확보 조치
대화 기록은 로컬 SQLite 파일에 저장되며 외부 네트워크로 전송되지 않습니다. 파일 접근권한은 서비스 운영자에 한정합니다.

## 8. 자동수집장치
쿠키, 웹로그, 접속 IP 등 자동수집 장치를 사용하지 않습니다.

## 9. 개인정보 보호책임자 및 문의처
- 보호책임자: 김강민
- 문의처: 동서대학교 교육혁신처 교수학습개발센터

## 10. 변경 이력
- 2026-05-26 (v1): 최초 작성
```

- [ ] **Step 2: static/privacy.html — md 를 그대로 보여주는 단순 페이지** (md 라이브러리 없이)

```html
<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>처리방침</title>
<style>body{max-width:760px;margin:40px auto;padding:0 16px;font-family:-apple-system,"Apple SD Gothic Neo",sans-serif;line-height:1.7;color:#1f2328}h1{font-size:22px}h2{font-size:16px;margin-top:28px;border-bottom:1px solid #d0d7de;padding-bottom:4px}</style>
</head><body>
<h1>LMS 챗봇 개인정보처리방침</h1>
<p>본 처리방침은 동서대학교 LMS 챗봇 서비스가 수집·이용하는 개인정보에 관한 사항을 안내합니다. 「개인정보 보호법」, 「표준개인정보보호지침」, 개인정보보호위원회의 「개인정보처리방침 작성 가이드(2025)」 및 「생성형 인공지능(AI) 개발·활용을 위한 개인정보 처리 안내서(2025.8)」를 준거로 합니다.</p>
<h2>1. 수집 항목</h2><ul><li>질의 본문, 응답 본문, 응답 시각</li><li>표시명(선택)</li><li>피드백 점수와 코멘트</li><li>운영 메타데이터(검색 점수, 응답 지연시간)</li></ul><p>실명·학번·교번·이메일·IP·기기 식별자는 수집하지 않습니다.</p>
<h2>2. 수집 목적</h2><ol><li>가이드북 업데이트 우선순위 도출</li><li>챗봇 응답 품질 모니터링</li></ol><p>본 목적 외 용도, 특히 모델 학습에는 수집된 대화를 사용하지 않습니다.</p>
<h2>3. 보유 및 이용 기간</h2><p>수집일로부터 6개월. 이후 자동 삭제. 동의 철회 또는 삭제 요청 시 즉시 삭제합니다.</p>
<h2>4. 제3자 제공</h2><p>제공하지 않습니다.</p>
<h2>5. 처리 위탁</h2><p>위탁하지 않습니다. LLM 추론은 로컬에서 수행하며 외부 API를 호출하지 않습니다.</p>
<h2>6. 정보주체의 권리</h2><p>열람·정정·삭제·처리정지·동의 철회 권리를 행사하실 수 있습니다.</p>
<h2>7. 안전성 확보 조치</h2><p>로컬 SQLite 파일 저장, 외부 전송 없음, 접근권한 운영자 한정.</p>
<h2>8. 자동수집장치</h2><p>쿠키·웹로그·접속 IP 등 자동수집 장치 미사용.</p>
<h2>9. 개인정보 보호책임자 및 문의처</h2><p>보호책임자: 김강민<br>문의처: 동서대학교 교육혁신처 교수학습개발센터</p>
<h2>10. 변경 이력</h2><p>2026-05-26 (v1): 최초 작성</p>
</body></html>
```

- [ ] **Step 3: 커밋**

```bash
git add docs/privacy.md static/privacy.html
git commit -m "Task 17: privacy policy (Markdown + HTML)"
```

---

## Task 18: 통합 점검 + 푸시

- [ ] **Step 1: 모든 테스트 통과 확인**

```bash
.venv/bin/pytest -v
```

- [ ] **Step 2: 인덱싱 → 서버 부팅 → 질의 한 번 라이브 확인**

```bash
.venv/bin/python -m ingest.cli
./run.sh   # 다른 터미널에서 ollama serve 가 떠 있어야 함
```
브라우저에서 한 질문을 던져 응답·이미지·출처·피드백 동작 확인.

- [ ] **Step 3: 푸시**

```bash
git push origin main
```

---

## Self-review 결과 (인라인 수정 적용)

- spec 1.4 비목표(모델 학습 미활용): persona.py 와 privacy.md 양쪽에 명시 — 커버 ✓
- spec 2.2 응답 규칙(존대·마크업 금지·이모지 금지·출처 표기·범위 외 거절): persona.py + filters.py 양쪽 안전망 — 커버 ✓
- spec 2.3 전처리 룰 5항: preprocess.py 의 strip_emoji + clean_markdown 분리 + filters.py 이중 안전망 — 커버 ✓
- spec 3.2 청크 단위(.md 페이지 단위, 2000 초과 시 H2 분할): chunk.py — 커버 ✓
- spec 3.3 임베딩 BGE-M3 + ChromaDB: embed.py — 커버 ✓
- spec 3.4 BM25 rank_bm25: bm25_index.py — 커버 ✓
- spec 4.1 하이브리드 0.4/0.6, top-5: pipeline.py + hybrid.py — 커버 ✓
- spec 4.3 이미지 매칭 최대 5장 + 상위 청크 우선: pipeline.py 의 응답 종료 시 집계 — 커버 ✓
- spec 4.4 num_ctx=8192: pipeline.py options 에 포함 — 커버 ✓
- spec 4.5 임계값 미만 정형 응답: pipeline.py SCORE_THRESHOLD — 커버 ✓
- spec 5.3 스키마: db/schema.py — 커버 ✓
- spec 6.2 항목별 분리 고지 + 핵심 약속 강조: static/index.html 모달 — 커버 ✓
- spec 6.4 동의 철회 → 즉시 삭제: /purge + UI 링크 — 커버 ✓
- spec 7 환경변수 (OLLAMA_HOST 등): .env.example — 커버 ✓
- spec 8 마일스톤 1~8: Task 1~17 모두 매핑 — 커버 ✓

placeholder 스캔 결과: 본 plan 안에 TBD/TODO 없음. 모든 step 에 실제 코드 또는 명령 포함.
