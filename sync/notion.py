"""노션 → IR 어댑터. **네트워크가 없다.**

받아오는 방법(MCP 툴이든 REST 든)과 해석하는 방법을 갈라 둔다. 여기 있는 것은
노션이 주는 JSON 을 IR 로 접는 순수 변환뿐이라, 전송 수단을 바꿔도 이 파일은
그대로다. 테스트도 픽스처만으로 돈다.

호출부가 넘겨야 하는 것은 노션 API 의 원형 그대로다.
  page   : GET /v1/pages/{id}            → {id, last_edited_time, properties}
  blocks : GET /v1/blocks/{id}/children  → {results: [...]} 의 results

**토글은 펼쳐서 넘겨야 한다.** 노션 API 는 `has_children` 만 알려주고 자식은 따로
받아야 한다. 안 받고 넘기면 토글 안 내용이 통째로 빠지는데, 그게 에러 없이
'문서가 짧아진 것'으로만 보인다 — 화면 긁기를 접은 이유와 같은 함정이다.
그래서 자식을 못 받은 블록은 `unresolved_children` 으로 **드러낸다**.

이미지 URL 은 만료된다(노션이 주는 presigned S3 링크). 여기서는 src 를 그대로
담고, 내려받기는 호출부가 즉시 한다.
"""
from __future__ import annotations

from typing import Any, Iterable

from sync.ir import (CODE, HEADING, IMAGE, LIST, SEPARATOR, TABLE, TEXT, Block,
                     Document, normalize)
from sync.manifest import RemotePage, normalize_id

# 노션 블록 타입 → IR 타입. 여기 없는 타입은 무시한다(레이아웃·임베드 등
# 답변에 기여하지 않는 것들). 무시한 타입은 unsupported_types 로 보고한다.
_TEXTUAL = {
    "paragraph": TEXT,
    "quote": TEXT,
    "callout": TEXT,
    "toggle": TEXT,
    "to_do": LIST,
    "bulleted_list_item": LIST,
    "numbered_list_item": LIST,
}
_HEADINGS = {"heading_1": 1, "heading_2": 2, "heading_3": 3}
_ORDERED = {"numbered_list_item"}


def rich_text(items: Iterable[dict[str, Any]] | None) -> str:
    """rich_text 배열 → 평문. 강조·색은 버린다(비교에 기여하지 않는다)."""
    if not items:
        return ""
    out = []
    for it in items:
        # plain_text 가 정석이지만, MCP 구현에 따라 text.content 만 올 수 있다.
        out.append(it.get("plain_text") or (it.get("text") or {}).get("content") or "")
    return "".join(out)


def _image_src(payload: dict[str, Any]) -> str:
    """file(내부 업로드) 과 external(외부 링크) 둘 다에서 URL 을 뽑는다."""
    for key in ("file", "external"):
        url = (payload.get(key) or {}).get("url")
        if url:
            return url
    return ""


def _table_rows(children: list[dict[str, Any]]) -> tuple[tuple[str, ...], ...]:
    rows = []
    for row in children:
        if row.get("type") != "table_row":
            continue
        cells = (row.get("table_row") or {}).get("cells") or []
        rows.append(tuple(rich_text(c) for c in cells))
    return tuple(rows)


def page_title(page: dict[str, Any]) -> str:
    """페이지 제목. DB 행은 제목 속성 이름이 제각각이라 type 으로 찾는다."""
    props = page.get("properties") or {}
    for prop in props.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return normalize(rich_text(prop.get("title")))
    return normalize(rich_text((props.get("title") or {}).get("title")))


def property_lines(page: dict[str, Any], keys: Iterable[str]) -> list[str]:
    """지정한 속성만 `키: 값` 라인으로. 파이프라인의 메타 처리와 맞물린다.

    `ingest.preprocess._META_HEADER_RE` 가 메뉴명·시기·연번·태그 4종을 줄 단위로
    지운다. 표로 내면 그 정규식에 안 걸려 분류 메타가 답변 본문에 그대로 노출된다.
    """
    props = page.get("properties") or {}
    lines = []
    for key in keys:
        prop = props.get(key)
        if not isinstance(prop, dict):
            continue
        value = _property_text(prop)
        if value:
            lines.append(f"{key}: {value}")
    return lines


def _property_text(prop: dict[str, Any]) -> str:
    kind = prop.get("type")
    if kind == "title":
        return normalize(rich_text(prop.get("title")))
    if kind == "rich_text":
        return normalize(rich_text(prop.get("rich_text")))
    if kind == "select":
        return ((prop.get("select") or {}).get("name") or "").strip()
    if kind == "multi_select":
        return ", ".join(o.get("name", "") for o in prop.get("multi_select") or [])
    if kind == "number":
        n = prop.get("number")
        return "" if n is None else str(n)
    return ""


def remote_page(page: dict[str, Any]) -> RemotePage:
    """페이지 객체 → 대조 계획이 쓰는 최소 형태."""
    return RemotePage(
        page_id=normalize_id(page.get("id", "")),
        title=page_title(page),
        last_edited=page.get("last_edited_time", "") or "",
    )


def blocks_to_ir(blocks: list[dict[str, Any]]) -> tuple[tuple[Block, ...], list[str], list[str]]:
    """블록 목록 → (IR 블록, 자식 미해결 블록 id, 처리 못 한 타입).

    뒤 둘은 호출부가 보고 판단하라고 돌려준다. 조용히 버리면 문서가 소리 없이
    짧아진다.
    """
    out: list[Block] = []
    unresolved: list[str] = []
    unsupported: list[str] = []

    for blk in blocks:
        kind = blk.get("type") or ""
        payload = blk.get(kind) or {}
        children = blk.get("children")

        if kind in _HEADINGS:
            out.append(Block(type=HEADING, level=_HEADINGS[kind],
                             text=normalize(rich_text(payload.get("rich_text")))))
        elif kind in _TEXTUAL:
            text = normalize(rich_text(payload.get("rich_text")))
            if text:
                out.append(Block(type=_TEXTUAL[kind], text=text,
                                 ordered=kind in _ORDERED))
        elif kind == "image":
            out.append(Block(type=IMAGE, src=_image_src(payload),
                             text=normalize(rich_text(payload.get("caption")))))
        elif kind == "code":
            out.append(Block(type=CODE, text=rich_text(payload.get("rich_text"))))
        elif kind == "divider":
            out.append(Block(type=SEPARATOR))
        elif kind == "table":
            out.append(Block(type=TABLE, rows=_table_rows(children or [])))
        elif kind in ("child_page", "child_database", "table_row"):
            pass                      # 목차/행은 부모 처리에서 다룬다
        else:
            unsupported.append(kind)

        # 자식이 있다고 표시된 블록은 펼쳐서 넘겨야 한다. 표는 위에서 children 을
        # 직접 소비하므로 제외한다.
        if blk.get("has_children") and children is None and kind != "table":
            unresolved.append(blk.get("id", ""))
        elif children and kind not in ("table",):
            nested, sub_unresolved, sub_unsupported = blocks_to_ir(children)
            out.extend(nested)
            unresolved.extend(sub_unresolved)
            unsupported.extend(sub_unsupported)

    return tuple(out), unresolved, sorted(set(unsupported))


def to_document(page: dict[str, Any], blocks: list[dict[str, Any]],
                *, meta_keys: Iterable[str] = ()) -> tuple[Document, list[str], list[str]]:
    """페이지 + 블록 → Document. meta_keys 를 주면 맨 앞에 `키: 값` 라인을 얹는다."""
    body, unresolved, unsupported = blocks_to_ir(blocks)
    meta = tuple(Block(type=TEXT, text=line) for line in property_lines(page, meta_keys))
    doc = Document(page_id=normalize_id(page.get("id", "")),
                   title=page_title(page), blocks=meta + body)
    return doc, unresolved, unsupported
