"""노션 JSON → IR 변환. 네트워크 없이 픽스처만으로 돈다.

회귀 표적은 전부 "조용히 문서가 상하는" 경우다.

  1. 토글 자식을 안 받은 채 넘기면 내용이 통째로 빠진다 → unresolved 로 드러나야 함
  2. 모르는 블록 타입을 말없이 버리면 문서가 짧아진다 → unsupported 로 드러나야 함
  3. properties 를 표로 내면 분류 메타가 답변 본문에 노출된다 → `키: 값` 라인이어야 함
  4. 이미지 URL 을 놓치면 자산 매핑이 깨진다 → file/external 둘 다 잡아야 함
"""
from __future__ import annotations

from sync import ir
from sync.notion import (blocks_to_ir, page_title, property_lines, remote_page,
                         rich_text, to_document)


def rt(text: str):
    return [{"plain_text": text, "text": {"content": text}}]


def para(text: str, **kw):
    return {"type": "paragraph", "paragraph": {"rich_text": rt(text)}, **kw}


PAGE = {
    "id": "3560163e-cf14-80a2-937d-d04e8f54db87",
    "last_edited_time": "2026-08-19T01:23:45.000Z",
    "properties": {
        "FAQ": {"type": "title", "title": rt("전자출결은 어떻게 하나요")},
        "메뉴명": {"type": "select", "select": {"name": "출결"}},
        "시기": {"type": "select", "select": {"name": "2.학기중"}},
        "연번": {"type": "number", "number": 12},
        "태그": {"type": "multi_select", "multi_select": [{"name": "모바일"}, {"name": "앱"}]},
    },
}


# ── 기본 변환 ──────────────────────────────────────────────────────
def test_rich_text_falls_back_to_text_content():
    # MCP 구현에 따라 plain_text 없이 text.content 만 올 수 있다.
    assert rich_text([{"text": {"content": "가"}}, {"plain_text": "나"}]) == "가나"
    assert rich_text(None) == ""


def test_remote_page_normalizes_id_and_pulls_time():
    p = remote_page(PAGE)
    assert p.page_id == "3560163ecf1480a2937dd04e8f54db87"   # 하이픈 제거
    assert p.title == "전자출결은 어떻게 하나요"
    assert p.last_edited == "2026-08-19T01:23:45.000Z"


def test_page_title_finds_title_property_by_type():
    # DB 행은 제목 속성 이름이 제각각이다('FAQ', '이름', 'Name' …). 이름으로 찾으면 놓친다.
    assert page_title(PAGE) == "전자출결은 어떻게 하나요"


def test_headings_lists_divider_code():
    blocks, _, _ = blocks_to_ir([
        {"type": "heading_2", "heading_2": {"rich_text": rt("출결현황")}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rt("항목 하나")}},
        {"type": "numbered_list_item", "numbered_list_item": {"rich_text": rt("첫째")}},
        {"type": "divider", "divider": {}},
        {"type": "code", "code": {"rich_text": rt("print(1)")}},
    ])
    assert [b.type for b in blocks] == [ir.HEADING, ir.LIST, ir.LIST, ir.SEPARATOR, ir.CODE]
    assert blocks[0].level == 2
    assert blocks[2].ordered is True


def test_image_from_file_and_external():
    blocks, _, _ = blocks_to_ir([
        {"type": "image", "image": {"file": {"url": "https://s3/a.png"},
                                    "caption": rt("캡션")}},
        {"type": "image", "image": {"external": {"url": "https://cdn/b.png"}}},
    ])
    assert [b.src for b in blocks] == ["https://s3/a.png", "https://cdn/b.png"]
    assert blocks[0].text == "캡션"


def test_table_rows_from_children():
    blocks, _, _ = blocks_to_ir([{
        "type": "table", "table": {"table_width": 2},
        "children": [
            {"type": "table_row", "table_row": {"cells": [rt("메뉴"), rt("설명")]}},
            {"type": "table_row", "table_row": {"cells": [rt("출결"), rt("조회")]}},
        ],
    }])
    assert blocks[0].type == ir.TABLE
    assert blocks[0].rows == (("메뉴", "설명"), ("출결", "조회"))


def test_empty_paragraph_is_dropped():
    blocks, _, _ = blocks_to_ir([para(""), para("본문")])
    assert [b.text for b in blocks] == ["본문"]


# ── 조용히 상하는 경우를 드러내는가 ────────────────────────────────
def test_unfetched_children_are_reported():
    """토글 자식을 안 받았으면 반드시 드러나야 한다. 그냥 넘기면 내용이 사라진다."""
    blocks, unresolved, _ = blocks_to_ir([
        {"id": "blk-1", "type": "toggle", "toggle": {"rich_text": rt("접힌 제목")},
         "has_children": True},
    ])
    assert unresolved == ["blk-1"]
    assert [b.text for b in blocks] == ["접힌 제목"]     # 제목만 들어오고 속은 비었다


def test_fetched_children_are_flattened():
    blocks, unresolved, _ = blocks_to_ir([
        {"id": "blk-1", "type": "toggle", "toggle": {"rich_text": rt("접힌 제목")},
         "has_children": True, "children": [para("속 내용")]},
    ])
    assert unresolved == []
    assert [b.text for b in blocks] == ["접힌 제목", "속 내용"]


def test_unsupported_types_are_reported_not_swallowed():
    _, _, unsupported = blocks_to_ir([
        {"type": "embed", "embed": {"url": "https://x"}},
        {"type": "column_list", "column_list": {}},
        para("본문"),
    ])
    assert unsupported == ["column_list", "embed"]


def test_layout_only_types_are_silently_skipped():
    # 목차/행은 부모 처리에서 다루므로 '처리 못 함'이 아니다.
    blocks, _, unsupported = blocks_to_ir([
        {"type": "child_page", "child_page": {"title": "하위"}},
    ])
    assert blocks == () and unsupported == []


# ── properties → 메타 라인 ─────────────────────────────────────────
def test_property_lines_are_key_value_not_table():
    lines = property_lines(PAGE, ["메뉴명", "시기", "연번", "태그"])
    assert lines == ["메뉴명: 출결", "시기: 2.학기중", "연번: 12", "태그: 모바일, 앱"]


def test_property_lines_skip_missing_keys():
    assert property_lines(PAGE, ["없는속성"]) == []


def test_meta_lines_match_preprocess_regex():
    """실제로 ingest.preprocess 가 이 라인들을 지우는지 확인한다.

    형식이 어긋나면 분류 메타가 답변 본문에 그대로 노출된다(#24 회귀).
    """
    from ingest.preprocess import _META_HEADER_RE

    for line in property_lines(PAGE, ["메뉴명", "시기", "연번", "태그"]):
        assert _META_HEADER_RE.sub("", line + "\n") == "", line


# ── 문서 조립 ──────────────────────────────────────────────────────
def test_to_document_puts_meta_first():
    doc, unresolved, unsupported = to_document(
        PAGE, [para("답변 본문입니다")], meta_keys=["메뉴명"])
    assert doc.page_id == "3560163ecf1480a2937dd04e8f54db87"
    assert [b.text for b in doc.blocks] == ["메뉴명: 출결", "답변 본문입니다"]
    assert unresolved == [] and unsupported == []


def test_document_is_comparable_with_markdown_side():
    """노션에서 온 문서와 export 에서 온 문서가 같은 IR 로 비교되는지."""
    from sync.diff import diff_documents

    doc, _, _ = to_document(PAGE, [para("답변 본문입니다")])
    same = ir.Document(doc.page_id, doc.title, ir.from_markdown("답변 본문입니다\n"))
    assert not diff_documents(same, doc).changed
