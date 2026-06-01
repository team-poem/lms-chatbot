from __future__ import annotations
import re

from ingest.preprocess import strip_emoji


_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", flags=re.MULTILINE)

# 운두언 안전망: 본문 첫 문장이 인사·공감·확인 표현을 포함하면 그 문장 전체를 제거.
# LLM 이 페르소나 룰을 어겨도 사용자에게 노출되지 않도록 함. 룰 1의 금지 표현과 동기화.
_PREAMBLE_KEYWORDS = (
    # 호칭 / 인사 — 첫 문장에 등장하면 의미상 운두언으로 판정
    r"교수님|안녕하세요|반갑습니다|"
    # 명확한 운두언 표현 (substantive 답변에 잘 안 섞임)
    r"문의하신\s*내용|이해(?:했|하였)습니다|"
    r"질문\s*감사(?:합|드립)니다|"
    r"도움(?:이\s*되)?\s*드리겠(?:습니다|어요)|"
    # "다음과 같이 안내/답변/설명" 같은 정형 표현 (전체 매칭, 부분 단독 매칭 X)
    r"(?:아래|다음)과?\s*같이\s*(?:안내|답변|설명)(?:해?\s*)?(?:드)?(?:립|리겠습)니다|"
    r"안내(?:해\s*드)?리겠습니다|"  # 자체 의도 선언
    r"답변(?:해\s*)?드립니다|설명(?:해\s*)?드립니다|"
    # 사과/완충 표현
    r"불편하시?더라도|번거로우?시?겠지만|양해\s*부탁(?:드)?립니다|"
    r"우선\s*안내(?:해\s*)?(?:드)?립니다"
)
# 한 문장 = 종결 어미(다./요./오.) 또는 ./!/? 까지
_PREAMBLE_SENTENCE = re.compile(
    rf"^[^.!?\n]{{0,80}}(?:{_PREAMBLE_KEYWORDS})[^.!?\n]{{0,80}}[.!?]\s*"
)


def _strip_preamble(text: str) -> str:
    """본문 첫 문장에 운두언 표현이 있으면 문장째 제거. 여러 문장이 겹쳐 나올 수
    있어 변화가 없을 때까지 반복."""
    prev = None
    out = text
    while out != prev:
        prev = out
        out = _PREAMBLE_SENTENCE.sub("", out, count=1).lstrip()
    return out


# 글머리 기호(규칙 3): 줄 시작의 "- ", "• ", "* " 마커 제거 (숫자 리스트는 보존).
_BULLET = re.compile(r"^(\s*)[-•*]\s+", flags=re.MULTILINE)
# 호칭(규칙 1): 본문 중간의 "교수님" + 뒤따르는 조사 제거.
_KYOSUNIM = re.compile(r"교수님(?:께서|께|이|은|는|의|을|를|도)?\s*")


def _normalize_tone(text: str) -> str:
    """페르소나 규칙 1·2·3 위반을 결정적으로 후처리한다. LLM이 가이드 원문의
    부탁조·호칭·글머리 기호를 따라가도 사용자에게 노출되지 않게 한다."""
    # 규칙 3: 글머리 기호 제거
    text = _BULLET.sub(r"\1", text)
    # 규칙 1: "교수님" 호칭 제거
    text = _KYOSUNIM.sub("", text)
    # 규칙 2: 부탁·청유 종결 → 평서형.
    #   (a) "~해/하여 + 보조용언" : 평서 종결 "~합니다"로
    text = re.sub(r"하여\s*주시기\s*바랍니다", "합니다", text)
    text = re.sub(r"해\s*주시기\s*바랍니다", "합니다", text)
    text = re.sub(r"해\s*주십시오", "합니다", text)
    text = re.sub(r"해\s*주세요", "합니다", text)
    text = re.sub(r"해주시기\s*바랍니다", "합니다", text)
    text = re.sub(r"해주십시오", "합니다", text)
    text = re.sub(r"해주세요", "합니다", text)
    #   (b) 그 외 "<동사어간> + 보조용언" : 어간 변형을 피해 "~주면 됩니다"로
    text = re.sub(r"([가-힣])\s*주시기\s*바랍니다", r"\1 주면 됩니다", text)
    text = re.sub(r"([가-힣])\s*주십시오", r"\1 주면 됩니다", text)
    text = re.sub(r"([가-힣])\s*주세요", r"\1 주면 됩니다", text)
    return text


def clean_response(text: str) -> str:
    """완성된 텍스트에 대한 풀 클린업. 마크업 매칭은 양쪽 끝 마커가 모두
    있어야 가능하므로, 스트리밍 토큰에 바로 적용하면 누수가 발생함.
    스트리밍 중에는 streaming_clean 사용, 종료 후 full text 에 clean_response 적용."""
    text = strip_emoji(text)
    text = _BOLD.sub(lambda m: m.group(1), text)
    text = _ITALIC.sub(lambda m: m.group(1), text)
    text = _HEADING.sub("", text)
    text = _strip_preamble(text)
    text = _normalize_tone(text)
    return text


def streaming_clean(token: str) -> str:
    """토큰 단위 안전 클린업: 이모지만 제거 (단일 문자 단위, 토큰 경계 영향 없음).
    bold/italic/heading 은 토큰 경계 사이에 마커가 걸칠 수 있어 스트리밍에서는
    건드리지 않음. 종료 시 clean_response 로 일괄 클린한 결과를 별도 이벤트로 전송."""
    return strip_emoji(token)
