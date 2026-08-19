"""선택형 상담 노드 레지스트리. 인덱스(chroma)+카탈로그 TOC+FAQ 답변 문서에서
노드를 자동 도출하고 data/nodes.overlay.json 큐레이션을 덧입힌다. LLM 미경유 —
FAQ는 faq_answer 원문, 가이드는 정제 본문 직출력."""
from __future__ import annotations
import hashlib
import json
import random
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from app_types import ChatEvent, AnswerCard, Chunk, NodeLink, NodeRef, ScoredChunk, Source
from generation.catalog import Manual, build_catalog
from generation.faq import faq_answer, plain_answer
from index.vector_store import get_collection
from ingest.preprocess import strip_emoji
from rag.state import RagState
from retrieval.search import _chunk_from_meta

FAQ_CATEGORY = "자주 묻는 질문"
FAQ_ROOT_ID = "lms-faq-root"
_DEFAULT_WELCOME = (
    "동서대학교 LMS 교수자 가이드 상담입니다. 아래에서 주제를 선택하시면 "
    "확정된 안내를 보여드립니다."
)


@dataclass(frozen=True)
class Node:
    id: str
    category: str
    category_id: str
    manual: str
    doc_set: str
    label: str
    doc_title: str
    answer: str
    images: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    parent: NodeRef | None = None
    related: tuple[NodeRef, ...] = ()
    links: tuple[NodeLink, ...] = ()


@dataclass(frozen=True)
class Registry:
    by_id: dict[str, Node]
    meta: dict


# 파일명 유래 표기 흔들림을 접는다. 같은 노션 제목이 소스마다 다르게 온다:
#   TOC 라벨(원문)        : '퀴즈/설문 유형', 'Cloud Editor란?', '1. 앞/뒷부분', '\[피어리뷰\]'
#   노션 공식 export 파일명: '퀴즈 설문 유형', 'Cloud Editor란',  '1 앞 뒷부분'
#   sync 수집기 파일명     : '퀴즈-설문 유형'                      '[피어리뷰]'
# '/', '-', '.' 는 공백으로, '?' 와 TOC 이스케이프 '\' 는 삭제로 접으면 세 소스가
# 같은 키로 떨어진다. 조인·ID 전용이라 표시 문자열에는 영향이 없다.
_FOLD_TO_SPACE_RE = re.compile(r"[/\-.]")
_FOLD_DROP_RE = re.compile(r"[?\\]")


def _norm(title: str) -> str:
    """조인·ID용 정규화: 이모지 제거 + 표기 흔들림 접기 + 연속 공백 축약.

    안 접으면 라벨과 인덱스 제목이 어긋난 문서의 노드·핀이 조용히 빠진다 —
    2026-08-19 실측: 슬래시 13건 + 노션 export 표기 6건 + 이스케이프 1건."""
    folded = _FOLD_DROP_RE.sub("", _FOLD_TO_SPACE_RE.sub(" ", title or ""))
    return re.sub(r"\s+", " ", strip_emoji(folded)).strip()


def _node_id(manual: str, doc_set: str, doc_title: str) -> str:
    h = hashlib.sha1(_norm(doc_title).encode("utf-8")).hexdigest()[:8]
    return f"{manual.lower()}-{doc_set}-{h}"


def _cat_id(manual: str, category: str) -> str:
    h = hashlib.sha1(_norm(category).encode("utf-8")).hexdigest()[:8]
    return f"{manual.lower()}-cat-{h}"


def group_docs(chunks: list[Chunk]) -> dict[tuple[str, str], dict]:
    """(manual, _norm(doc_title)) 로 청크를 묶어 seq 순으로 본문·이미지를 결합한다."""
    buckets: dict[tuple[str, str], list[Chunk]] = {}
    for c in chunks:
        if not c.doc_title:
            continue
        buckets.setdefault((c.manual, _norm(c.doc_title)), []).append(c)

    out: dict[tuple[str, str], dict] = {}
    for key, cs in buckets.items():
        cs = sorted(cs, key=lambda c: c.seq)
        images: list[str] = []
        for c in cs:
            for img in c.image_refs:
                if img and img not in images:
                    images.append(img)
        out[key] = {
            "doc_title": cs[0].doc_title,
            "manual": cs[0].manual,
            "doc_set": cs[0].doc_set,
            "text": "\n\n".join(c.text for c in cs).strip(),
            "images": tuple(images),
            "notion_url": next((c.notion_url for c in cs if c.notion_url), ""),
        }
    return out


def build_nodes(chunks: list[Chunk], catalog: tuple[Manual, ...]) -> dict[str, Node]:
    """카탈로그 트리로 가이드 노드를, doc_set=='faq' 문서로 FAQ 노드를 만든다.
    인덱스에 없는 카탈로그 항목·빈 FAQ 답변은 건너뛴다(graceful)."""
    docs = group_docs(chunks)
    nodes: dict[str, Node] = {}

    # 가이드: 카탈로그 순서·카테고리 기준
    for manual in catalog:
        for cat in manual.categories:
            cid = _cat_id(manual.name, cat.name)
            for doc_label in cat.docs:
                doc = docs.get((manual.name, _norm(doc_label)))
                if doc is None or doc["doc_set"] != "guide":
                    continue
                nid = _node_id(manual.name, "guide", doc["doc_title"])
                nodes[nid] = Node(
                    id=nid, category=cat.name, category_id=cid,
                    manual=manual.name, doc_set="guide",
                    label=doc["doc_title"], doc_title=doc["doc_title"],
                    # 원문 그대로 두면 '#'·'**'·'![](…)' 가 화면에 문자로 노출된다
                    # — 프론트가 마크다운을 파싱하지 않는다(faq.plain_answer 참조).
                    answer=plain_answer(doc["text"]), images=doc["images"],
                    sources=(Source(title=doc["doc_title"], url=doc["notion_url"]),),
                    parent=NodeRef(id=cid, label=cat.name),
                )

    # FAQ: 인덱싱된 doc_set=='faq' 문서 전부(빈 답변 제외)
    for (manual, _nt), doc in docs.items():
        if doc["doc_set"] != "faq":
            continue
        ans = faq_answer(doc["text"])
        if not ans:
            continue
        label = doc["doc_title"]
        if label.startswith("FAQ —"):           # 방어적(CSV는 미인덱싱)
            label = label[len("FAQ —"):].strip()
        nid = _node_id(manual, "faq", doc["doc_title"])
        nodes[nid] = Node(
            id=nid, category=FAQ_CATEGORY, category_id=FAQ_ROOT_ID,
            manual=manual, doc_set="faq",
            label=label, doc_title=doc["doc_title"],
            answer=ans, images=doc["images"], sources=(),
            parent=NodeRef(id=FAQ_ROOT_ID, label=FAQ_CATEGORY),
        )
    return nodes


def fill_auto_related(nodes: dict[str, Node], *, limit: int = 6) -> dict[str, Node]:
    """같은 category_id 형제를 related 로 채운다(자기 제외, 카탈로그 순서 유지).
    오버레이가 이후 덮어쓸 수 있다."""
    by_cat: dict[str, list[Node]] = {}
    for n in nodes.values():
        by_cat.setdefault(n.category_id, []).append(n)
    out: dict[str, Node] = {}
    for nid, n in nodes.items():
        sibs = [s for s in by_cat.get(n.category_id, []) if s.id != n.id][:limit]
        out[nid] = replace(n, related=tuple(NodeRef(id=s.id, label=s.label) for s in sibs))
    return out


def load_overlay(path: Path) -> dict:
    """오버레이 JSON 로드. 없으면 빈 dict(graceful)."""
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def overlay_meta(overlay: dict) -> dict:
    """첫 화면 메타(welcome/quick_links). 예약 키 '_meta'."""
    return overlay.get("_meta", {})


def apply_overlay(nodes: dict[str, Node], overlay: dict) -> dict[str, Node]:
    """id 기준으로 answer/links/related/parent 를 덮어쓴다. '_'로 시작하는 예약
    키와 알 수 없는 id 는 무시(graceful)."""
    out = dict(nodes)
    for nid, ov in overlay.items():
        if nid.startswith("_"):
            continue
        base = out.get(nid)
        if base is None:
            continue
        out[nid] = replace(
            base,
            answer=ov.get("answer", base.answer),
            links=(tuple(NodeLink(**x) for x in ov["links"])
                   if "links" in ov else base.links),
            related=(tuple(NodeRef(**x) for x in ov["related"])
                     if "related" in ov else base.related),
            parent=(NodeRef(**ov["parent"]) if ov.get("parent") else base.parent),
        )
    return out


def card_of(node: Node) -> AnswerCard:
    """Node → /answer 응답 카드. label 이 곧 사용자가 누른 '질문'."""
    return AnswerCard(
        id=node.id, category=node.category, question=node.label,
        answer=node.answer, images=node.images, links=node.links,
        related=node.related, parent=node.parent, sources=node.sources,
    )


def dockey_index(nodes: dict[str, Node]) -> dict[tuple[str, str], Node]:
    return {(n.manual, _norm(n.doc_title)): n for n in nodes.values()}



def find_related(items: Iterable[ScoredChunk], nodes: dict[str, Node], *, limit: int = 5) -> list[NodeRef]:
    """검색 결과(ScoredChunk) → 노드 후보. (manual, _norm(doc_title))로 매핑,
    중복 노드 제거, 점수 순 상위 limit. 노드 없는 청크는 건너뜀. LLM 미경유."""
    idx = dockey_index(nodes)
    seen: set[str] = set()
    out: list[NodeRef] = []
    for it in items:
        n = idx.get((it.chunk.manual, _norm(it.chunk.doc_title)))
        if n is None or n.id in seen:
            continue
        seen.add(n.id)
        out.append(NodeRef(id=n.id, label=n.label))
        if len(out) >= limit:
            break
    return out


def entry_payload(registry: Registry, catalog: tuple[Manual, ...],
                  *, n_recommended: int = 6) -> dict:
    """첫 화면: welcome + 카테고리(가이드 카탈로그 순서 + FAQ 합성) + 추천 FAQ + 빠른 링크."""
    nodes = registry.by_id
    categories: list[dict] = []
    for manual in catalog:
        for cat in manual.categories:
            members = []
            for doc_label in cat.docs:
                n = nodes.get(_node_id(manual.name, "guide", doc_label))
                if n is not None:
                    members.append({"id": n.id, "label": n.label})
            if members:
                categories.append({"id": _cat_id(manual.name, cat.name),
                                   "label": cat.name, "manual": manual.name,
                                   "nodes": members})

    faq_nodes = [n for n in nodes.values() if n.doc_set == "faq"]
    if faq_nodes:
        categories.append({"id": FAQ_ROOT_ID, "label": FAQ_CATEGORY, "manual": "LMS",
                           "nodes": [{"id": n.id, "label": n.label} for n in faq_nodes]})

    sample = random.sample(faq_nodes, min(n_recommended, len(faq_nodes))) if faq_nodes else []
    return {
        "welcome": registry.meta.get("welcome", _DEFAULT_WELCOME),
        "categories": categories,
        "recommended": [{"id": n.id, "label": n.label} for n in sample],
        "quick_links": registry.meta.get("quick_links", []),
    }


def enumerate_chunks(state: RagState) -> list[Chunk]:
    """chroma 컬렉션의 모든 청크를 Chunk 로 복원한다(노드 도출용)."""
    coll = get_collection(state.chroma)
    res = coll.get(include=["documents", "metadatas"])
    return [
        _chunk_from_meta(cid, doc, meta)
        for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"])
    ]


def build_pinned_events(state: RagState, pins: dict[str, tuple[str, str]]
                        ) -> dict[str, tuple[ChatEvent, ...]]:
    """기동 시 1회: 핀 질문 → 확정 답변 SSE 이벤트 맵.

    레지스트리(find_by_doc)가 아니라 인덱스 전수 열거로 찾는 이유: 노드는 카탈로그
    카테고리에서만 만들어지는데, 메타 네비('전체 메뉴 안내' 등)로 제외된 카테고리의
    문서는 인덱스에는 있어도 노드가 없다 — '로그인 - 대시보드 유형 선택'이 그렇다.
    핀은 문서를 가리키는 것이지 노드를 가리키는 것이 아니다.

    없는 핀 대상은 맵에서 빠지고 경고만 남는다 — 문서가 노션에서 사라져도 부팅은
    막지 않되, /chat 은 검색 경로로 자연 폴백한다.
    """
    docs = group_docs(enumerate_chunks(state))
    out: dict[str, tuple[ChatEvent, ...]] = {}
    for query, (manual, title) in pins.items():
        doc = docs.get((manual, _norm(title)))
        if doc is None:
            print(f"[nodes] 핀 대상 문서 없음: {manual}/{title} — '{query}' 는 검색 경로로",
                  flush=True)
            continue
        answer = (faq_answer if doc["doc_set"] == "faq" else plain_answer)(doc["text"])
        out[query] = (
            ChatEvent(type="text", delta=answer),
            ChatEvent(type="text_final", text=answer),
            ChatEvent(type="done", images=doc["images"],
                      sources=(Source(title=doc["doc_title"], url=doc["notion_url"]),),
                      score=1.0),
        )
    return out


def fixed_events(text: str) -> tuple[ChatEvent, ...]:
    """고정 문안 → /chat SSE 이벤트. 문서 없이 문안이 답의 전부인 질문용
    (예: 자료실 링크 안내). 출처·이미지 없음, score=1.0 — 확정 답변이다."""
    return (
        ChatEvent(type="text", delta=text),
        ChatEvent(type="text_final", text=text),
        ChatEvent(type="done", score=1.0),
    )


def catalog_pin_events(chunks: list[Chunk], catalog: tuple[Manual, ...]
                       ) -> dict[str, tuple[ChatEvent, ...]]:
    """카탈로그의 모든 문서 라벨 → 그 문서의 확정 답변 SSE.

    카탈로그 클릭은 문서 '제목 텍스트'를 /chat 으로 보낸다. 이걸 검색에 태우면
    짧은 제목('웹링크', '소셜미디어')이 자기 문서를 못 찾아 폴백이 난다(2026-08-19
    라이브 전수 101건 중 4건 실측). 제목이 곧 문서를 가리키는데 확률적 검색을
    거칠 이유가 없다 — 상담 플로우·TOP 핀과 같은 판단(같은 버튼 → 같은 답).

    key 는 프론트가 실제로 보내는 문자열(카탈로그 doc 라벨)이다. 매뉴얼 간 라벨
    충돌은 현재 없음을 확인했고, 생기면 뒤에 온 것이 이긴다 — 그때는 라벨을
    고치는 것이 맞다(사용자에게 두 문서를 구분해 보여줄 방법도 없다).
    """
    docs = group_docs(chunks)
    out: dict[str, tuple[ChatEvent, ...]] = {}
    for manual in catalog:
        for cat in manual.categories:
            for label in cat.docs:
                doc = docs.get((manual.name, _norm(label)))
                if doc is None:
                    print(f"[nodes] 카탈로그 핀 대상 없음: {manual.name}/{label}",
                          flush=True)
                    continue
                answer = (faq_answer if doc["doc_set"] == "faq" else plain_answer)(doc["text"])
                out[label] = (
                    ChatEvent(type="text", delta=answer),
                    ChatEvent(type="text_final", text=answer),
                    ChatEvent(type="done", images=doc["images"],
                              sources=(Source(title=doc["doc_title"],
                                              url=doc["notion_url"]),),
                              score=1.0),
                )
    return out


def build_catalog_pins(state: RagState) -> dict[str, tuple[ChatEvent, ...]]:
    """기동 시 1회: 인덱스 전수 열거 + 카탈로그로 자동 핀 맵을 만든다."""
    return catalog_pin_events(enumerate_chunks(state), build_catalog())


def build_registry(state: RagState, *, overlay_path: Path) -> Registry:
    """기동 시 1회: 인덱스 전수 열거 → 노드 도출 → 자동 related → 오버레이 병합."""
    chunks = enumerate_chunks(state)
    catalog = build_catalog()
    nodes = fill_auto_related(build_nodes(chunks, catalog))
    overlay = load_overlay(overlay_path)
    nodes = apply_overlay(nodes, overlay)
    return Registry(by_id=nodes, meta=overlay_meta(overlay))
