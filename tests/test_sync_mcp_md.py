"""MCP enhanced markdown → export 형 md 변환.

회귀 표적은 다운스트림 계약이다. 변환 결과가 실제 소비자(parse_toc,
_rewrite_image_refs 의 unquote 관례)와 맞물리는지를 직접 검증한다 — 형식을
글로 맞추는 게 아니라 소비자 함수에 태워본다.
"""
from __future__ import annotations

from urllib.parse import unquote

from generation.catalog import parse_toc
from sync.mcp_md import (TocEntry, page_id_from_url, page_markdown,
                         toc_markdown)

# 실제 MCP fetch 응답에서 그대로 딴 축약 픽스처.
TOC_FIXTURE = """\
<page url="https://app.notion.com/p/42c457931cd28376a857813f9ab4ecec">
<content>
<columns>
\t<column ratio="28.13">
\t\t# <span color="gray_bg">**LMS 상세 가이드 │교수자 용**</span>
\t\t![](https://prod-files-secure.s3.us-west-2.amazonaws.com/x/y/image.png?X-Amz-Expires=300)
\t</column>
</columns>
## 📁 **전체 메뉴 안내**  {color="yellow_bg"}
---
**🟠 Learning X 첫 시작**
<page url="https://app.notion.com/p/d01457931cd2838bbcad814cc51d05ba">LearningX LMS 이용 환경</page>
<empty-block/>
<columns>
\t<column ratio="50">
\t\t## **📁 주차학습** {color="yellow_bg"}
\t\t---
\t\t<page url="https://app.notion.com/p/276457931cd2834f9bae013093b618db">주차학습 개요 및 구성</page>
\t\t<page url="https://app.notion.com/p/d7b457931cd2835fa94981b69e338b7f">학습 활동 - 과제 추가하기 (📄)</page>
\t</column>
\t<column ratio="50">
\t\t## **📁출결현황** {color="yellow_bg"}
\t\t---
\t\t<page url="https://app.notion.com/p/bc1457931cd283609158817629083ab3">출결현황 조회 및 관리 (📄)</page>
\t</column>
</columns>
</content>
</page>
"""

BODY_FIXTURE = """\
<content>
<callout icon="👉🏻">
\t주차학습 메뉴는 수업 정보를 한 눈에 파악할 수 있는 메뉴입니다. <br>교수는 간편하게 등록할 수 있습니다.
</callout>
<table_of_contents color="gray"/>
<empty-block/>
### <span color="blue">주차학습 개요</span>
![](https://prod-files-secure.s3.us-west-2.amazonaws.com/ws/blob1/Untitled.png?X-Amz-Expires=300&sig=a)
1. 강의 유형별 다른 아이콘으로 구분하여 표시됩니다.
- 동영상, 화상강의, 오프라인 출결
![](https://prod-files-secure.s3.us-west-2.amazonaws.com/ws/blob2/Untitled.png?X-Amz-Expires=300&sig=b)
<page url="https://app.notion.com/p/aaa457931cd2835fa94981b69e338b7f">과제 추가하기</page>
</content>
"""


def test_page_id_from_url():
    assert page_id_from_url(
        "https://app.notion.com/p/276457931cd2834f9bae013093b618db?pvs=204"
    ) == "276457931cd2834f9bae013093b618db"
    assert page_id_from_url("https://example.com/no-id") == ""


# ── TOC ────────────────────────────────────────────────────────────
def test_toc_survives_parse_toc():
    """변환 결과를 실제 parse_toc 에 태운다 — 최종 소비자가 검증자다."""
    md, _ = toc_markdown(TOC_FIXTURE, "LMS 매뉴얼")
    cats = {c.name: c for c in parse_toc(md)}
    # 볼드 소제목을 가진 '전체 메뉴 안내' 는 메타 네비로 제외된다.
    assert set(cats) == {"주차학습", "출결현황"}
    assert cats["주차학습"].docs == ("주차학습 개요 및 구성", "학습 활동 - 과제 추가하기")
    assert cats["출결현황"].docs == ("출결현황 조회 및 관리",)


def test_toc_collects_child_entries_in_order():
    _, entries = toc_markdown(TOC_FIXTURE, "LMS 매뉴얼")
    assert entries[0] == TocEntry("d01457931cd2838bbcad814cc51d05ba",
                                  "LearningX LMS 이용 환경")
    assert [e.title for e in entries] == [
        "LearningX LMS 이용 환경", "주차학습 개요 및 구성",
        "학습 활동 - 과제 추가하기 (📄)", "출결현황 조회 및 관리 (📄)",
    ]


def test_toc_drops_hr_and_decoration():
    """'---' 를 남기면 parse_toc 가 '---' 라는 유령 문서를 만든다."""
    md, _ = toc_markdown(TOC_FIXTURE, "LMS 매뉴얼")
    assert "---" not in md
    assert "prod-files-secure" not in md      # 장식 이미지도 버린다


# ── 본문 ───────────────────────────────────────────────────────────
def test_body_keeps_callout_text_drops_tags():
    r = page_markdown(BODY_FIXTURE, "주차학습 개요 및 구성", asset_dir="주차학습 abc")
    assert "주차학습 메뉴는 수업 정보를 한 눈에 파악할 수 있는 메뉴입니다." in r.markdown
    assert "<callout" not in r.markdown and "<table_of_contents" not in r.markdown


def test_body_headings_lose_span():
    r = page_markdown(BODY_FIXTURE, "t", asset_dir="d")
    assert "### 주차학습 개요" in r.markdown
    assert "<span" not in r.markdown


def test_body_images_rewritten_and_listed():
    r = page_markdown(BODY_FIXTURE, "t", asset_dir="주차학습 abc")
    assert len(r.images) == 2
    # 같은 파일명(Untitled.png)이라도 seq 로 갈라져야 한다 — 덮어쓰면 이미지가 사라진다.
    urls, names = zip(*r.images)
    assert len(set(names)) == 2
    assert all(u.startswith("https://prod-files-secure") for u in urls)


def test_body_image_ref_matches_pipeline_unquote():
    """md 안의 참조는 URL 인코딩, unquote 하면 실제 경로 — export 관례 그대로."""
    r = page_markdown(BODY_FIXTURE, "t", asset_dir="주차학습 abc")
    ref = next(l for l in r.markdown.splitlines() if l.startswith("!["))
    path = ref[4:-1]                        # ![](...) 안쪽
    assert "%20" in path                    # 공백이 인코딩돼 있다
    assert unquote(path).startswith("주차학습 abc/")


def test_body_page_link_becomes_plain_title():
    r = page_markdown(BODY_FIXTURE, "t", asset_dir="d")
    assert "과제 추가하기" in r.markdown
    assert "<page" not in r.markdown
