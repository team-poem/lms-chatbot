"""Notion MCP fetch 원문 → data/raw 의 export 형 md + 이미지 즉시 다운로드.

사용:
  .venv/bin/python scripts/mcp_ingest_doc.py <원문파일> <page_id> "<제목>" [<매뉴얼 폴더>]

<원문파일> 은 MCP fetch 응답 text 의 <content>…</content> 구간을 그대로 저장한
파일이다(한 글자도 바꾸지 말 것 — 이미지 서명 URL 이 깨지면 다운로드가 전부
실패한다). <매뉴얼 폴더> 기본값은 'LMS 매뉴얼'.

이미지 URL 은 fetch 후 수 분 내 만료되므로 fetch → 이 스크립트 실행을 지체 없이
이어야 한다. 실패한 이미지가 있으면 종료코드 1 — 그 문서만 fetch 부터 다시 한다.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sync.mcp_md import page_markdown  # noqa: E402


def main() -> int:
    raw_file, pid, title = sys.argv[1], sys.argv[2], sys.argv[3]
    folder = sys.argv[4] if len(sys.argv) > 4 else "LMS 매뉴얼"
    # 파일명에 못 들어가는 '/' 는 '-' 로 — 그대로 두면 경로 구분자로 먹혀 md 가
    # 중첩 폴더에 쪼개져 저장되고, 에러 없이 '성공'으로 보인다(2026-08-19 실측 13건).
    title = re.sub(r"\s+", " ", title.replace("/", "-").replace("\\", "")).strip()

    raw = Path(raw_file).read_text(encoding="utf-8")
    asset_dir = f"{title} {pid}"
    base = ROOT / "data/raw/Private & Shared" / folder

    r = page_markdown(raw, title, asset_dir=asset_dir)
    (base / asset_dir).mkdir(parents=True, exist_ok=True)
    (base / f"{title} {pid}.md").write_text(r.markdown, encoding="utf-8")

    fail = 0
    for url, fname in r.images:
        out = base / asset_dir / fname
        rc = subprocess.run(["curl", "-sf", "-m", "30", "-o", str(out), url]).returncode
        if rc != 0 or not out.exists() or out.stat().st_size == 0:
            fail += 1
            print(f"  FAIL {fname}")
    print(f"{title}: md {len(r.markdown)}B, 이미지 {len(r.images) - fail}/{len(r.images)}"
          + (f", 못 다룬 태그 {r.dropped_tags}" if r.dropped_tags else ""))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
