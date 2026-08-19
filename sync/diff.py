"""블록 단위 신구대조.

kordoc(https://github.com/chrisryugj/kordoc, MIT)의 `src/diff` 를 파이썬으로 옮겼다.
줄 단위 diff 를 쓰지 않는 이유는 노션 편집이 줄을 통째로 흔들기 때문이다 — 문단
하나에 단어를 더하면 줄바꿈 위치가 밀려 그 아래가 전부 '변경'으로 잡힌다. 블록을
유사도로 정렬하면 실제로 손댄 블록만 남는다.

상태는 넷이다. 사람이 문서를 볼 때 하는 판단과 같다.
  unchanged  그대로
  modified   같은 블록인데 내용이 바뀜
  added      노션에 새로 생김
  removed    노션에서 사라짐

원본에서 가져온 값과 그 이유:
  SIMILARITY_THRESHOLD 0.4   이 미만이면 '고친 것'이 아니라 '지우고 새로 쓴 것'
  UNCHANGED_THRESHOLD  0.99  공백 차이 정도는 같은 것으로 본다
  MAX_PAIRS            1e7   이 넘으면 LCS 를 포기하고 순서대로 짝지음(폭주 방지)
  MAX_LEVENSHTEIN_LEN  1e4   긴 문자열은 bigram Dice 로 근사(O(m·n) 회피)
"""
from __future__ import annotations

from dataclasses import dataclass

from sync.ir import TABLE, Block, Document, normalize

SIMILARITY_THRESHOLD = 0.4
UNCHANGED_THRESHOLD = 0.99
MAX_PAIRS = 10_000_000
MAX_LEVENSHTEIN_LEN = 10_000

UNCHANGED, MODIFIED, ADDED, REMOVED = "unchanged", "modified", "added", "removed"

def _bigram_counts(s: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in range(len(s) - 1):
        g = s[i : i + 2]
        out[g] = out.get(g, 0) + 1
    return out


def _approx_distance(a: str, b: str) -> int:
    """bigram 다중집합 Dice 유사도 기반 근사 거리.

    위치를 맞춰 표본 비교하는 방식은 앞쪽 삽입 하나에도 전량 불일치로 폭주한다.
    bigram 은 위치에 둔감해 그 오차가 없다(원본 주석의 교정 사유)."""
    ca, cb = _bigram_counts(a), _bigram_counts(b)
    inter = sum(min(n, cb.get(g, 0)) for g, n in ca.items())
    total = max(len(a) - 1, 0) + max(len(b) - 1, 0)
    dice = (2 * inter) / total if total > 0 else 1.0
    return round(max(len(a), len(b)) * (1 - dice))


def levenshtein(a: str, b: str) -> int:
    """편집 거리. 공간 O(min(m,n)). 너무 길면 근사로 넘긴다."""
    if len(a) + len(b) > MAX_LEVENSHTEIN_LEN:
        return _approx_distance(a, b)
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j in range(1, len(b) + 1):
        curr = [j] + [0] * len(a)
        for i in range(1, len(a) + 1):
            curr[i] = prev[i - 1] if a[i - 1] == b[j - 1] else 1 + min(
                prev[i - 1], prev[i], curr[i - 1]
            )
        prev = curr
    return prev[len(a)]


def similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return 1 - levenshtein(a, b) / max(len(a), len(b))


def normalized_similarity(a: str, b: str) -> float:
    return similarity(normalize(a), normalize(b))


def block_similarity(a: Block, b: Block) -> float:
    """타입이 다르면 0. 같은 타입이면 비교 텍스트의 정규화 유사도."""
    if a.type != b.type:
        return 0.0
    ta, tb = a.compare_text(), b.compare_text()
    if not ta and not tb:
        return 1.0          # separator 처럼 텍스트 없는 동일 타입
    return normalized_similarity(ta, tb)


def _fallback_align(a, b):
    """LCS 를 포기했을 때: 순서대로 짝지음. 정확도는 떨어져도 끝나기는 한다."""
    return [(a[i] if i < len(a) else None, b[i] if i < len(b) else None)
            for i in range(max(len(a), len(b)))]


def align_blocks(a: tuple[Block, ...], b: tuple[Block, ...]):
    """유사도 임계값을 만족하는 쌍으로 LCS 정렬 → (a블록|None, b블록|None) 목록."""
    m, n = len(a), len(b)
    if m * n > MAX_PAIRS:
        return _fallback_align(a, b)

    a_len = [len(normalize(x.compare_text())) for x in a]
    b_len = [len(normalize(x.compare_text())) for x in b]
    cache: dict[tuple[int, int], float] = {}

    def sim(i: int, j: int) -> float:
        key = (i, j)
        if key not in cache:
            # 길이비 프리필터. Levenshtein 하한(sim ≤ 1 − 길이차/max)으로 임계
            # 미달이 확정인 쌍은 계산 자체를 건너뛴다 — 전쌍 O(len²) 을 막는 핵심.
            mx = max(a_len[i], b_len[j])
            cut = 6 / 7 if TABLE in (a[i].type, b[j].type) else 1 - SIMILARITY_THRESHOLD
            cache[key] = (
                0.0
                if mx > 0 and (mx - min(a_len[i], b_len[j])) / mx > cut
                else block_similarity(a[i], b[j])
            )
        return cache[key]

    # dp 는 (짝지은 개수, 유사도 합). 개수가 같으면 유사도 합이 큰 정렬을 고른다.
    #
    # **원본과 다른 점이자 의도한 개선이다.** 원본은 개수만 최대화해서, 임계값을
    # 겨우 넘는 엉뚱한 짝도 동점이면 그대로 채택됐다. 실제로 문단을 뒤에 덧붙였을
    # 때 '첫 문단입니다' ↔ '뒤에 붙은 새 문단입니다'(유사도 0.417)가 짝으로 잡혀,
    # 손대지 않은 문단이 modified 로 보고됐다. 갱신 대조에서 이건 곧 "안 바뀐
    # 문서를 다시 인덱싱"으로 이어진다.
    dp = [[(0, 0.0)] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        row = dp[i]
        for j in range(1, n + 1):
            s = sim(i - 1, j - 1)
            if s >= SIMILARITY_THRESHOLD:
                c, acc = dp[i - 1][j - 1]
                diag = (c + 1, acc + s)
                row[j] = max(diag, dp[i - 1][j], row[j - 1])
            else:
                row[j] = max(dp[i - 1][j], row[j - 1])

    pairs: list[tuple[int, int]] = []
    i, j = m, n
    while i > 0 and j > 0:
        s = sim(i - 1, j - 1)
        c, acc = dp[i - 1][j - 1]
        if s >= SIMILARITY_THRESHOLD and dp[i][j] == (c + 1, acc + s):
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()

    out: list[tuple[Block | None, Block | None]] = []
    ai = bi = 0
    for pi, pj in pairs:
        while ai < pi:
            out.append((a[ai], None)); ai += 1
        while bi < pj:
            out.append((None, b[bi])); bi += 1
        out.append((a[ai], b[bi])); ai += 1; bi += 1
    while ai < m:
        out.append((a[ai], None)); ai += 1
    while bi < n:
        out.append((None, b[bi])); bi += 1
    return out


@dataclass(frozen=True)
class BlockDiff:
    type: str
    before: Block | None = None
    after: Block | None = None
    similarity: float = 0.0


@dataclass(frozen=True)
class DiffResult:
    diffs: tuple[BlockDiff, ...]
    added: int = 0
    removed: int = 0
    modified: int = 0
    unchanged: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    def summary(self) -> str:
        return (f"변경 {self.modified} · 추가 {self.added} · "
                f"삭제 {self.removed} · 유지 {self.unchanged}")


def diff_blocks(a: tuple[Block, ...], b: tuple[Block, ...]) -> DiffResult:
    """a(현재 인덱스) 대비 b(노션 최신) 의 블록 diff."""
    diffs: list[BlockDiff] = []
    counts = {ADDED: 0, REMOVED: 0, MODIFIED: 0, UNCHANGED: 0}
    for x, y in align_blocks(a, b):
        if x is not None and y is not None:
            s = block_similarity(x, y)
            kind = UNCHANGED if s >= UNCHANGED_THRESHOLD else MODIFIED
            diffs.append(BlockDiff(type=kind, before=x, after=y, similarity=s))
        elif x is not None:
            kind = REMOVED
            diffs.append(BlockDiff(type=kind, before=x))
        else:
            kind = ADDED
            diffs.append(BlockDiff(type=kind, after=y))
        counts[kind] += 1
    return DiffResult(tuple(diffs), counts[ADDED], counts[REMOVED],
                      counts[MODIFIED], counts[UNCHANGED])


def diff_documents(before: Document, after: Document) -> DiffResult:
    return diff_blocks(before.blocks, after.blocks)
