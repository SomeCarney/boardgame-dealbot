"""Composites a was/now price banner onto the product image, for social
posts. Square JPEG output -- satisfies both Facebook's and Instagram's
image requirements (Instagram specifically: JPEG only, aspect ratio between
4:5 and 1.91:1 -- square is explicitly fine, and the image must be hosted
at a publicly reachable URL, which is why this gets saved into docs/ and
pushed to GitHub Pages rather than kept as a local temp file.

Uses fonts shipped with Windows (this pipeline only ever runs locally on
Windows, per the scheduling setup in README.md) rather than bundling a font.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

CANVAS_SIZE = 1080
BANNER_HEIGHT = 280
BACKGROUND_COLOR = (255, 255, 255)
BANNER_COLOR = (20, 20, 20, 235)
NOW_PRICE_COLOR = (255, 214, 0)
WAS_PRICE_COLOR = (190, 190, 190)
BADGE_COLOR = (214, 40, 40)
BADGE_TEXT_COLOR = (255, 255, 255)

FONT_IMPACT = "C:/Windows/Fonts/impact.ttf"
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "docs" / "images"


def compose_deal_image(deal: dict[str, Any]) -> str | None:
    """Downloads the product image, overlays a price banner, saves a JPEG
    into docs/images/. Returns the path relative to docs/ (e.g.
    "images/B0CS7SMQ7P.jpg"), or None if there's no source image or the
    download/composite fails -- callers should treat that as "no image
    available," not crash the run over a cosmetic feature."""
    if not deal.get("image"):
        return None

    try:
        response = requests.get(deal["image"], timeout=15)
        response.raise_for_status()
        product_img = Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception:
        logger.exception("Could not download product image for %s, skipping composite", deal.get("asin"))
        return None

    try:
        canvas = _build_canvas(product_img, deal)
    except Exception:
        logger.exception("Image composite failed for %s, skipping", deal.get("asin"))
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{deal['asin']}.jpg"
    canvas.save(out_path, "JPEG", quality=88)
    return f"images/{deal['asin']}.jpg"


def _build_canvas(product_img: Image.Image, deal: dict[str, Any]) -> Image.Image:
    canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), BACKGROUND_COLOR)

    available_height = CANVAS_SIZE - BANNER_HEIGHT
    scale = min(CANVAS_SIZE / product_img.width, available_height / product_img.height)
    new_size = (max(1, int(product_img.width * scale)), max(1, int(product_img.height * scale)))
    product_img = product_img.resize(new_size, Image.Resampling.LANCZOS)
    paste_x = (CANVAS_SIZE - new_size[0]) // 2
    paste_y = (available_height - new_size[1]) // 2
    canvas.paste(product_img, (paste_x, paste_y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    banner_top = CANVAS_SIZE - BANNER_HEIGHT
    draw.rectangle([0, banner_top, CANVAS_SIZE, CANVAS_SIZE], fill=BANNER_COLOR)

    now_font = ImageFont.truetype(FONT_IMPACT, 110)
    was_font = ImageFont.truetype(FONT_BOLD, 46)
    badge_font = ImageFont.truetype(FONT_IMPACT, 64)

    text_x = 50
    was_text = f"${deal['typical_price']:.2f}"
    was_y = banner_top + 36
    draw.text((text_x, was_y), was_text, font=was_font, fill=WAS_PRICE_COLOR)
    was_bbox = draw.textbbox((text_x, was_y), was_text, font=was_font)
    strike_y = (was_bbox[1] + was_bbox[3]) // 2
    draw.line([(was_bbox[0] - 4, strike_y), (was_bbox[2] + 4, strike_y)], fill=WAS_PRICE_COLOR, width=4)

    now_text = f"${deal['price']:.2f}"
    now_y = was_bbox[3] + 6
    draw.text((text_x, now_y), now_text, font=now_font, fill=NOW_PRICE_COLOR)

    badge_text = f"{deal['percent_off']}% OFF"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w, badge_h = badge_bbox[2] - badge_bbox[0], badge_bbox[3] - badge_bbox[1]
    badge_pad = 24
    badge_x2 = CANVAS_SIZE - 40
    badge_x1 = badge_x2 - badge_w - badge_pad * 2
    badge_y1 = banner_top + (BANNER_HEIGHT - badge_h - badge_pad * 2) // 2
    badge_y2 = badge_y1 + badge_h + badge_pad * 2
    draw.rounded_rectangle([badge_x1, badge_y1, badge_x2, badge_y2], radius=16, fill=BADGE_COLOR)
    draw.text(
        (badge_x1 + badge_pad, badge_y1 + badge_pad - badge_bbox[1]),
        badge_text, font=badge_font, fill=BADGE_TEXT_COLOR,
    )

    return canvas
