"""메뉴 클릭 시 보여줄 매뉴얼 문서를 청크에서 재조립한다(검색 우회).
같은 doc_title 청크를 seq 순으로 이어 붙이고, 이미지를 등장순 중복제거하며,
출처 URL 은 첫 notion_url 을 쓴다. 해당 문서가 없으면 None."""
from __future__ import annotations


def build_guide(chunks, doc_title: str) -> dict | None:
    matched = sorted(
        (c for c in chunks if c.doc_title == doc_title),
        key=lambda c: c.seq,
    )
    if not matched:
        return None
    text = "\n\n".join(c.text.strip() for c in matched if c.text.strip())
    images: list[str] = []
    for c in matched:
        for img in c.image_refs:
            if img and img not in images:
                images.append(img)
    source_url = next((c.notion_url for c in matched if c.notion_url), "")
    return {"title": doc_title, "text": text, "images": images, "source_url": source_url}
