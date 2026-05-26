from __future__ import annotations
import shutil
import zipfile
from pathlib import Path


def unzip_all_recursive(raw_dir: Path) -> None:
    """data/raw 안의 모든 .zip 을 자기 위치에 풀어둔다. 안의 .zip 도 재귀."""
    while True:
        zips = list(raw_dir.rglob("*.zip"))
        if not zips:
            return
        progressed = False
        for z in zips:
            out = z.with_suffix("")
            if out.exists():
                continue
            with zipfile.ZipFile(z) as zf:
                zf.extractall(z.parent)
            progressed = True
        if not progressed:
            return


def collect_markdown(raw_dir: Path) -> list[Path]:
    return sorted(p for p in raw_dir.rglob("*.md") if p.is_file())


def collect_csv(raw_dir: Path) -> list[Path]:
    return sorted(p for p in raw_dir.rglob("*.csv") if p.is_file())


def collect_images(raw_dir: Path) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    return sorted(p for p in raw_dir.rglob("*") if p.suffix.lower() in exts)


def copy_assets(images: list[Path], raw_dir: Path, assets_dir: Path) -> dict[str, str]:
    """이미지를 assets_dir 평탄 복사. 원본 raw 경로 → /assets/<filename> 매핑 반환."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for src in images:
        dest_name = f"{src.parent.name[:8]}__{src.name}"
        dest = assets_dir / dest_name
        if not dest.exists():
            shutil.copy2(src, dest)
        rel = str(src.relative_to(raw_dir))
        mapping[rel] = f"/assets/{dest_name}"
    return mapping
