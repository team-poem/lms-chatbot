"""IR 변환과 블록 신구대조.

회귀 표적은 "조용히 틀리는" 쪽이다. 갱신 대조가 잘못되면 인덱스가 어긋난 채로도
아무 에러가 안 나고, 답변 품질로만 뒤늦게 드러난다.

  1. 문단 하나를 고쳤을 때 그 블록만 modified 로 잡히는가 (줄 밀림 전파 금지)
  2. 새 블록·삭제 블록이 added/removed 로 분리되는가
  3. 공백·줄바꿈 차이가 변경으로 잡히지 않는가
  4. 파일명에서 노션 page id 를 뽑아내는가 (로컬↔노션을 잇는 유일한 열쇠)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sync import diff as D
from sync import ir


def md(text: str):
    return ir.from_markdown(text)


# ── IR 변환 ────────────────────────────────────────────────────────
def test_headings_and_paragraphs():
    blocks = md("# 제목\n\n본문 첫 줄\n이어지는 줄\n\n## 소제목\n")
    assert [(b.type, b.level) for b in blocks] == [
        (ir.HEADING, 1), (ir.TEXT, 0), (ir.HEADING, 2)
    ]
    # 이어지는 줄은 한 문단으로 합쳐진다 — 줄바꿈 위치가 diff 를 흔들면 안 된다.
    assert blocks[1].text == "본문 첫 줄 이어지는 줄"


def test_list_and_image_and_separator():
    blocks = md("- 하나\n1. 둘\n\n![캡션](image%201.png)\n\n---\n")
    assert [b.type for b in blocks] == [ir.LIST, ir.LIST, ir.IMAGE, ir.SEPARATOR]
    assert blocks[1].ordered is True
    # 이미지 src 는 URL 인코딩된 그대로 둔다 — pipeline._rewrite_image_refs 가 unquote 한다.
    assert blocks[2].src == "image%201.png"


def test_table_needs_separator_row():
    blocks = md("| 메뉴 | 설명 |\n| --- | --- |\n| 출결 | 조회 |\n")
    assert blocks[0].type == ir.TABLE
    assert blocks[0].rows == (("메뉴", "설명"), ("출결", "조회"))


def test_pipe_in_prose_is_not_a_table():
    # 구분선 없이 '|' 만 있는 문장을 표로 오인하면 블록 경계가 통째로 어긋난다.
    blocks = md("출결 | 학습 현황 메뉴에서 확인합니다\n")
    assert blocks[0].type == ir.TEXT


def test_code_fence_is_one_block():
    blocks = md("```\nline1\nline2\n```\n")
    assert len(blocks) == 1 and blocks[0].type == ir.CODE
    assert blocks[0].text == "line1\nline2"


def test_page_id_from_filename():
    p = Path("CMS 매뉴얼 34f0163ecf148015a358db64b64d0784.md")
    assert ir.page_id_of(p) == "34f0163ecf148015a358db64b64d0784"
    assert ir.document_from_file.__doc__          # 시그니처 유지 확인용
    assert ir.page_id_of(Path("아이디없음.md")) == ""


# ── 유사도 ─────────────────────────────────────────────────────────
def test_whitespace_only_change_is_unchanged():
    a = md("출결현황 조회 및 관리\n")
    b = md("출결현황   조회 및\n관리\n")
    assert D.diff_blocks(a, b).unchanged == 1


def test_levenshtein_matches_known_values():
    assert D.levenshtein("kitten", "sitting") == 3
    assert D.levenshtein("", "abc") == 3
    assert D.similarity("abc", "abc") == 1.0
    assert D.similarity("", "abc") == 0.0


def test_long_input_falls_back_to_approx():
    # 근사 경로가 죽지 않고 0~1 유사도를 내는지만 본다(정확도는 보장 대상이 아니다).
    a, b = "가" * 8000, "가" * 7000 + "나" * 1000
    s = D.similarity(a, b)
    assert 0.0 <= s <= 1.0


# ── 신구대조 ───────────────────────────────────────────────────────
def test_edited_paragraph_does_not_shift_the_rest():
    """가운데 문단만 고쳤을 때 그 블록만 modified. 아래가 통째로 밀리면 안 된다."""
    a = md("# 제목\n\n첫 문단입니다\n\n둘째 문단입니다\n\n셋째 문단입니다\n")
    b = md("# 제목\n\n첫 문단입니다\n\n둘째 문단을 조금 고쳤습니다\n\n셋째 문단입니다\n")
    r = D.diff_blocks(a, b)
    assert (r.modified, r.added, r.removed) == (1, 0, 0)
    assert r.unchanged == 3


def test_new_and_deleted_blocks_split():
    a = md("첫 문단입니다\n\n사라질 문단입니다\n")
    b = md("첫 문단입니다\n\n완전히 다른 새 내용이 들어왔습니다\n")
    r = D.diff_blocks(a, b)
    # 유사도가 임계 미만이면 '고침'이 아니라 '지우고 새로 씀'으로 갈린다.
    assert (r.added, r.removed, r.modified) == (1, 1, 0)


def test_appended_block_is_added_only():
    a = md("첫 문단입니다\n")
    b = md("첫 문단입니다\n\n뒤에 붙은 새 문단입니다\n")
    r = D.diff_blocks(a, b)
    assert (r.added, r.removed, r.modified, r.unchanged) == (1, 0, 0, 1)


def test_identical_documents_report_no_change():
    text = "# 제목\n\n본문\n\n- 항목\n"
    r = D.diff_blocks(md(text), md(text))
    assert not r.changed and r.unchanged == 3


def test_type_change_is_not_a_modification():
    # 문단이 헤딩이 되면 같은 블록의 수정이 아니라 교체다.
    r = D.diff_blocks(md("출결현황\n"), md("## 출결현황\n"))
    assert (r.added, r.removed, r.modified) == (1, 1, 0)


def test_summary_is_readable():
    r = D.diff_blocks(md("가\n"), md("가\n\n나\n"))
    assert r.summary() == "변경 0 · 추가 1 · 삭제 0 · 유지 1"


@pytest.mark.parametrize("a,b,expect_changed", [("가나다\n", "가나다\n", False),
                                                ("가나다\n", "가나라\n", True)])
def test_changed_flag(a, b, expect_changed):
    assert D.diff_blocks(md(a), md(b)).changed is expect_changed
