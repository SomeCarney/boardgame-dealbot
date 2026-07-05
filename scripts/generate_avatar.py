"""Generates a Reddit profile avatar for the u/90-Day-Average account, in the
Board Game Black Market aesthetic (gold die on a dark, softly-lit backdrop).

The mark marries the three ideas: a die (board games), a big "90" on its face
(the account name), and a descending price line behind it (the 90-day average /
price drop). Reddit crops avatars to a circle, so everything stays centered
inside a circle-safe zone. Outputs a 1024x1024 PNG ready to upload.

    python scripts/generate_avatar.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import image_compose as ic  # reuse the exact brand background (panel/pinstripes/glow/vignette)

SIZE = 1024
OUT = Path(__file__).resolve().parent.parent / "branding" / "reddit_avatar.png"

GOLD = ic.GOLD                 # (232, 185, 35)
GOLD_BRIGHT = (245, 208, 96)
DARK = (24, 22, 19)            # "90" on the gold die
FONT_IMPACT = "C:/Windows/Fonts/impact.ttf"
FONT_ARIAL_BOLD = "C:/Windows/Fonts/arialbd.ttf"


def _die_layer(tile: int) -> Image.Image:
    """A gold rounded-square die face with '90', on its own transparent layer
    so it can be rotated as one piece (keeping the number square to the die)."""
    radius = int(tile * 0.17)
    layer = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([0, 0, tile - 1, tile - 1], radius=radius, fill=GOLD)

    # subtle top sheen: a brighter band on its own layer, masked to the die,
    # alpha-composited so it LIGHTENS (drawing with alpha in-place doesn't blend)
    sheen = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    sd.rounded_rectangle([0, 0, tile - 1, int(tile * 0.5)], radius=radius, fill=GOLD_BRIGHT + (110,))
    die_mask = Image.new("L", (tile, tile), 0)
    ImageDraw.Draw(die_mask).rounded_rectangle([0, 0, tile - 1, tile - 1], radius=radius, fill=255)
    layer = Image.composite(Image.alpha_composite(layer, sheen), layer, die_mask)

    d = ImageDraw.Draw(layer)
    font = ImageFont.truetype(FONT_IMPACT, int(tile * 0.62))
    bb = d.textbbox((0, 0), "90", font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((tile - tw) / 2 - bb[0], (tile - th) / 2 - bb[1]), "90", font=font, fill=DARK)
    return layer.rotate(-8, resample=Image.BICUBIC, expand=True)


def make() -> None:
    canvas = ic._branded_canvas(SIZE, SIZE).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # the die, with a soft drop shadow, a touch above center for the label
    die = _die_layer(500)
    dx, dy = (SIZE - die.width) // 2, (SIZE - die.height) // 2 - 46
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 150), (dx + 14, dy + 20), die)
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    canvas.alpha_composite(die, (dx, dy))

    # small wordmark under the die (reads on the profile; ignorable when tiny)
    label_font = ImageFont.truetype(FONT_ARIAL_BOLD, 60)
    label = "DAY  AVERAGE"
    lb = draw.textbbox((0, 0), label, font=label_font)
    # letter-spacing by hand for a cleaner look
    draw.text(((SIZE - (lb[2] - lb[0])) / 2 - lb[0], 792), label, font=label_font,
              fill=GOLD, stroke_width=0)

    # gold seal ring (aligns with Reddit's circular crop -> reads as a coin/stamp)
    pad = 30
    draw.ellipse([pad, pad, SIZE - pad, SIZE - pad], outline=GOLD + (110,), width=7)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUT, "PNG")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    make()
