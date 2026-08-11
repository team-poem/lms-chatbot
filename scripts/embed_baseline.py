"""임베딩 유사도 분포 측정 — tuning.py 임계값 재보정의 근거.

tuning.py 의 ABS_EMBED_FLOOR/ABS_EMBED_CONFIDENT 는 BGE-M3 로 실측한 값이다.
임베딩 백엔드를 바꾸면 유사도 분포가 통째로 달라져 이 숫자들이 무의미해지므로,
전환 전후로 같은 질문셋을 돌려 분포를 다시 재야 한다.

  전환 전:  .venv/bin/python scripts/embed_baseline.py --out baseline-local.json
  전환 후:  EMBED_PROVIDER=gemini .venv/bin/python scripts/embed_baseline.py \
                --out baseline-gemini.json --compare baseline-local.json

질문셋은 둘로 나뉜다.
  - 매뉴얼 내(in): FAQ CSV 의 질문 원문. 실제 사용자 질문에 가장 가깝다.
  - 매뉴얼 밖(out): 학사/LMS 와 무관한 질문. 가드레일이 막아야 할 것들.

두 분포가 겹치지 않고 갈리는 지점이 임계값 후보다. 겹치면 그 임계값으로는
'진짜 질문 차단'과 '헛질문 환각' 중 하나를 반드시 겪는다.
"""
from __future__ import annotations
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from config import load_config  # noqa: E402
from index.embed import build_embed_config, load_embedder  # noqa: E402
from index.vector_store import get_chroma_client, query_embed  # noqa: E402

# 매뉴얼 밖 질문. LMS/CMS 매뉴얼이 답할 수 없는 것들로, 가드레일이 걸러야 한다.
# tuning.py 주석의 실측 사례('주차장' 0.57)를 포함한다.
OUT_OF_SCOPE = [
    "학교 주차장 요금이 얼마인가요",
    "오늘 학식 메뉴 알려줘",
    "졸업 학점은 몇 학점인가요",
    "장학금 신청 기간이 언제인가요",
    "기숙사 통금 시간이 어떻게 되나요",
    "휴학 신청은 어디서 하나요",
    "셔틀버스 시간표 알려줘",
    "도서관 열람실 예약하는 법",
    "복학하려면 뭘 해야 하나요",
    "등록금 분할납부 되나요",
    "피자 맛있게 만드는 법",
    "내일 날씨 어때",
]


def load_in_scope(csv_path: Path, limit: int | None) -> list[str]:
    """FAQ CSV 첫 컬럼(질문 원문)을 질문셋으로 쓴다."""
    df = pd.read_csv(csv_path)
    qs = [str(v).strip() for v in df[df.columns[0]] if str(v).strip() and str(v) != "nan"]
    return qs[:limit] if limit else qs


def top_score(client, embedder, query: str) -> float:
    hits = query_embed(client, embedder, query, k=1)
    return hits[0][1] if hits else 0.0


def summarize(name: str, scores: list[float]) -> dict:
    s = sorted(scores)
    return {
        "name": name,
        "n": len(s),
        "min": round(s[0], 4),
        "p10": round(s[max(0, len(s) // 10)], 4),
        "median": round(statistics.median(s), 4),
        "p90": round(s[min(len(s) - 1, len(s) * 9 // 10)], 4),
        "max": round(s[-1], 4),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, help="FAQ CSV 경로 (미지정 시 data/raw 에서 탐색)")
    ap.add_argument("--out", type=Path, help="결과 JSON 저장 경로")
    ap.add_argument("--compare", type=Path, help="이전 결과 JSON 과 비교 출력")
    ap.add_argument("--limit", type=int, help="매뉴얼 내 질문 개수 상한(빠른 확인용)")
    args = ap.parse_args(argv)

    config = load_config()
    csv_path = args.csv
    if csv_path is None:
        found = sorted(config.raw_dir.rglob("*.csv"))
        if not found:
            print("FAQ CSV 를 찾지 못했습니다. --csv 로 지정하세요.", file=sys.stderr)
            return 1
        csv_path = found[0]

    embed_cfg = build_embed_config()
    print(f"임베딩 백엔드: {embed_cfg.provider} / {embed_cfg.model}")
    embedder = load_embedder(embed_cfg)
    client = get_chroma_client(config.chroma_dir)

    in_qs = load_in_scope(csv_path, args.limit)
    in_scores = [top_score(client, embedder, q) for q in in_qs]
    out_scores = [top_score(client, embedder, q) for q in OUT_OF_SCOPE]

    result = {
        "provider": embed_cfg.provider,
        "model": embed_cfg.model,
        "in_scope": summarize("매뉴얼 내", in_scores),
        "out_of_scope": summarize("매뉴얼 밖", out_scores),
        # 분리도: 매뉴얼 내 하위 10%와 매뉴얼 밖 상위 10% 사이의 간격.
        # 양수면 그 사이 어딘가에 임계값을 놓을 수 있다. 음수면 겹친다.
        "separation": None,
        "worst_in_scope": [
            {"q": q, "score": round(s, 4)}
            for q, s in sorted(zip(in_qs, in_scores), key=lambda t: t[1])[:5]
        ],
        "best_out_of_scope": [
            {"q": q, "score": round(s, 4)}
            for q, s in sorted(zip(OUT_OF_SCOPE, out_scores), key=lambda t: -t[1])[:5]
        ],
    }
    gap = result["in_scope"]["p10"] - result["out_of_scope"]["p90"]
    result["separation"] = round(gap, 4)
    result["suggested_floor"] = round(
        (result["in_scope"]["p10"] + result["out_of_scope"]["p90"]) / 2, 4
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if gap <= 0:
        print(
            "\n⚠ 두 분포가 겹친다 — 단일 임계값으로 깨끗이 가를 수 없다. "
            "LLM 관련성 게이트에 더 의존해야 한다.",
            file=sys.stderr,
        )

    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n저장: {args.out}")

    if args.compare and args.compare.exists():
        prev = json.loads(args.compare.read_text(encoding="utf-8"))
        print(f"\n=== 비교: {prev['provider']}/{prev['model']} → {result['provider']}/{result['model']}")
        for key in ("in_scope", "out_of_scope"):
            for stat in ("min", "p10", "median", "p90", "max"):
                a, b = prev[key][stat], result[key][stat]
                print(f"  {key:14s} {stat:6s} {a:7.4f} → {b:7.4f}  ({b - a:+.4f})")
        print(f"  {'separation':14s} {'':6s} {prev['separation']:7.4f} → {result['separation']:7.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
