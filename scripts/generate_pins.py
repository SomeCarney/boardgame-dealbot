"""Generates ready-to-upload Pinterest pins (1000x1500, the 2:3 pin ratio) from
the ranked lists -- one per gift category. Each is a branded collage of that
list's top games in the Board Game Black Market look.

Workflow: run this, then on Pinterest upload each pin and set its destination
link to the matching ranked-list page (printed below each file). Automating the
upload itself needs the Pinterest API (a future step once the account is set up).

    python scripts/generate_pins.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import image_compose as ic

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "config" / "rankings_cache.json"
IMG_DIR = ROOT / "docs" / "images"
OUT = ROOT / "branding" / "pins"

W, H = 1000, 1500
GOLD = ic.GOLD
GOLD_BRIGHT = (245, 208, 96)
CREAM = ic.CREAM
MUTED = (158, 146, 130)
IMPACT = "C:/Windows/Fonts/impact.ttf"
ARIAL_BOLD = "C:/Windows/Fonts/arialbd.ttf"

# (rankings-list key, pin title, destination page slug)
PINS = [
    ("family",   "BOARD GAMES\nFOR FAMILIES",  "best-family"),
    ("2p",       "BEST 2-PLAYER\nBOARD GAMES",  "best-2-player"),
    ("gateway",  "BOARD GAMES\nFOR BEGINNERS",  "best-gateway"),
    ("strategy", "BEST STRATEGY\nBOARD GAMES",  "best-strategy"),
    ("party",    "BEST PARTY\nBOARD GAMES",     "best-party"),
    ("solo",     "BEST SOLO\nBOARD GAMES",      "best-solo"),
]


def _center(draw, text, font, cx, y, fill, tracking=0):
    if tracking:
        widths = [draw.textlength(c, font=font) for c in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = cx - total / 2
        for c, w in zip(text, widths):
            draw.text((x, y), c, font=font, fill=fill)
            x += w + tracking
    else:
        draw.text((cx - draw.textlength(text, font=font) / 2, y), text, font=font, fill=fill)


def _square(im, size):
    s = min(im.width, im.height)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
    return im.resize((size, size), Image.Resampling.LANCZOS)


def _thumb(asin, image_id):
    p = IMG_DIR / f"ranked_{asin}.jpg"
    if p.exists():
        return Image.open(p).convert("RGB")
    try:
        r = requests.get(f"https://m.media-amazon.com/images/I/{image_id}", timeout=15)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


def make_pin(key, title, slug, lists):
    lst = lists.get(key)
    if not lst:
        return None
    games = [g for g in lst.get("games", []) if g.get("image_id")][:3]
    canvas = ic._branded_canvas(W, H).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([0, 0, W, 8], fill=GOLD)
    _center(draw, "BOARD GAME BLACK MARKET", ImageFont.truetype(ARIAL_BOLD, 30), W // 2, 58, GOLD, tracking=6)

    tfont = ImageFont.truetype(IMPACT, 116)
    y = 165
    for line in title.split("\n"):
        _center(draw, line, tfont, W // 2, y, CREAM)
        y += 116
    _center(draw, "ranked & price-checked", ImageFont.truetype(ARIAL_BOLD, 34), W // 2, y + 8, GOLD_BRIGHT)

    n = len(games)
    tw, gap = 280, 40
    x = (W - (n * tw + (n - 1) * gap)) // 2
    ty = 600
    for g in games:
        im = _thumb(g["asin"], g["image_id"])
        if im:
            canvas.paste(_square(im, tw), (x, ty))
            draw.rectangle([x, ty, x + tw, ty + tw], outline=GOLD, width=3)
        x += tw + gap

    nfont = ImageFont.truetype(ARIAL_BOLD, 42)
    ny = ty + tw + 55
    for g in games:
        name = g["title"] if len(g["title"]) <= 32 else g["title"][:31] + "…"
        _center(draw, name, nfont, W // 2, ny, CREAM)
        ny += 60

    # CTA pill (fills the lower third, gives the pin a clear purpose)
    cta = "See the full ranked list"
    cfont = ImageFont.truetype(ARIAL_BOLD, 40)
    cw = draw.textlength(cta, font=cfont)
    cy = ny + 70
    pad = 34
    draw.rounded_rectangle([(W - cw) / 2 - pad, cy - 6, (W + cw) / 2 + pad, cy + 62],
                           radius=14, fill=GOLD)
    _center(draw, cta, cfont, W // 2, cy, (24, 22, 19))

    draw.rectangle([0, H - 150, W, H - 142], fill=GOLD)
    _center(draw, "Verified against 90 days of real price history",
            ImageFont.truetype(ARIAL_BOLD, 30), W // 2, H - 118, MUTED)
    _center(draw, "boardgameblackmarket.com", ImageFont.truetype(ARIAL_BOLD, 40), W // 2, H - 78, GOLD, tracking=2)

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"pin_{key}.png"
    canvas.save(out, "PNG")
    return out


def main():
    lists = json.loads(CACHE.read_text(encoding="utf-8")).get("lists", {})
    for key, title, slug in PINS:
        out = make_pin(key, title, slug, lists)
        if out:
            print(f"{out.name}  ->  link it to https://boardgameblackmarket.com/{slug}.html")


if __name__ == "__main__":
    main()
