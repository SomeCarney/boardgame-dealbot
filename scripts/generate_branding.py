"""Generates Facebook profile picture and cover photo for Board Game Black Market.

Output:
  branding/logo-die.svg          — the die mark (copied from docs/favicon.svg)
  branding/facebook-profile.png  — 800x800, upload as FB page profile picture
  branding/facebook-cover.png    — 1702x630, upload as FB page cover photo

Run: .venv\\Scripts\\python.exe scripts\\generate_branding.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRANDING_DIR = ROOT / "branding"

BG     = (18, 18, 18)
PANEL  = (28, 26, 23)
BORDER = (58, 51, 43)
GOLD   = (232, 185, 35)
GOLD_L = (240, 202, 74)   # lighter gold for top-face bevel
TEXT   = (236, 230, 214)
MUTED  = (168, 159, 140)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    paths = {
        "impact":  "C:/Windows/Fonts/impact.ttf",
        "arialbd": "C:/Windows/Fonts/arialbd.ttf",
    }
    try:
        return ImageFont.truetype(paths[name], size)
    except Exception:
        return ImageFont.load_default()


def _draw_die(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """Flat gold d6 with dark dots, matching the SVG favicon."""
    r = max(size // 7, 4)
    # Main gold body
    draw.rounded_rectangle([x, y, x + size, y + size], radius=r, fill=GOLD)
    # Lighter highlight on the top ~40% (bevel illusion)
    draw.rounded_rectangle([x, y, x + size, y + int(size * 0.42)], radius=r, fill=GOLD_L)
    draw.rectangle([x, y + r, x + size, y + int(size * 0.42)], fill=GOLD_L)
    # Six dots: 2 columns × 3 rows
    dot_r = max(size // 11, 3)
    pad   = size // 4
    for cx in [x + pad, x + size - pad]:
        for cy in [y + pad, y + size // 2, y + size - pad]:
            draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=PANEL)


def make_profile() -> None:
    """800×800 — Facebook crops profile pictures as a circle, so the die
    is centred with generous dark padding so nothing important gets clipped."""
    S = 800
    img  = Image.new("RGB", (S, S), PANEL)
    draw = ImageDraw.Draw(img)

    die  = 480
    dx   = (S - die) // 2
    dy   = (S - die) // 2 - 35
    _draw_die(draw, dx, dy, die)

    font = _font("impact", 50)
    text = "BOARD GAME BLACK MARKET"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw   = bbox[2] - bbox[0]
    draw.text(((S - tw) // 2, dy + die + 24), text, fill=GOLD, font=font)

    out = BRANDING_DIR / "facebook-profile.png"
    img.save(out, quality=95)
    print(f"Saved  {out.relative_to(ROOT)}")


def make_cover() -> None:
    """1702×630 — 2× retina of Facebook's recommended 851×315 display size."""
    W, H = 1702, 630
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Gold bottom bar
    draw.rectangle([0, H - 8, W, H], fill=GOLD)

    # Die on left
    die  = 390
    dx   = 80
    dy   = (H - die) // 2
    _draw_die(draw, dx, dy, die)

    # Vertical separator
    sep_x = dx + die + 72
    draw.rectangle([sep_x, 55, sep_x + 3, H - 55], fill=GOLD)

    # Text block
    tx = sep_x + 55

    tf  = _font("impact",  152)
    stf = _font("impact",  152)
    tgf = _font("arialbd",  40)

    ty = 72
    draw.text((tx, ty),            "BOARD GAME",   fill=TEXT,  font=tf)
    draw.text((tx, ty + 168),      "BLACK MARKET", fill=GOLD,  font=stf)
    draw.text((tx, ty + 168 + 178), "Underground deals  ·  no markup  ·  no nonsense.",
              fill=MUTED, font=tgf)

    out = BRANDING_DIR / "facebook-cover.png"
    img.save(out, quality=95)
    print(f"Saved  {out.relative_to(ROOT)}")


def copy_logo() -> None:
    src = ROOT / "docs" / "favicon.svg"
    dst = BRANDING_DIR / "logo-die.svg"
    shutil.copy2(src, dst)
    print(f"Copied {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    copy_logo()
    make_profile()
    make_cover()
    print("\nDone. Upload sizes:")
    print("  facebook-profile.png — set as Page profile picture (800×800)")
    print("  facebook-cover.png   — set as Page cover photo  (1702×630)")
