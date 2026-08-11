"""Gemini Embedding API 클라이언트 — 배치 임베딩(embed_batch).

generation/gemini.py 와 같은 구성이다: 순수 변환(instruct/build_payload/
extract_embeddings/l2_normalize)은 모듈 함수로 분리해 네트워크 없이 테스트하고,
HTTP 는 맨 아래 한 함수에만 둔다.

로컬 BGE-M3 어댑터와 다른 점이 셋이고 이 모듈이 전부 흡수한다:

  1. 문서와 질문을 다르게 인코딩한다. gemini-embedding-2 는 task_type 파라미터가
     없고 대신 프롬프트 지시문으로 용도를 알린다 — 문서는 "title: … | text: …",
     질문은 "task: search result | query: …". BGE-M3 는 대칭 모델이라 이 구분이
     없었으므로, kind 인자는 이 백엔드에서만 의미를 갖는다.
  2. 동기 API 다. 생성(generation/)은 async 지만 임베딩은 인덱싱·검색 경로 양쪽
     모두 동기라 httpx.Client 를 쓴다.
  3. 요청당 배치 상한이 있어 나눠 보낸다(BATCH_LIMIT).

정규화: gemini-embedding-2 는 축소 차원(768/1536)을 자동 정규화한다고 문서에
명시돼 있지만, 여기서 한 번 더 태운다. index/vector_store.py 의 유사도 환산
(`1 - d/2`)이 단위벡터를 전제로 하고, 그 전제가 깨지면 tuning.py 의 임계값이
전부 어긋나기 때문이다 — 이미 정규화된 입력에는 사실상 no-op 이라 공짜다.
"""
from __future__ import annotations
import math

import httpx

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# 요청 하나에 담을 최대 문서 수. 상한에 딱 붙이지 않고 여유를 둔다.
BATCH_LIMIT = 100

DOCUMENT = "document"
QUERY = "query"


def instruct(text: str, kind: str, *, title: str = "") -> str:
    """용도 지시문을 붙인다. gemini-embedding-2 는 task_type 대신 이 방식을 쓴다.

    알 수 없는 kind 는 조용히 문서로 넘기지 않고 실패시킨다 — 오타가 검색 품질
    저하로만 나타나면 원인을 찾기 어렵다(llm.py 의 provider 분기와 같은 판단)."""
    if kind == QUERY:
        return f"task: search result | query: {text}"
    if kind == DOCUMENT:
        return f"title: {title} | text: {text}" if title else f"text: {text}"
    raise ValueError(f"알 수 없는 임베딩 kind: {kind!r} (document|query)")


def build_payload(model: str, texts: list[str], kind: str, dim: int) -> dict:
    """batchEmbedContents 요청 본문. 각 요청에 model 을 다시 넣어야 한다(API 스펙)."""
    return {
        "requests": [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": instruct(t, kind)}]},
                "outputDimensionality": dim,
            }
            for t in texts
        ]
    }


def l2_normalize(vec: list[float]) -> list[float]:
    """단위벡터로. 영벡터는 그대로 둔다(0 나눗셈 회피)."""
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def extract_embeddings(obj: dict) -> list[list[float]]:
    """응답에서 벡터만 순서대로. 정규화까지 여기서 끝낸다."""
    return [l2_normalize(e.get("values") or []) for e in obj.get("embeddings") or []]


def _batches(texts: list[str], size: int = BATCH_LIMIT):
    for i in range(0, len(texts), size):
        yield texts[i : i + size]


def embed_batch(
    api_key: str,
    model: str,
    texts: list[str],
    *,
    kind: str = DOCUMENT,
    dim: int = 768,
    timeout: float = 60.0,
) -> list[list[float]]:
    """텍스트 목록 → 정규화된 벡터 목록. 입력 순서를 그대로 유지한다.

    HTTP 오류는 예외로 전파한다 — 인덱싱 도중 일부 배치가 조용히 비면 인덱스가
    말없이 불완전해지고, 그건 검색 품질 저하로만 드러나 추적이 어렵다."""
    if not texts:
        return []
    url = f"{API_ROOT}/{model}:batchEmbedContents"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    out: list[list[float]] = []
    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
        for batch in _batches(texts):
            resp = client.post(
                url, json=build_payload(model, batch, kind, dim), headers=headers
            )
            resp.raise_for_status()
            vecs = extract_embeddings(resp.json())
            if len(vecs) != len(batch):
                raise RuntimeError(
                    f"임베딩 개수 불일치: 요청 {len(batch)} → 응답 {len(vecs)}"
                )
            out.extend(vecs)
    return out
