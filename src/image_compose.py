"""Produces two branded versions of each deal's product photo:

- a square "social" image with a was/now price banner, for Facebook/
  Instagram/Telegram (those platforms have no surrounding page layout, so
  the price has to live in the image itself)
- a plain square "site" thumbnail (no banner) for the website card, which
  already has its own price/rating text next to the image

Both replace the product photo's near-white studio background with the
site's brand background color, via a simple per-channel whiteness
threshold (Amazon product shots are near-pure-white, so this is a cheap,
dependency-light stand-in for real subject segmentation -- not perfect on
every edge case, but good enough across hundreds of varying product shots).

Uses fonts shipped with Windows (this pipeline only ever runs locally on
Windows, per the scheduling setup in README.md) rather than bundling a font.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

# Keep in sync with the --bg/--panel/--gold/--red custom properties in
# render_site.py's STYLE_CSS -- these are the same "Board Game Black
# Market" brand colors, just as RGB tuples for Pillow instead of hex.
BRAND_PANEL = (28, 26, 23)
GOLD = (232, 185, 35)
CREAM = (236, 230, 214)
MUTED = (168, 159, 140)
RED = (179, 36, 42)
WHITE_TEXT = (255, 255, 255)

WHITE_THRESHOLD = 235  # per-channel brightness above which a pixel counts as "studio background"
EDGE_FEATHER_PX = 3

SOCIAL_SIZE = 1080
BANNER_HEIGHT = 280
THUMB_SIZE = 800

# Instagram's profile grid crops square posts to a centered 3:4 tile, keeping
# only the middle 810px horizontally. Product art, prices, and badges must all
# live inside this band or they get clipped in the grid (feed shows the full
# square; Facebook is unaffected either way).
SAFE_W = 810
SAFE_X0 = (SOCIAL_SIZE - SAFE_W) // 2

FONT_IMPACT = "C:/Windows/Fonts/impact.ttf"
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "docs" / "images"


def compose_images(deal: dict[str, Any]) -> tuple[str | None, str | None]:
    """Returns (social_image_path, site_thumbnail_path) relative to docs/,
    e.g. ("images/B0CS7SMQ7P.jpg", "images/site_B0CS7SMQ7P.jpg"). Either or
    both may be None if there's no source image or a step fails -- callers
    should treat that as "no image available," not crash over a cosmetic
    feature."""
    product_img = _load_product_image(deal)
    if product_img is None:
        return None, None

    try:
        branded = _replace_white_background(product_img, BRAND_PANEL)
    except Exception:
        logger.exception("Background replacement failed for %s, using original photo", deal.get("asin"))
        branded = product_img

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return (
        _save_social_image(branded, deal),
        _save_site_thumbnail(branded, deal),
    )


def _load_product_image(deal: dict[str, Any]) -> Image.Image | None:
    if not deal.get("image"):
        return None
    try:
        response = requests.get(deal["image"], timeout=15)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception:
        logger.exception("Could not download product image for %s", deal.get("asin"))
        return None


def _replace_white_background(img: Image.Image, bg_color: tuple[int, int, int]) -> Image.Image:
    r, g, b = img.split()
    min_channel = ImageChops.darker(ImageChops.darker(r, g), b)
    mask = min_channel.point(lambda p: 255 if p >= WHITE_THRESHOLD else 0)
    mask = mask.filter(ImageFilter.GaussianBlur(EDGE_FEATHER_PX))
    background = Image.new("RGB", img.size, bg_color)
    return Image.composite(background, img, mask)


def _save_social_image(branded: Image.Image, deal: dict[str, Any]) -> str | None:
    try:
        canvas = _build_social_canvas(branded, deal)
        out_path = OUTPUT_DIR / f"{deal['asin']}.jpg"
        canvas.save(out_path, "JPEG", quality=88)
        return f"images/{deal['asin']}.jpg"
    except Exception:
        logger.exception("Social image composite failed for %s, skipping", deal.get("asin"))
        return None


def _save_site_thumbnail(branded: Image.Image, deal: dict[str, Any]) -> str | None:
    try:
        canvas = _build_thumbnail_canvas(branded)
        out_path = OUTPUT_DIR / f"site_{deal['asin']}.jpg"
        canvas.save(out_path, "JPEG", quality=88)
        return f"images/site_{deal['asin']}.jpg"
    except Exception:
        logger.exception("Site thumbnail composite failed for %s, skipping", deal.get("asin"))
        return None


def _fit(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    scale = min(max_w / img.width, max_h / img.height)
    new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _build_thumbnail_canvas(product_img: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (THUMB_SIZE, THUMB_SIZE), BRAND_PANEL)
    resized = _fit(product_img, THUMB_SIZE, THUMB_SIZE)
    canvas.paste(resized, ((THUMB_SIZE - resized.width) // 2, (THUMB_SIZE - resized.height) // 2))
    return canvas


def _build_social_canvas(product_img: Image.Image, deal: dict[str, Any]) -> Image.Image:
    canvas = Image.new("RGB", (SOCIAL_SIZE, SOCIAL_SIZE), BRAND_PANEL)

    available_height = SOCIAL_SIZE - BANNER_HEIGHT
    resized = _fit(product_img, SAFE_W, available_height)
    paste_x = (SOCIAL_SIZE - resized.width) // 2
    paste_y = (available_height - resized.height) // 2
    canvas.paste(resized, (paste_x, paste_y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    banner_top = SOCIAL_SIZE - BANNER_HEIGHT
    # background strip still runs edge to edge -- only CONTENT needs the safe zone
    draw.rectangle([0, banner_top, SOCIAL_SIZE, SOCIAL_SIZE], fill=(15, 14, 12, 235))

    now_font = ImageFont.truetype(FONT_IMPACT, 110)
    was_font = ImageFont.truetype(FONT_BOLD, 46)
    badge_font = ImageFont.truetype(FONT_IMPACT, 64)

    was_text = f"${deal['typical_price']:.2f}"
    now_text = f"${deal['price']:.2f}"
    badge_text = f"{deal['percent_off']}% OFF"

    # measure everything, then center the whole price+badge group in the
    # safe zone so nothing can be clipped by the 3:4 grid crop
    price_w = max(draw.textlength(was_text, font=was_font), draw.textlength(now_text, font=now_font))
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w, badge_h = badge_bbox[2] - badge_bbox[0], badge_bbox[3] - badge_bbox[1]
    badge_pad = 24
    badge_total_w = badge_w + badge_pad * 2
    gap = 56
    group_w = price_w + gap + badge_total_w
    group_x = max(SAFE_X0, (SOCIAL_SIZE - int(group_w)) // 2)

    text_x = group_x
    was_y = banner_top + 36
    draw.text((text_x, was_y), was_text, font=was_font, fill=MUTED)
    was_bbox = draw.textbbox((text_x, was_y), was_text, font=was_font)
    strike_y = (was_bbox[1] + was_bbox[3]) // 2
    draw.line([(was_bbox[0] - 4, strike_y), (was_bbox[2] + 4, strike_y)], fill=MUTED, width=4)

    now_y = was_bbox[3] + 6
    draw.text((text_x, now_y), now_text, font=now_font, fill=GOLD)

    badge_x1 = group_x + int(price_w) + gap
    badge_x2 = badge_x1 + badge_total_w
    badge_y1 = banner_top + (BANNER_HEIGHT - badge_h - badge_pad * 2) // 2
    badge_y2 = badge_y1 + badge_h + badge_pad * 2
    draw.rounded_rectangle([badge_x1, badge_y1, badge_x2, badge_y2], radius=16, fill=RED)
    draw.text(
        (badge_x1 + badge_pad, badge_y1 + badge_pad - badge_bbox[1]),
        badge_text, font=badge_font, fill=WHITE_TEXT,
    )

    return canvas
