import zipfile
from pathlib import Path

from ingest.extract import unzip_all_recursive, collect_markdown, collect_csv


def test_unzip_terminates_when_extract_dir_name_differs_from_zip(tmp_path: Path):
    """Notion export 의 zip 추출 결과는 zip stem 과 다른 폴더로 떨어지므로
    stem-existence 기반 체크는 무한 루프를 일으킨다. marker 기반 체크 검증.
    """
    z = tmp_path / "weird-name_123.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Inner Folder/note.md", "# 테스트\n")
    unzip_all_recursive(tmp_path)
    assert (tmp_path / "Inner Folder" / "note.md").exists()
    assert (tmp_path / "weird-name_123.zip.extracted").exists()
    mtime = (tmp_path / "weird-name_123.zip.extracted").stat().st_mtime
    unzip_all_recursive(tmp_path)
    assert (tmp_path / "weird-name_123.zip.extracted").stat().st_mtime == mtime


def test_unzip_recursive_handles_nested_zip(tmp_path: Path):
    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("a.md", "# A\n")
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.write(inner, arcname="inner.zip")
    inner.unlink()
    unzip_all_recursive(tmp_path)
    mds = collect_markdown(tmp_path)
    assert any(p.name == "a.md" for p in mds)
