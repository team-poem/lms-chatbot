from generation.catalog import (
    Category,
    _clean_doc_label,
    _clean_heading,
    _is_bold_subheader,
    _manual_key,
    parse_toc,
)


# --- 제목/라벨 정리 ---

def test_clean_heading_strips_bold_emoji_space():
    assert _clean_heading("** 주차학습**") == "주차학습"
    assert _clean_heading("**** **글로벌 탐색 메뉴**") == "글로벌 탐색 메뉴"
    assert _clean_heading(" 시험 및 설문") == "시험 및 설문"
    assert _clean_heading("** 채점하기(SpeedGrader)**") == "채점하기(SpeedGrader)"


def test_clean_doc_label_plain():
    assert _clean_doc_label("주차학습 개요 및 구성") == "주차학습 개요 및 구성"


def test_clean_doc_label_broken_export_link():
    # '제목 ()%20<id>.md)' 형태 — 첫 % 이전까지 + 빈 괄호 정리
    line = "학습 활동 - 과제 추가하기 ()%2034f0163ecf14812ba0d5c62612d605af.md)"
    assert _clean_doc_label(line) == "학습 활동 - 과제 추가하기"


def test_clean_doc_label_title_with_real_parens():
    # 제목 자체에 괄호가 있고 그 뒤 URL 조각 — 괄호 보존
    line = "출결 상태 수동 변경(학습 인정 처리)%2034f0163ecf1481548344f8e0215f4af8.md)"
    assert _clean_doc_label(line) == "출결 상태 수동 변경(학습 인정 처리)"


def test_clean_doc_label_proper_markdown_link():
    line = "[[참고] 동영상 출결 상세 이력 확인하기](LMS%20%EB%A7%A4.md)"
    assert _clean_doc_label(line) == "[참고] 동영상 출결 상세 이력 확인하기"


def test_is_bold_subheader():
    assert _is_bold_subheader("** 메시지함**") is True
    assert _is_bold_subheader("주차학습 개요") is False
    assert _is_bold_subheader("****") is False


def test_manual_key():
    assert _manual_key("LMS 매뉴얼") == "LMS"
    assert _manual_key("CMS 매뉴얼") == "CMS"
    assert _manual_key("기타") == "기타"


# --- TOC 파싱 ---

_SAMPLE_TOC = """# LMS 매뉴얼

##  **전체 메뉴 안내**

** Learning X 첫 시작**

LearningX LMS 이용 환경

## ** 주차학습**

주차학습 개요 및 구성

학습 활동 - 과제 추가하기 ()%2034f0163ecf14812ba0d5c62612d605af.md)

## **출결현황**

출결현황 조회 및 관리 ()%2034f0163ecf14816d8d87d08ffe0f70bd.md)

출결 상태 수동 변경(학습 인정 처리)%2034f0163ecf1481548344f8e0215f4af8.md)
"""


def test_parse_toc_excludes_meta_section_with_bold():
    cats = parse_toc(_SAMPLE_TOC)
    names = [c.name for c in cats]
    # 볼드 소제목을 가진 '전체 메뉴 안내' 는 제외
    assert "전체 메뉴 안내" not in names
    assert names == ["주차학습", "출결현황"]


def test_parse_toc_collects_docs():
    cats = {c.name: c for c in parse_toc(_SAMPLE_TOC)}
    assert cats["주차학습"] == Category(
        name="주차학습",
        docs=("주차학습 개요 및 구성", "학습 활동 - 과제 추가하기"),
    )
    assert cats["출결현황"].docs == (
        "출결현황 조회 및 관리",
        "출결 상태 수동 변경(학습 인정 처리)",
    )


def test_parse_toc_empty():
    assert parse_toc("# 제목\n\n본문만 있음\n") == ()


# --- CMS 식(볼드 카테고리 + 링크) ---

_CMS_TOC = """# CMS 매뉴얼

**🏅 콘텐츠 등록하기**

[EverLec](CMS%20%EB%A7%A4%EB%89%B4%EC%96%BC/EverLec%2034f0163ecf148197b1f3e5ef7255cd20.md)

[MP4 동영상](CMS%20%EB%A7%A4%EB%89%B4%EC%96%BC/MP4%2034f0163ecf148197b1f3e5ef7255cd20.md)

**🏅 Cloud Editor 개요**

[Cloud Editor란?](CMS%20%EB%A7%A4%EB%89%B4%EC%96%BC/Cloud%2034f0163ecf148197b1f3e5ef7255cd20.md)
"""


def test_parse_toc_cms_bold_categories():
    cats = {c.name: c for c in parse_toc(_CMS_TOC)}
    assert list(cats) == ["콘텐츠 등록하기", "Cloud Editor 개요"]
    assert cats["콘텐츠 등록하기"].docs == ("EverLec", "MP4 동영상")
    assert cats["Cloud Editor 개요"].docs == ("Cloud Editor란?",)
