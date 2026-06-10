"""첫 진입 화면용 FAQ 질문. 노션 교수자 매뉴얼의 FAQ DATABASE CSV(원본)를
런타임에 읽어 질문을 뽑는다 — 값을 코드에 박지 않으므로, FAQ가 바뀌면 CSV만
교체하고 서버를 재시작하면 반영된다(코드 수정 불필요). 첫 진입 시 이 중 5~7개를
무작위로 뽑아 칩으로 보여준다."""
from __future__ import annotations
import csv
import random
from functools import lru_cache
from pathlib import Path

from config import load_config
from tuning import FAQ_ENTRY_MAX, FAQ_ENTRY_MIN

# FAQ DATABASE CSV 의 질문 컬럼명(Notion export 헤더).
_FAQ_COLUMN = "FAQ"
# Notion export 파일명은 재export 시 해시가 바뀌므로 고정 경로 대신 패턴으로 찾는다.
_FAQ_CSV_GLOB = "**/*FAQ DATABASE*_all.csv"


def parse_questions(csv_path: Path) -> tuple[str, ...]:
    """FAQ DATABASE CSV 의 질문 컬럼을 등장 순서대로, 빈 값·중복 제외하고 읽는다.
    (헤더에 BOM 이 붙는 Notion export 대비 utf-8-sig)"""
    out: list[str] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            q = (row.get(_FAQ_COLUMN) or "").strip()
            if q and q not in out:
                out.append(q)
    return tuple(out)


def _find_faq_csv(raw_dir: Path) -> Path | None:
    matches = sorted(raw_dir.glob(_FAQ_CSV_GLOB))
    return matches[0] if matches else None


@lru_cache(maxsize=1)
def load_questions() -> tuple[str, ...]:
    """raw_dir 에서 FAQ DATABASE CSV 를 찾아 질문을 읽는다(없으면 빈 튜플 — 첫 진입
    제안은 graceful 하게 생략된다). 프로세스 수명 동안 1회만 읽어 캐시한다."""
    path = _find_faq_csv(load_config().raw_dir)
    return parse_questions(path) if path else ()


def pick(pool: tuple[str, ...], n: int) -> list[str]:
    """pool 에서 무작위 n개를 중복 없이 뽑는다. n 을 [0, len(pool)] 로 자른다."""
    n = max(0, min(n, len(pool)))
    return random.sample(pool, n)


def sample_questions(n: int) -> list[str]:
    return pick(load_questions(), n)


def sample_for_entry() -> list[str]:
    """첫 진입용: 5~7개 사이 무작위 개수만큼 뽑는다."""
    return pick(load_questions(), random.randint(FAQ_ENTRY_MIN, FAQ_ENTRY_MAX))
