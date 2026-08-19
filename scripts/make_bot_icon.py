"""챗봇 아이콘과 "챗봇에게 질문하기" 배너를 PNG 로 그린다.

SVG 를 그대로 쓰지 않고 다시 그리는 이유: Notion 이미지 블록은 SVG 렌더가 들쭉날쭉
하고, 브라우저 탭 아이콘도 PNG 쪽이 안전하다. 렌더러(rsvg/inkscape)를 새로 깔지
않으려고 Pillow 로 같은 도형을 직접 그린다 — 의존성은 이미 있는 것만 쓴다.

  .venv/bin/python scripts/make_bot_icon.py

SVG 를 고치면 이 파일도 함께 고쳐야 한다. 둘은 자동 동기화되지 않는다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


# 배너: 빨간 원(로봇) + 옆에 문구. 노션 등 외부 문서에 붙여 클릭 유도용으로 쓴다.
LABEL = "챗봇에게 질문하기"
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
FONT_INDEX = 6            # Bold
DARK = (23, 25, 26, 255)  # --text


def _font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, px, index=FONT_INDEX)


def banner(filled: bool) -> Image.Image:
    """filled=False → 투명 배경 + 크림슨 글자, True → 크림슨 알약 + 흰 글자.

    두 벌을 내는 이유는 붙이는 자리의 배경색을 모르기 때문이다. 흰 바탕에는
    투명본이 가볍고, 어두운 바탕이나 버튼처럼 보이게 하려면 채운 쪽이 안전하다.
    """
    icon_px, pad, gap, text_px = 128, 28, 24, 56
    fnt = _font(text_px * S)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = int(tmp.textlength(LABEL, font=fnt))
    h = (icon_px + pad * 2) * S
    w = pad * S + icon_px * S + gap * S + tw + pad * S

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if filled:
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=CRIMSON)

    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw(ImageDraw.Draw(icon))
    if filled:
        # 채운 배경 위에서는 원판이 묻히므로 흰 원판에 크림슨 로봇으로 뒤집는다.
        icon = _invert(icon)
    img.paste(icon.resize((icon_px * S, icon_px * S), Image.LANCZOS),
              (pad * S, pad * S), icon.resize((icon_px * S, icon_px * S), Image.LANCZOS))

    d.text((pad * S + icon_px * S + gap * S, h // 2), LABEL,
           font=fnt, fill=(WHITE if filled else CRIMSON), anchor="lm")
    return img


def _invert(icon: Image.Image) -> Image.Image:
    """크림슨↔흰색을 맞바꾼다(원판만 흰색, 로봇은 크림슨)."""
    out = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    src, dst = icon.load(), out.load()
    for y in range(icon.size[1]):
        for x in range(icon.size[0]):
            r, g, b, a = src[x, y]
            if a == 0:
                continue
            dst[x, y] = (WHITE if (r, g, b) == CRIMSON[:3] else CRIMSON) if (r, g, b) in (CRIMSON[:3], WHITE[:3]) else (r, g, b, a)
    return out


def readme_banner() -> Image.Image:
    """README 히어로 배너 — 앱 테마(크림슨 원판·흰 로봇·Pretendard 계열) 그대로.

    크림슨 바탕이므로 아이콘은 흰 원판·크림슨 로봇으로 뒤집는다(_invert).
    하단의 어두운 띠는 앱 상단 크림슨 바(.topbar)의 반전 오마주다.
    """
    W, H = 1600 * 2, 400 * 2          # 2배로 그려 절반 축소(안티에일리어싱)
    img = Image.new("RGB", (W, H), CRIMSON[:3])
    d = ImageDraw.Draw(img)

    # 하단 악센트 띠 (primary-hover 색)
    d.rectangle((0, H - 24, W, H), fill=(155, 2, 29))

    # 아이콘: 흰 원판 + 크림슨 로봇
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw(ImageDraw.Draw(icon))
    icon = _invert(icon)
    icon_px = 480
    icon = icon.resize((icon_px, icon_px), Image.LANCZOS)

    title = "동서대학교 LMS 챗봇"
    subtitle = "LearningX 교수자 가이드 · e-Class"
    f_title = _font(150)
    f_sub = _font(56)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw = int(tmp.textlength(title, font=f_title))
    gap = 90
    total = icon_px + gap + tw
    x0 = (W - total) // 2

    img.paste(icon, (x0, (H - icon_px) // 2 - 20), icon)
    tx = x0 + icon_px + gap
    d.text((tx, H // 2 - 46), title, font=f_title, fill=WHITE[:3], anchor="lm")
    d.text((tx + 8, H // 2 + 106), subtitle, font=f_sub,
           fill=(255, 214, 221), anchor="lm")
    return img.resize((W // 2, H // 2), Image.LANCZOS)


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw(ImageDraw.Draw(img))
    OUT.mkdir(parents=True, exist_ok=True)
    for px in (512, 192, 64, 32):
        img.resize((px, px), Image.LANCZOS).save(OUT / f"bot-{px}.png")

    for filled, name in ((False, "ask-bot-banner.png"), (True, "ask-bot-banner-filled.png")):
        b = banner(filled)
        b.resize((b.width // S, b.height // S), Image.LANCZOS).save(OUT / name)

    readme_banner().save(OUT / "readme-banner.png")

    print("wrote bot-{512,192,64,32}.png, ask-bot-banner{,-filled}.png, readme-banner.png")


if __name__ == "__main__":
    main()
