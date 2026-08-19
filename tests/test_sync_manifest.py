"""로컬 장부와 문서 단위 대조 계획.

여기서 틀리면 "받아올 문서를 빠뜨린다"(인덱스가 조용히 낡음) 또는 "안 바뀐 걸
전부 받아온다"(임베딩 호출 낭비) 둘 중 하나가 된다. 둘 다 에러 없이 진행되므로
테스트로 못박는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sync import ir
from sync.manifest import (CHANGED, Entry, RemotePage, build_manifest,
                           content_hash, load_manifest, merge_manifest,
                           normalize_id, plan_sync, save_manifest)

ID_A = "34f0163ecf148015a358db64b64d0784"
ID_B = "3560163ecf1480a2937dd04e8f54db87"


def write(raw: Path, name: str, body: str) -> Path:
    p = raw / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    return d


# ── id 정규화 ──────────────────────────────────────────────────────
def test_normalize_id_absorbs_hyphens_and_case():
    # 노션 API 는 하이픈 있는 형태로 준다. export 파일명은 하이픈이 없다.
    assert normalize_id("34F0163E-CF14-8015-A358-DB64B64D0784") == ID_A


# ── 장부 만들기 ────────────────────────────────────────────────────
def test_build_manifest_keys_by_page_id(raw: Path):
    write(raw, f"CMS 매뉴얼 {ID_A}.md", "# CMS 매뉴얼\n\n본문\n")
    write(raw, f"하위/출결 {ID_B}.md", "# 출결\n\n- 항목\n")
    m = build_manifest(raw)
    assert set(m) == {ID_A, ID_B}
    assert m[ID_A].title == "CMS 매뉴얼"
    assert m[ID_B].path == f"하위/출결 {ID_B}.md"


def test_build_manifest_skips_files_without_id(raw: Path):
    # id 가 없으면 노션 페이지와 이을 방법이 없다. 조용히 넣으면 영원히 고아가 된다.
    write(raw, "손으로 만든 메모.md", "# 메모\n")
    assert build_manifest(raw) == {}


def test_content_hash_ignores_whitespace_but_not_content(raw: Path):
    a = ir.Document("x", "t", ir.from_markdown("본문 한 줄\n"))
    b = ir.Document("x", "t", ir.from_markdown("본문   한\n줄\n"))
    c = ir.Document("x", "t", ir.from_markdown("본문 두 줄\n"))
    assert content_hash(a) == content_hash(b)
    assert content_hash(a) != content_hash(c)


# ── 저장·복원·병합 ─────────────────────────────────────────────────
def test_manifest_roundtrip(tmp_path: Path, raw: Path):
    write(raw, f"CMS 매뉴얼 {ID_A}.md", "# CMS 매뉴얼\n\n본문\n")
    m = build_manifest(raw)
    p = tmp_path / "sync-manifest.json"
    save_manifest(p, m)
    assert load_manifest(p) == m


def test_load_missing_manifest_is_empty(tmp_path: Path):
    assert load_manifest(tmp_path / "없음.json") == {}


def test_merge_keeps_time_only_when_content_is_same(raw: Path):
    write(raw, f"CMS 매뉴얼 {ID_A}.md", "# CMS 매뉴얼\n\n본문\n")
    scanned = build_manifest(raw)
    stored = {ID_A: Entry(**{**scanned[ID_A].__dict__, "last_edited": "2026-08-01T00:00:00Z"})}
    assert merge_manifest(scanned, stored)[ID_A].last_edited == "2026-08-01T00:00:00Z"

    # 내용이 바뀌었으면 이전 시각을 물려주면 안 된다 — 물려주면 '안 바뀜'으로 오판한다.
    write(raw, f"CMS 매뉴얼 {ID_A}.md", "# CMS 매뉴얼\n\n본문이 달라졌다\n")
    rescanned = build_manifest(raw)
    assert merge_manifest(rescanned, stored)[ID_A].last_edited == ""


# ── 대조 계획 ──────────────────────────────────────────────────────
def _entry(pid: str, last_edited: str = "") -> Entry:
    return Entry(page_id=pid, path=f"{pid}.md", title="t", blocks=1,
                 content_hash="h", last_edited=last_edited)


def test_new_and_removed_split_by_id_set():
    local = {ID_A: _entry(ID_A, "2026-08-01T00:00:00Z")}
    remote = [RemotePage(ID_B, "새 문서", "2026-08-10T00:00:00Z")]
    plan = plan_sync(local, remote)
    assert [p.page_id for p in plan.new] == [ID_B]
    assert [e.page_id for e in plan.removed] == [ID_A]


def test_changed_when_remote_is_newer():
    local = {ID_A: _entry(ID_A, "2026-08-01T00:00:00Z")}
    remote = [RemotePage(ID_A, "문서", "2026-08-10T00:00:00Z")]
    assert [p.page_id for p in plan_sync(local, remote).changed] == [ID_A]


def test_unchanged_when_remote_is_not_newer():
    local = {ID_A: _entry(ID_A, "2026-08-10T00:00:00Z")}
    remote = [RemotePage(ID_A, "문서", "2026-08-10T00:00:00Z")]
    plan = plan_sync(local, remote)
    assert len(plan.unchanged) == 1 and not plan.needs_action


def test_first_run_is_all_unknown():
    """장부에 시각이 없으면 전부 unknown. 숨기지 말고 드러내야 한다."""
    local = {ID_A: _entry(ID_A)}          # last_edited 없음
    remote = [RemotePage(ID_A, "문서", "2026-08-10T00:00:00Z")]
    plan = plan_sync(local, remote)
    assert len(plan.unknown) == 1 and not plan.changed and not plan.unchanged


def test_remote_without_time_is_also_unknown():
    local = {ID_A: _entry(ID_A, "2026-08-01T00:00:00Z")}
    remote = [RemotePage(ID_A, "문서", "")]
    assert len(plan_sync(local, remote).unknown) == 1


def test_hyphenated_remote_id_matches_local():
    local = {ID_A: _entry(ID_A, "2026-08-10T00:00:00Z")}
    remote = [RemotePage("34f0163e-cf14-8015-a358-db64b64d0784", "문서",
                         "2026-08-10T00:00:00Z")]
    plan = plan_sync(local, remote)
    assert not plan.new and not plan.removed and len(plan.unchanged) == 1


def test_fetch_targets_and_summary():
    local = {ID_A: _entry(ID_A, "2026-08-01T00:00:00Z")}
    remote = [RemotePage(ID_A, "문서", "2026-08-10T00:00:00Z"),
              RemotePage(ID_B, "새 문서", "2026-08-10T00:00:00Z")]
    plan = plan_sync(local, remote)
    # 받아올 대상 = 신규 + 변경 + 확인필요. 이 수가 곧 API 호출 수다.
    assert {p.page_id for p in plan.fetch_targets} == {ID_A, ID_B}
    assert plan.summary() == "신규 1 · 변경 1 · 삭제 0 · 확인필요 0 · 유지 0"
