"""Dockerfile 이 런타임 import 폐포를 전부 담는지.

2026-08-12: ratelimit.py 를 추가하면서 Dockerfile 의 루트 모듈 COPY 목록을 갱신하지
못했다. backend.py 가 이를 import 하므로 이미지가 부팅 즉시 ModuleNotFoundError 로
죽는데, **파이썬 테스트는 전부 통과한다** — 로컬에는 파일이 있기 때문이다. 빌드해서
컨테이너를 띄워야만 드러나는 종류다.

바로 그 COPY 줄 위에 같은 위험을 경고하는 주석이 이미 있었는데도 놓쳤다. 주의력
대신 여기서 강제한다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"

# 런타임에 쓰이지 않는 루트 .py 가 생기면 여기에 적는다(이미지에 넣을 이유가 없다).
NOT_SHIPPED: set[str] = set()


def _copied_paths() -> set[str]:
    """Dockerfile 의 COPY 구문이 담는 경로(파일명·디렉터리명)."""
    out: set[str] = set()
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^COPY\s+(?:--from=\S+\s+)?(.*)$", line.strip())
        if not m:
            continue
        parts = m.group(1).split()
        out.update(parts[:-1])          # 마지막은 목적지
    return out


def test_all_root_modules_are_copied_into_image():
    """루트 .py 가 하나라도 빠지면 컨테이너가 부팅 즉시 죽는다."""
    on_disk = {p.name for p in ROOT.glob("*.py")} - NOT_SHIPPED
    copied = _copied_paths()
    missing = sorted(on_disk - copied)
    assert not missing, (
        f"Dockerfile COPY 에 빠진 루트 모듈: {missing}. "
        "backend import 단계에서 ModuleNotFoundError 로 컨테이너가 죽는다."
    )


def test_all_runtime_packages_are_copied_into_image():
    """런타임 패키지 디렉터리도 마찬가지다."""
    packages = {
        p.name for p in ROOT.iterdir()
        if p.is_dir() and (p / "__init__.py").exists() and not p.name.startswith(".")
    }
    # 테스트 패키지는 이미지에 넣지 않는다(.dockerignore).
    packages -= {"tests"}
    missing = sorted(packages - _copied_paths())
    assert not missing, f"Dockerfile COPY 에 빠진 런타임 패키지: {missing}"


def test_dockerignore_does_not_exclude_shipped_code():
    """data/ 나 tests/ 를 제외하는 것은 의도적이지만, 런타임 코드가 걸리면 안 된다."""
    ignored = {
        ln.strip().rstrip("/")
        for ln in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    }
    shipped = {p.name for p in ROOT.glob("*.py")} - NOT_SHIPPED
    collide = sorted(shipped & ignored)
    assert not collide, f".dockerignore 가 런타임 모듈을 제외한다: {collide}"
