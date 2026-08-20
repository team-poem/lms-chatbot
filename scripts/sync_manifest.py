"""로컬 장부(sync-manifest.json) CLI — 노션 갱신 대조의 앞단.

  scan   data/raw 를 훑어 장부를 만들고 저장한다. 기존 장부의 last_edited 는
         내용 해시가 같은 문서에 한해 이어받는다(merge_manifest).
  plan   원격 목록 JSON([{page_id, title, last_edited?}, ...])과 대조해
         받아올 문서를 버킷별로 보고한다. 원격 목록은 노션 MCP 로 만든다
         (notion-sync 스킬 참조).
  hash   변환된 문서 하나의 내용 해시를 찍는다 — 받아온 문서가 실제로
         바뀌었는지(재인덱싱 필요 여부) 장부와 대조할 때 쓴다.

장부는 data/sync-manifest.json 에 둔다. 인덱스와 같은 이유로 git 에 안 들어간다
— 이 머신의 데이터 상태를 기술하는 파일이다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sync.ir import document_from_file  # noqa: E402
from sync.manifest import (MANIFEST_NAME, RemotePage, build_manifest,  # noqa: E402
                           content_hash, load_manifest, merge_manifest,
                           plan_sync, save_manifest)

RAW_DIR = ROOT / "data/raw"
MANIFEST = ROOT / "data" / MANIFEST_NAME


def cmd_scan() -> int:
    stored = load_manifest(MANIFEST)
    merged = merge_manifest(build_manifest(RAW_DIR), stored)
    save_manifest(MANIFEST, merged)
    stamped = sum(1 for e in merged.values() if e.last_edited)
    print(f"장부 저장: 문서 {len(merged)}개 (수정시각 보유 {stamped}) → {MANIFEST}")
    return 0


def cmd_plan(remote_json: str) -> int:
    remote_raw = json.loads(Path(remote_json).read_text(encoding="utf-8"))
    remote = [RemotePage(page_id=r["page_id"], title=r.get("title", ""),
                         last_edited=r.get("last_edited", "")) for r in remote_raw]
    plan = plan_sync(load_manifest(MANIFEST), remote)
    print(plan.summary())
    for name, items in (("신규", plan.new), ("변경", plan.changed),
                        ("확인필요", plan.unknown)):
        for p in items:
            print(f"  [{name}] {p.page_id} {p.title}")
    for e in plan.removed:
        print(f"  [삭제] {e.page_id} {e.title} ({e.path})")
    return 0


def cmd_hash(md_path: str) -> int:
    print(content_hash(document_from_file(Path(md_path))))
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("scan", "plan", "hash"):
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "scan":
        return cmd_scan()
    if cmd == "plan":
        return cmd_plan(sys.argv[2])
    return cmd_hash(sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(main())
