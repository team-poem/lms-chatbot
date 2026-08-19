"""static/img/bot.svg 와 같은 로봇 아이콘을 PNG 로 그린다.

SVG 를 그대로 쓰지 않고 다시 그리는 이유: Notion 이미지 블록은 SVG 렌더가 들쭉날쭉
하고, 브라우저 탭 아이콘도 PNG 쪽이 안전하다. 렌더러(rsvg/inkscape)를 새로 깔지
않으려고 Pillow 로 같은 도형을 직접 그린다 — 의존성은 이미 있는 것만 쓴다.

  .venv/bin/python scripts/make_bot_icon.py

SVG 를 고치면 이 파일도 함께 고쳐야 한다. 둘은 자동 동기화되지 않는다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

CRIMSON = (197, 17, 48, 255)
WHITE = (255, 255, 255, 255)
OUT = Path(__file__).resolve().parent.parent / "static" / "img"

# 4배로 그린 뒤 줄여서 계단현상을 없앤다(Pillow 에는 안티에일리어싱 그리기가 없다).
S = 4
SIZE = 128 * S
W = 6 * S   # 선 두께


def draw(d: ImageDraw.ImageDraw) -> None:
    d.ellipse((0, 0, SIZE - 1, SIZE - 1), fill=CRIMSON)

    def sc(*xs):                       # 128 기준 좌표 → 실제 픽셀
        return tuple(x * S for x in xs)

    d.line(sc(64, 24, 64, 34), fill=WHITE, width=W)          # 안테나
    d.ellipse(sc(60, 17, 68, 25), fill=WHITE)                # 안테나 끝
    d.rounded_rectangle(sc(34, 36, 94, 82), radius=12 * S,   # 머리
                        outline=WHITE, width=W)
    d.line(sc(28, 54, 28, 66), fill=WHITE, width=W)          # 왼쪽 귀
    d.line(sc(100, 54, 100, 66), fill=WHITE, width=W)        # 오른쪽 귀
    d.line(sc(52, 82, 52, 96, 68, 82), fill=WHITE, width=W,  # 말풍선 꼬리
           joint="curve")
    d.ellipse(sc(46, 52, 58, 64), fill=WHITE)                # 눈
    d.ellipse(sc(70, 52, 82, 64), fill=WHITE)


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw(ImageDraw.Draw(img))
    OUT.mkdir(parents=True, exist_ok=True)
    for px in (512, 192, 64, 32):
        img.resize((px, px), Image.LANCZOS).save(OUT / f"bot-{px}.png")
    print("wrote", ", ".join(f"bot-{p}.png" for p in (512, 192, 64, 32)))


if __name__ == "__main__":
    main()
