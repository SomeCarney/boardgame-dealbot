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
import os
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
# Mirror render_site: a DRY_RUN writes composited images under docs_preview/ so
# a test run never drops files into the real, committed docs/images tree.
OUTPUT_DIR = ROOT / ("docs_preview" if os.environ.get("DRY_RUN") == "1" else "docs") / "images"


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
        mask_bg = _background_mask(product_img)
    except Exception:
        logger.exception("Background masking failed for %s, keeping full photo", deal.get("asin"))
        mask_bg = Image.new("L", product_img.size, 0)  # nothing masked out

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return (
        _save_social_image(product_img, mask_bg, deal),
        _save_site_thumbnail(product_img, mask_bg, deal),
    )


def compose_ranked_thumb(asin: str, image_id: str, force: bool = False) -> str | None:
    """Branded square thumbnail for the Hot Board Games hub/lists: Amazon box
    art with the studio background flood-filled away, composited onto the
    brand backdrop (glow, pinstripes, vignette). Cached on disk -- each game
    is downloaded and processed once, then reused by every render."""
    out_path = OUTPUT_DIR / f"ranked_{asin}.jpg"
    rel = f"images/ranked_{asin}.jpg"
    if out_path.exists() and not force:
        return rel
    try:
        resp = requests.get(f"https://m.media-amazon.com/images/I/{image_id}", timeout=20)
        resp.raise_for_status()
        product = Image.open(io.BytesIO(resp.content)).convert("RGB")
        try:
            mask_bg = _background_mask(product)
        except Exception:
            mask_bg = Image.new("L", product.size, 0)
        size = 600
        canvas = _branded_canvas(size, size)
        tw, th = _fit_box(product, int(size * 0.86), int(size * 0.86))
        _paste_subject(canvas, product, mask_bg, ((size - tw) // 2, (size - th) // 2, tw, th))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, "JPEG", quality=86)
        return rel
    except Exception:
        logger.exception("Ranked thumbnail failed for %s (%s)", asin, image_id)
        return None


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


def _background_mask(img: Image.Image) -> Image.Image:
    """L mask, 255 = studio background. Flood-fills from the borders so ONLY
    the connected outer background is selected -- white components INSIDE the
    product (cards, dice, box art) are preserved, unlike a global whiteness
    threshold which erased them."""
    work = img.copy()
    w, h = work.size
    px = work.load()
    marker = (255, 0, 255)  # never occurs in product photography

    # tight thresh: white game components (cards, dice) often touch the studio
    # background seamlessly, and a loose fill leaks into them (verified on
    # That's Not a Hat -- thresh 40 ate half a card, 22 preserved it)
    step = max(6, w // 60)
    seeds = [(x, y) for x in range(0, w, step) for y in (0, h - 1)]
    seeds += [(x, y) for y in range(0, h, step) for x in (0, w - 1)]
    for sx, sy in seeds:
        pixel = px[sx, sy]
        if pixel == marker:
            continue  # already filled by an earlier seed
        if min(pixel[:3]) >= WHITE_THRESHOLD - 10:
            ImageDraw.floodfill(work, (sx, sy), marker, thresh=22)

    target = Image.new("RGB", work.size, marker)
    diff = ImageChops.difference(work, target).convert("L")
    core = diff.point(lambda p: 255 if p == 0 else 0)

    # Soft product-photo drop shadows survive the tight fill (their grey is
    # too far from the white seed) and read as white smears on the dark
    # backdrop. Fade out shadow-toned pixels (grey 195..236) in a band around
    # the background boundary; brighter pixels (real white components) and
    # anything far from the background stay fully protected.
    r = max(24, min(w, h) // 12)
    small = core.resize((max(1, w // 8), max(1, h // 8)), Image.Resampling.BILINEAR)
    small = small.filter(ImageFilter.MaxFilter(2 * max(1, r // 16) + 1))
    dilated = small.resize((w, h), Image.Resampling.BILINEAR)
    ring = ImageChops.subtract(dilated, core)

    rch, gch, bch = img.split()
    min_channel = ImageChops.darker(ImageChops.darker(rch, gch), bch)
    LO, HI = 185, 236
    shadow_ramp = min_channel.point(
        lambda v: int((v - LO) * 255 / (HI - LO)) if LO <= v <= HI else 0
    )
    shadow = ImageChops.multiply(ring, shadow_ramp)

    mask = ImageChops.lighter(core, shadow)
    return mask.filter(ImageFilter.GaussianBlur(EDGE_FEATHER_PX))


def _branded_canvas(w: int, h: int, glow_center: tuple[int, int] | None = None) -> Image.Image:
    """Brand background: panel base, faint diagonal pinstripes (the site
    header texture), a soft gold glow behind the subject, darker corners."""
    canvas = Image.new("RGB", (w, h), BRAND_PANEL)

    stripes = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    for x in range(-h, w + h, 26):
        sd.line([(x, h), (x + h, 0)], fill=(232, 185, 35, 8), width=1)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), stripes)

    cx, cy = glow_center or (w // 2, h // 2)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    r = int(min(w, h) * 0.46)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(232, 185, 35, 34))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(min(w, h) * 0.10)))

    vignette = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse([-w * 0.3, -h * 0.3, w * 1.3, h * 1.3], fill=36)
    vd.ellipse([w * 0.04, h * 0.04, w * 0.96, h * 0.96], fill=0)
    dark = Image.new("RGBA", (w, h), (10, 9, 8, 255))
    canvas = Image.composite(dark, canvas, vignette.filter(ImageFilter.GaussianBlur(min(w, h) * 0.05)))

    return canvas.convert("RGB")


def _paste_subject(canvas: Image.Image, product: Image.Image, mask_bg: Image.Image,
                   box: tuple[int, int, int, int]) -> None:
    """Pastes the product's SUBJECT pixels (background masked out) into
    canvas at box, resizing product and mask together."""
    x, y, tw, th = box
    resized = product.resize((tw, th), Image.Resampling.LANCZOS)
    subject_alpha = ImageChops.invert(mask_bg).resize((tw, th), Image.Resampling.LANCZOS)
    canvas.paste(resized, (x, y), subject_alpha)


def _save_social_image(product: Image.Image, mask_bg: Image.Image, deal: dict[str, Any]) -> str | None:
    try:
        canvas = _build_social_canvas(product, mask_bg, deal)
        out_path = OUTPUT_DIR / f"{deal['asin']}.jpg"
        canvas.save(out_path, "JPEG", quality=88)
        return f"images/{deal['asin']}.jpg"
    except Exception:
        logger.exception("Social image composite failed for %s, skipping", deal.get("asin"))
        return None


def _save_site_thumbnail(product: Image.Image, mask_bg: Image.Image, deal: dict[str, Any]) -> str | None:
    try:
        canvas = _build_thumbnail_canvas(product, mask_bg)
        out_path = OUTPUT_DIR / f"site_{deal['asin']}.jpg"
        canvas.save(out_path, "JPEG", quality=88)
        return f"images/site_{deal['asin']}.jpg"
    except Exception:
        logger.exception("Site thumbnail composite failed for %s, skipping", deal.get("asin"))
        return None


def _fit_box(img: Image.Image, max_w: int, max_h: int) -> tuple[int, int]:
    scale = min(max_w / img.width, max_h / img.height)
    return max(1, int(img.width * scale)), max(1, int(img.height * scale))


def _build_thumbnail_canvas(product: Image.Image, mask_bg: Image.Image) -> Image.Image:
    canvas = _branded_canvas(THUMB_SIZE, THUMB_SIZE)
    tw, th = _fit_box(product, THUMB_SIZE, THUMB_SIZE)
    _paste_subject(canvas, product, mask_bg, ((THUMB_SIZE - tw) // 2, (THUMB_SIZE - th) // 2, tw, th))
    return canvas


def _build_social_canvas(product: Image.Image, mask_bg: Image.Image, deal: dict[str, Any]) -> Image.Image:
    available_height = SOCIAL_SIZE - BANNER_HEIGHT
    canvas = _branded_canvas(SOCIAL_SIZE, SOCIAL_SIZE, glow_center=(SOCIAL_SIZE // 2, available_height // 2))

    tw, th = _fit_box(product, SAFE_W, available_height)
    paste_x = (SOCIAL_SIZE - tw) // 2
    paste_y = (available_height - th) // 2
    _paste_subject(canvas, product, mask_bg, (paste_x, paste_y, tw, th))

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
