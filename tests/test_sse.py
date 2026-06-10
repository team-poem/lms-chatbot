"""SSE 직렬화 고정 테스트. backend._serialize_sse 의 출력 JSON 을 바이트 수준으로
고정한다 — asdict 단순화(리팩터링) 전후로 포맷이 변하지 않음을 보장."""
from app_types import ChatEvent, Source
from backend import _serialize_sse


def test_serialize_text_event():
    line = _serialize_sse(ChatEvent(type="text", delta="안녕"))
    assert line == (
        'data: {"type": "text", "delta": "안녕", "text": "", "images": [], '
        '"sources": [], "score": 0.0, "turn_id": null}\n\n'
    )


def test_serialize_done_event_with_nested_dataclass_and_tuples():
    evt = ChatEvent(
        type="done",
        images=("/assets/a.png",),
        sources=(Source(title="출결 관리", url="https://www.notion.so/x"),),
        score=0.5,
    )
    assert _serialize_sse(evt) == (
        'data: {"type": "done", "delta": "", "text": "", '
        '"images": ["/assets/a.png"], '
        '"sources": [{"title": "출결 관리", "url": "https://www.notion.so/x"}], '
        '"score": 0.5, "turn_id": null}\n\n'
    )


def test_serialize_plain_dict_passthrough():
    assert _serialize_sse({"type": "x"}) == 'data: {"type": "x"}\n\n'
