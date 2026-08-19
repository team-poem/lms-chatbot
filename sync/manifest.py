"""로컬 장부와 문서 단위 대조 계획.

`sync/diff.py` 는 문서 **한 장**을 여는 도구다. 그 앞에 "어느 문서를 열어야
하는가"가 필요하다. 123개를 전부 받아 블록 대조하는 것은 낭비고, 노션 API 호출도
그만큼 늘어난다.

문서 단위 판단은 집합 연산과 시각 비교로 끝난다 — 모델이 낄 자리가 없다.

  new       노션에 있는데 로컬에 없다        → 받아서 추가
  removed   로컬에 있는데 노션에 없다        → 인덱스에서 빼야 한다
  changed   last_edited_time 이 장부보다 최신 → 받아서 블록 대조
  unknown   장부에 시각이 없다              → 받아서 블록 대조(첫 실행)
  unchanged 나머지                          → 건드리지 않는다

**첫 실행은 전부 unknown 이다.** 지금 export 를 언제 떴는지 기록이 없기 때문이고,
이건 숨길 게 아니라 드러내야 한다. 한 번 돌면 시각이 장부에 남아 그다음부터
changed/unchanged 가 갈린다.

page_id 는 export 파일명 끝 32자리 hex 에서 온다(`sync.ir.page_id_of`). 노션이
주는 id 는 하이픈이 섞여 있으므로 `normalize_id` 로 맞춘 뒤 비교한다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sync.ir import Document, document_from_file, normalize

MANIFEST_NAME = "sync-manifest.json"

NEW, REMOVED, CHANGED, UNKNOWN, UNCHANGED = (
    "new", "removed", "changed", "unknown", "unchanged",
)


def normalize_id(page_id: str) -> str:
    """노션 id 표기 흔들림 흡수: 하이픈 제거 + 소문자."""
    return page_id.replace("-", "").strip().lower()


def content_hash(doc: Document) -> str:
    """블록 내용만으로 만든 해시. 파일 mtime·경로 변화에는 흔들리지 않는다.

    diff 와 같은 정규화 기준(ir.normalize)을 쓴다 — 한쪽만 정규화하면 공백만 바뀐
    문서가 '내용 변경'으로 잡혀 last_edited 를 버리고 다시 받아오게 된다."""
    h = hashlib.sha256()
    for b in doc.blocks:
        h.update(b.type.encode())
        h.update(b"\0")
        h.update(normalize(b.compare_text()).encode())
        h.update(b"\n")
    return h.hexdigest()[:16]


@dataclass(frozen=True)
class Entry:
    page_id: str
    path: str            # raw_dir 기준 상대 경로
    title: str
    blocks: int
    content_hash: str
    # 이 문서를 마지막으로 받아왔을 때의 노션 수정 시각(ISO8601).
    # 첫 실행에서는 비어 있다 — 그래서 첫 판정이 unknown 이 된다.
    last_edited: str = ""


@dataclass(frozen=True)
class RemotePage:
    """노션 쪽 한 페이지. 어댑터(MCP/API)가 이 모양으로만 내놓으면 된다."""

    page_id: str
    title: str
    last_edited: str = ""


@dataclass(frozen=True)
class SyncPlan:
    new: tuple[RemotePage, ...] = ()
    removed: tuple[Entry, ...] = ()
    changed: tuple[RemotePage, ...] = ()
    unknown: tuple[RemotePage, ...] = ()
    unchanged: tuple[RemotePage, ...] = ()

    @property
    def fetch_targets(self) -> tuple[RemotePage, ...]:
        """실제로 본문을 받아와야 하는 것들. 이 수가 곧 API 호출 수다."""
        return self.new + self.changed + self.unknown

    @property
    def needs_action(self) -> bool:
        return bool(self.new or self.removed or self.changed or self.unknown)

    def summary(self) -> str:
        return (f"신규 {len(self.new)} · 변경 {len(self.changed)} · "
                f"삭제 {len(self.removed)} · 확인필요 {len(self.unknown)} · "
                f"유지 {len(self.unchanged)}")


def build_manifest(raw_dir: Path) -> dict[str, Entry]:
    """data/raw 를 훑어 현재 인덱스 상태를 장부로 만든다.

    id 가 없는 파일(export 가 아닌 손으로 둔 md 등)은 노션과 이을 수 없어 건너뛴다.
    """
    out: dict[str, Entry] = {}
    for md in sorted(raw_dir.rglob("*.md")):
        doc = document_from_file(md)
        if not doc.page_id:
            continue
        pid = normalize_id(doc.page_id)
        out[pid] = Entry(
            page_id=pid,
            path=str(md.relative_to(raw_dir)),
            title=doc.title,
            blocks=len(doc.blocks),
            content_hash=content_hash(doc),
        )
    return out


def load_manifest(path: Path) -> dict[str, Entry]:
    """저장된 장부를 읽는다. 없으면 빈 장부(첫 실행)."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: Entry(**v) for k, v in raw.get("entries", {}).items()}


def save_manifest(path: Path, entries: dict[str, Entry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "entries": {k: asdict(v) for k, v in entries.items()}}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def merge_manifest(scanned: dict[str, Entry],
                   stored: dict[str, Entry]) -> dict[str, Entry]:
    """디스크 스캔 결과에 저장된 last_edited 를 얹는다.

    스캔은 파일에서 나오므로 노션 수정 시각을 알 수 없다. 그 값만 이전 장부에서
    가져온다 — 스캔 쪽을 진실로 두되, 시각은 유일하게 장부에만 있는 정보다.
    """
    out: dict[str, Entry] = {}
    for pid, e in scanned.items():
        prev = stored.get(pid)
        keep = prev.last_edited if prev and prev.content_hash == e.content_hash else ""
        out[pid] = Entry(**{**asdict(e), "last_edited": keep})
    return out


def plan_sync(local: dict[str, Entry],
              remote: list[RemotePage] | tuple[RemotePage, ...]) -> SyncPlan:
    """장부 대 노션 목록 → 무엇을 받아와야 하는지."""
    buckets: dict[str, list] = {NEW: [], CHANGED: [], UNKNOWN: [], UNCHANGED: []}
    seen: set[str] = set()

    for page in remote:
        pid = normalize_id(page.page_id)
        seen.add(pid)
        entry = local.get(pid)
        if entry is None:
            buckets[NEW].append(page)
        elif not entry.last_edited or not page.last_edited:
            # 어느 한쪽이라도 시각을 모르면 내용으로 판단할 수밖에 없다.
            buckets[UNKNOWN].append(page)
        elif page.last_edited > entry.last_edited:
            buckets[CHANGED].append(page)
        else:
            buckets[UNCHANGED].append(page)

    removed = tuple(e for pid, e in local.items() if pid not in seen)
    return SyncPlan(
        new=tuple(buckets[NEW]),
        removed=removed,
        changed=tuple(buckets[CHANGED]),
        unknown=tuple(buckets[UNKNOWN]),
        unchanged=tuple(buckets[UNCHANGED]),
    )
