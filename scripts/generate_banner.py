"""Generates the u/90-Day-Average Reddit profile banner (1920x384), designed to
complement the avatar: same gold-on-dark brand palette, but where the avatar is
the "90" die icon, the banner carries the wordmark + tagline and the one motif
the avatar had no room for -- a declining price line (the 90-day average, below
which every posted deal sits).

Key content is centered/upper so it survives Reddit's mobile crop and the
avatar that overlaps the bottom-left corner.

    python scripts/generate_banner.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import image_compose as ic  # reuse the exact brand background

W, H = 1920, 384
OUT = Path(__file__).resolve().parent.parent / "branding" / "reddit_banner.png"

GOLD = ic.GOLD                 # (232, 185, 35)
GOLD_BRIGHT = (245, 208, 96)
GOLD_DIM = (196, 155, 24)
CREAM = ic.CREAM               # (236, 230, 214)
MUTED = (158, 146, 130)
FONT_IMPACT = "C:/Windows/Fonts/impact.ttf"
FONT_ARIAL_BOLD = "C:/Windows/Fonts/arialbd.ttf"


def _centered(draw, text, font, cx, y, fill, tracking=0):
    """Draw text centered on cx, with optional letter-spacing (tracking px)."""
    if tracking:
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = cx - total / 2
        for ch, w in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill)
            x += w + tracking
    else:
        w = draw.textlength(text, font=font)
        draw.text((cx - w / 2, y), text, font=font, fill=fill)


def make() -> None:
    canvas = ic._branded_canvas(W, H).convert("RGBA")
    draw = ImageDraw.Draw(canvas, "RGBA")

    # gold hairline along the very top, like the site's pinned rule
    draw.rectangle([0, 0, W, 5], fill=GOLD)

    # ── declining price line in the lower band (a price trending down, ending
    # at its low -- the whole "below the 90-day average" idea) ──
    pts = [(80, 268), (360, 292), (660, 286), (980, 312), (1300, 322),
           (1600, 346), (1850, 360)]  # gentle wiggle but clearly downward L->R
    # faint gold "chart" fill under the line
    fill_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(fill_layer).polygon(pts + [(W, H), (0, H)], fill=GOLD + (24,))
    canvas.alpha_composite(fill_layer)
    draw.line(pts, fill=GOLD + (165,), width=7, joint="curve")
    for i, (x, y) in enumerate(pts):
        r = 9 if i != len(pts) - 1 else 15
        col = GOLD_BRIGHT if i == len(pts) - 1 else GOLD
        draw.ellipse([x - r, y - r, x + r, y + r], fill=col + (210,))

    # ── wordmark + tagline, centered ─────────────────────────────────────────
    wm_font = ImageFont.truetype(FONT_IMPACT, 132)
    _centered(draw, "90-DAY AVERAGE", wm_font, W // 2, 74, GOLD, tracking=4)

    tag_font = ImageFont.truetype(FONT_ARIAL_BOLD, 40)
    _centered(draw, "Board game deals, checked against 90 days of real price history",
              tag_font, W // 2, 216, CREAM, tracking=1)

    sub_font = ImageFont.truetype(FONT_ARIAL_BOLD, 28)
    _centered(draw, "no inflated “list prices”  ·  no fake sales",
              sub_font, W // 2, 262, MUTED, tracking=2)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUT, "PNG")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    make()
