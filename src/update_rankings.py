"""Monthly rankings updater.

Fetches current Keepa data for every game in rankings_config.yaml,
recomputes ranking scores, and writes rankings_cache.json.
render_site.py reads the cache to generate the Best Board Games pages.

Usage:
    python src/update_rankings.py            # full refresh
    python src/update_rankings.py --dry-run  # print scores without writing
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("update_rankings")

CONFIG_PATH = ROOT / "config" / "rankings_config.yaml"
CACHE_PATH  = ROOT / "config" / "rankings_cache.json"
ASSOCIATE_TAG = os.environ.get("AMAZON_ASSOCIATE_TAG", "carnivalgam06-20")


def _score(rating: float | None, reviews: int | None, sales_rank: int | None) -> float:
    """Weighted quality score used to order games within a list.

    Higher = better.  All three signals push in the same direction:
    high rating × many reviews × low sales rank.
    """
    r = rating or 3.5
    n = max(reviews or 0, 10)
    sr = sales_rank or 500_000
    return (r ** 2) * math.log10(n) / math.log10(max(sr, 2))


def fetch_keepa_data(asins: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-fetch product data from Keepa for all ASINs. Returns dict keyed by ASIN."""
    import keepa
    api = keepa.Keepa(os.environ["KEEPA_API_KEY"])
    results: dict[str, dict[str, Any]] = {}

    # Query in batches of 100 to avoid token exhaustion in a single call
    BATCH = 100
    for i in range(0, len(asins), BATCH):
        batch = asins[i : i + BATCH]
        logger.info("Querying Keepa for %d ASINs (batch %d/%d)", len(batch), i // BATCH + 1, math.ceil(len(asins) / BATCH))
        try:
            products = api.query(batch, stats=90, rating=True, domain="US", progress_bar=False, history=False)
        except Exception:
            logger.exception("Keepa query failed for batch starting at index %d", i)
            continue

        for p in products:
            asin = p.get("asin")
            if not asin:
                continue
            imgs = p.get("images") or []
            img = imgs[0].get("l") if imgs else None
            stats = p.get("stats") or {}
            cur = stats.get("current") or []

            def _cur(idx: int) -> Any:
                v = cur[idx] if len(cur) > idx else None
                return None if v is None or v < 0 else v

            price_raw = _cur(0)
            rating_raw = _cur(16)
            reviews = _cur(17)
            sales_rank = _cur(3)

            results[asin] = {
                "asin": asin,
                "fetched_title": (p.get("title") or "")[:120],
                "image_id": img,
                "price": round(price_raw / 100, 2) if price_raw else None,
                "rating": round(rating_raw / 10, 1) if rating_raw else None,
                "reviews": reviews,
                "sales_rank": sales_rank,
                "score": _score(
                    round(rating_raw / 10, 1) if rating_raw else None,
                    reviews,
                    sales_rank,
                ),
            }

    return results


def compute_ranked_list(
    list_cfg: dict[str, Any],
    game_defs: dict[str, Any],
    keepa_data: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return games for one list, ordered by ranking strategy."""
    asins = list_cfg.get("asins", [])
    ranking = list_cfg.get("ranking", "formula")
    count = list_cfg.get("count", 20)

    rows: list[dict[str, Any]] = []
    for asin in asins:
        kd = keepa_data.get(asin, {})
        gd = game_defs.get(asin, {})
        if not kd.get("image_id"):
            # No image data — include with no photo rather than silently dropping
            logger.warning("No Keepa image data for %s (%s)", asin, gd.get("title", "?"))
        rows.append({
            "asin": asin,
            "title": gd.get("title") or kd.get("fetched_title") or asin,
            "players": gd.get("players"),
            "time": gd.get("time"),
            "age": gd.get("age"),
            "blurb": (gd.get("blurb") or "").strip(),
            "editorial_rank": gd.get("editorial_rank"),
            "image_id": kd.get("image_id"),
            "price": kd.get("price"),
            "rating": kd.get("rating"),
            "reviews": kd.get("reviews"),
            "sales_rank": kd.get("sales_rank"),
            "score": kd.get("score", 0.0),
            "link": f"https://www.amazon.com/dp/{asin}?tag={ASSOCIATE_TAG}",
        })

    if ranking == "editorial":
        # Primary: editorial_rank (ascending, None goes last)
        # Secondary: score (descending)
        rows.sort(key=lambda r: (
            r["editorial_rank"] if r["editorial_rank"] is not None else 9999,
            -r["score"],
        ))
    else:
        rows.sort(key=lambda r: -r["score"])

    # Box art is required: a ranked entry with a placeholder die looks broken.
    # (Missing images are backstopped from the previous cache in main() first,
    # so only games Keepa has never had art for get dropped.)
    rows = [r for r in rows if r["title"] and r["asin"] and r["image_id"]]
    return rows[:count]


def _previous_image_ids() -> dict[str, str]:
    """ASIN -> image_id from the existing cache. Keepa occasionally returns
    products without image data (seen live 2026-07-02); without this guard a
    single bad monthly fetch silently strips box art off the whole site."""
    if not CACHE_PATH.exists():
        return {}
    try:
        old = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    for lst in old.get("lists", {}).values():
        for g in lst.get("games", []):
            if g.get("asin") and g.get("image_id"):
                out[g["asin"]] = g["image_id"]
    return out


def main(dry_run: bool = False) -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    game_defs: dict[str, Any] = cfg.get("games", {})
    list_cfgs: dict[str, Any] = cfg.get("lists", {})

    # Collect all unique ASINs across all lists
    all_asins: list[str] = sorted({
        asin
        for lc in list_cfgs.values()
        for asin in lc.get("asins", [])
        if asin and isinstance(asin, str)
    })
    logger.info("Fetching Keepa data for %d unique ASINs", len(all_asins))

    keepa_data = fetch_keepa_data(all_asins)
    logger.info("Got data for %d/%d ASINs", len(keepa_data), len(all_asins))

    # Backstop missing images with the previous cache's
    prev_images = _previous_image_ids()
    restored = 0
    for asin, kd in keepa_data.items():
        if not kd.get("image_id") and asin in prev_images:
            kd["image_id"] = prev_images[asin]
            restored += 1
    if restored:
        logger.warning("Keepa returned no image for %d ASIN(s) -- kept previous box art", restored)

    cache: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "lists": {},
    }

    for list_key, list_cfg in list_cfgs.items():
        ranked = compute_ranked_list(list_cfg, game_defs, keepa_data)
        cache["lists"][list_key] = {
            "slug": list_cfg["slug"],
            "title": list_cfg["title"],
            "description": list_cfg["description"],
            "games": ranked,
        }
        logger.info("List %s: %d games ranked", list_key, len(ranked))
        if dry_run:
            for i, g in enumerate(ranked):
                print(f"  #{len(ranked)-i:2d}  {g['asin']}  {g['rating']}/5  {g['title'][:60]}")

    if not dry_run:
        CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Wrote %s", CACHE_PATH)
    else:
        logger.info("Dry run — not writing cache.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
