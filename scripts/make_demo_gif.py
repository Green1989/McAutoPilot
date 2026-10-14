"""把三张仓库页面截图合成为 README 演示动图 docs/demo.gif。

用法:
    python scripts/make_demo_gif.py <目录>   # 目录需含 mcap_home.png / mcap_diary.png / mcap_actions.png

合成规则：统一缩放到 960 宽，底部加说明字幕条，每帧停留 3s，末尾加一帧结尾卡。
字体用系统微软雅黑（Windows）或黑体兜底。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 960
CAPTION_H = 64
FRAME_SECONDS = 3
END_SECONDS = 2

FRAMES = [
    ("mcap_home.png", "① 仓库：一个每天自己写日记的 GitHub 仓库"),
    ("mcap_diary.png", "② 《AI 吃饭日记》：每条决策附编号理由与营养台账"),
    ("mcap_actions.png", "③ GitHub Actions：每天 10:00 自动运行，全部 ✅"),
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/dejavu/NotoSansCJK-Regular.ttc",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def frame_with_caption(img: Image.Image, caption: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    scale = WIDTH / img.width
    resized = img.resize((WIDTH, round(img.height * scale)), Image.LANCZOS)
    canvas = Image.new("RGB", (WIDTH, resized.height + CAPTION_H), "#0d1117")
    canvas.paste(resized, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, resized.height, WIDTH, resized.height + CAPTION_H], fill="#1f6feb")
    bbox = draw.textbbox((0, 0), caption, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(
        ((WIDTH - tw) // 2, resized.height + (CAPTION_H - (bbox[3] - bbox[1])) // 2 - bbox[1]),
        caption, fill="white", font=font,
    )
    return canvas


def end_card(font: ImageFont.FreeTypeFont, big: ImageFont.FreeTypeFont) -> Image.Image:
    h = 420
    card = Image.new("RGB", (WIDTH, h), "#0d1117")
    draw = ImageDraw.Draw(card)
    draw.text((WIDTH // 2, 150), "Star 它 = 订阅一个 AI 的午饭人生", fill="white", font=big, anchor="mm")
    draw.text((WIDTH // 2, 230), "github.com/Green1989/McAutoPilot", fill="#58a6ff", font=font, anchor="mm")
    draw.text((WIDTH // 2, 300), "🍟 默认 dry-run · Token 只走 Secrets · 决策可解释", fill="#8b949e", font=font, anchor="mm")
    return card


def pad_to(img: Image.Image, width: int, height: int) -> Image.Image:
    if img.width != width:
        scale = width / img.width
        img = img.resize((width, round(img.height * scale)), Image.LANCZOS)
    if img.height == height:
        return img
    canvas = Image.new("RGB", (width, height), "#0d1117")
    canvas.paste(img, (0, (height - img.height) // 2))
    return canvas


def main() -> None:
    src_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    font = load_font(26)
    big = load_font(34)

    images: list[Image.Image] = []
    durations: list[int] = []
    for name, caption in FRAMES:
        path = src_dir / name
        if not path.exists():
            sys.exit(f"缺少截图: {path}")
        base = Image.open(path).convert("RGB")
        images.append(frame_with_caption(base, caption, font))
        durations.append(FRAME_SECONDS * 1000)

    card = end_card(font, big)
    images.append(card)
    durations.append(END_SECONDS * 1000)

    # 统一画布：等宽、按最高帧补 #0d1117 底色，避免播放跳动
    canvas_h = max(img.height for img in images)
    images = [pad_to(img, WIDTH, canvas_h) for img in images]

    out = Path(__file__).resolve().parent.parent / "docs" / "demo.gif"
    images[0].save(
        out, save_all=True, append_images=images[1:], duration=durations,
        loop=0, optimize=True,
    )
    print(f"已生成 {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
