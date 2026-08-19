"""첫 진입 화면용 FAQ 질문. 노션 교수자 매뉴얼의 FAQ DATABASE CSV(원본)를
런타임에 읽어 질문을 뽑는다 — 값을 코드에 박지 않으므로, FAQ가 바뀌면 CSV만
교체하고 서버를 재시작하면 반영된다(코드 수정 불필요). 첫 진입 시 이 중 5~7개를
무작위로 뽑아 칩으로 보여준다."""
from __future__ import annotations
import csv
import random
import re
from functools import lru_cache
from pathlib import Path

from config import load_config
from tuning import FAQ_ENTRY_COUNT

# FAQ DATABASE CSV 의 질문 컬럼명(Notion export 헤더).
_FAQ_COLUMN = "FAQ"
# Notion export 파일명은 재export 시 해시가 바뀌므로 고정 경로 대신 패턴으로 찾는다.
# '_all' 쪽을 먼저 본다 — Notion 이 데이터베이스를 내보내면 뷰별 CSV(필터가 걸린
# 부분집합)와 전체 행이 담긴 `_all.csv` 가 함께 나오므로 전체 쪽이 옳다.
# 다만 **HTML export 에는 `_all.csv` 가 없다**(그 이름은 "Markdown & CSV" 형식에서만
# 나온다). 못 찾으면 `_all` 없는 CSV 로 물러선다 — 이 폴백이 없으면 HTML export 로
# 인덱싱한 배포에서 첫 진입 FAQ 칩이 조용히 통째로 비어버린다.
_FAQ_CSV_GLOBS = ("**/*FAQ DATABASE*_all.csv", "**/*FAQ DATABASE*.csv")


_FAQ_LABEL_RE = re.compile(r"\*{0,2}\s*답변\s*\*{0,2}\s*[:：]\s*")
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_BOLD_RE = re.compile(r"\*\*")


def plain_answer(text: str) -> str:
    """문서 본문을 화면에 그대로 띄울 평문으로 정리한다.

    프론트는 마크다운을 파싱하지 않는다 — `ui.setAnswerText` 가 escapeHtml 후
    innerHTML 에 넣으므로, 남은 마커는 렌더링되지 않고 **문자 그대로** 보인다.
    그래서 표시에 기여하지 않는 마커는 여기서 걷어낸다.

      - 제목('# …') 줄: 카드가 question 을 따로 보여줘 중복이다
      - 이미지 마크다운: 이미지는 card.images 로 별도 렌더된다. 남기면
        '![](/assets/Untitled.png)' 가 본문에 문자로 노출된다
      - 강조 '**': 평문 화면에선 별표 두 개로만 보인다

    표 구분자('|')는 남긴다 — 평문으로도 열 구분이 읽히고, 대안(공백 정렬)이
    더 낫다는 근거가 없다."""
    body = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    body = _MD_IMG_RE.sub("", body)
    body = _MD_BOLD_RE.sub("", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def faq_answer(text: str) -> str:
    """FAQ 본문에서 '답변' 텍스트만 뽑는다. FAQ 는 사람이 쓴 정답이라 LLM 으로
    재생성하면 질문 되풀이·원인 누락 등 손실이 생겨 원문을 그대로 쓴다.
    평문 정리(plain_answer)에 더해 '답변 :' 라벨 한 번을 떼어낸다."""
    body = plain_answer(text)
    body = _FAQ_LABEL_RE.sub("", body, count=1)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


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
    for pattern in _FAQ_CSV_GLOBS:
        matches = sorted(raw_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


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
    """첫 진입용: 5개를 뽑는다(개수 고정, 어느 5개인지는 아직 무작위)."""
    return pick(load_questions(), FAQ_ENTRY_COUNT)
