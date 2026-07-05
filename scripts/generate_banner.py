"""Generates the u/90-Day-Average Reddit profile banner (1920x384).

Reddit center-crops the banner hard (narrow card on desktop, worse on mobile),
so it carries NO text -- any wide wordmark loses its ends. Instead it's an
abstract, edge-to-edge price-chart motif in the brand palette: gold price lines
on the dark textured backdrop, trending down into bright "low" nodes (the whole
"below the 90-day average" idea). Because the pattern is uniform across the full
width, any crop still looks intentional. The avatar carries the name; this just
sets the mood and ties them together by palette.

    python scripts/generate_banner.py
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import image_compose as ic  # reuse the exact brand background

W, H = 1920, 384
OUT = Path(__file__).resolve().parent.parent / "branding" / "reddit_banner.png"

GOLD = ic.GOLD                 # (232, 185, 35)
GOLD_BRIGHT = (245, 208, 96)


def _wave(seed: int, mid: float, amp: float, drift: float, freq: float, n: int = 60):
    """A smooth left-to-right wavy line that bleeds past both edges (so a crop
    never shows a dangling end), with a gentle downward drift toward the right."""
    rnd = random.Random(seed)
    pts = []
    for i in range(n + 1):
        t = i / n
        x = -80 + (W + 160) * t
        y = mid + drift * t + amp * math.sin(i * freq + seed) + rnd.uniform(-6, 6)
        pts.append((x, y))
    return pts


def make() -> None:
    canvas = ic._branded_canvas(W, H).convert("RGBA")

    # ── faint background price line (depth) ──
    back = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(back)
    bpts = _wave(seed=7, mid=H * 0.42, amp=H * 0.11, drift=H * 0.10, freq=0.55)
    bd.line(bpts, fill=GOLD + (55,), width=5, joint="curve")
    canvas.alpha_composite(back.filter(ImageFilter.GaussianBlur(1.2)))

    # ── main price line + soft area fill beneath it ──
    pts = _wave(seed=3, mid=H * 0.60, amp=H * 0.12, drift=H * 0.14, freq=0.62)
    fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(fill).polygon(pts + [(W + 80, H + 80), (-80, H + 80)], fill=GOLD + (30,))
    canvas.alpha_composite(fill)

    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.line(pts, fill=GOLD + (180,), width=7, joint="curve")

    # bright "low" nodes at the local minima (each valley = a real price drop)
    for i in range(2, len(pts) - 2):
        if pts[i][1] > pts[i - 1][1] and pts[i][1] >= pts[i + 1][1]:
            x, y = pts[i]
            draw.ellipse([x - 11, y - 11, x + 11, y + 11], fill=GOLD_BRIGHT + (230,))
            draw.ellipse([x - 20, y - 20, x + 20, y + 20], outline=GOLD + (70,), width=3)

    # thin gold rules top and bottom to frame it (cropped away gracefully if lost)
    draw.rectangle([0, 0, W, 4], fill=GOLD)
    draw.rectangle([0, H - 4, W, H], fill=GOLD + (120,))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUT, "PNG")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    make()
