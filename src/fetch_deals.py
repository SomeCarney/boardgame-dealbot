"""Finds genuine price drops via the Keepa API.

Field choices here are verified against the installed `keepa` package's source
(keepa/keepa_sync.py, keepa/constants.py) rather than guessed -- in particular
the csv/stats index constants (0=AMAZON price, 16=RATING, 17=COUNT_REVIEWS) and
the fact that the wrapper already normalizes prices to dollars and ratings to a
0-5 scale, returning None for missing values. See that source for specifics.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import keepa

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CATEGORY_CACHE_PATH = CONFIG_DIR / "category_cache.json"

# keepa.constants.csv_indices -- index into stats["current"] / stats["avg90"]
IDX_AMAZON_PRICE = 0
IDX_RATING = 16
IDX_REVIEW_COUNT = 17

_DOMAIN_IDS = {
    "US": 1, "GB": 2, "DE": 3, "FR": 4, "JP": 5,
    "CA": 6, "CN": 7, "IT": 8, "ES": 9, "IN": 10, "MX": 11, "BR": 12,
}

FIXTURE_DEALS: list[dict[str, Any]] = [
    {
        "asin": "B00FIXTURE1",
        "title": "[SAMPLE FIXTURE DEAL] Wingspan",
        "price": 39.99,
        "typical_price": 59.99,
        "percent_off": 33,
        "rating": 4.8,
        "review_count": 12000,
        "image": None,
    },
    {
        "asin": "B00FIXTURE2",
        "title": "[SAMPLE FIXTURE DEAL] Catan: 5-6 Player Extension",
        "price": 24.50,
        "typical_price": 34.99,
        "percent_off": 30,
        "rating": 4.7,
        "review_count": 8500,
        "image": None,
    },
]


def fetch_deals(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Entry point used by main.py. Set DRY_RUN=1 to get fixture data instead
    of calling Keepa, so the pipeline is testable without spending real
    tokens or needing credentials yet. Without DRY_RUN, a missing API key is
    a hard error -- a misconfigured production run should fail loudly, not
    silently publish fixture data."""
    if os.environ.get("DRY_RUN") == "1":
        logger.warning("DRY_RUN=1 -- returning fixture deals, not calling Keepa")
        return FIXTURE_DEALS
    if not os.environ.get("KEEPA_API_KEY"):
        raise RuntimeError("KEEPA_API_KEY is not set. Set DRY_RUN=1 to test without it.")
    return _fetch_real_deals(config)


def _fetch_real_deals(config: dict[str, Any]) -> list[dict[str, Any]]:
    api = keepa.Keepa(os.environ["KEEPA_API_KEY"])
    niche = config["niche"]
    filters = config["deal_filters"]
    domain = niche.get("domain", "US")

    category_id, category_name = _resolve_category_id(api, niche["category_search_term"], domain)

    deal_parms: dict[str, Any] = {
        "page": 0,
        "domainId": _DOMAIN_IDS.get(domain.upper(), 1),
        "includeCategories": [category_id],
        "priceTypes": [0],  # 0 = Amazon price
        "deltaPercentRange": [int(filters["min_percent_off"]), 100],
        "currentRange": [int(filters["min_price"] * 100), int(filters["max_price"] * 100)],
        "minRating": int(filters["min_rating"] * 10),
        "isRangeEnabled": True,
        "isFilterEnabled": True,
        "hasReviews": True,
        "sortType": 4,
        "dateRange": int(filters.get("date_range", 1)),
    }
    if filters.get("require_in_stock", True):
        deal_parms["isOutOfStock"] = False

    raw = api.deals(deal_parms, domain=domain)
    candidates = raw.get("dr", [])
    logger.info("Keepa returned %d raw deal candidates in category %r (%s)", len(candidates), category_name, category_id)

    asins = [d["asin"] for d in candidates if d.get("asin")]
    if not asins:
        return []

    # history=False: we only ever read the `stats` summary (current/avg90),
    # never the full price/sales history -- pulling it was burning tokens
    # for data this code never looks at.
    products = api.query(asins, stats=90, rating=True, domain=domain, progress_bar=False, history=False)
    deals = _normalize_products(products, filters)
    logger.info("%d deals passed normalization/filtering", len(deals))
    return deals


def _resolve_category_id(api: "keepa.Keepa", search_term: str, domain: str) -> tuple[int, str]:
    """Resolve a human category name to a Keepa category id once, then cache
    it on disk so future runs don't spend tokens re-resolving it."""
    cache: dict[str, Any] = {}
    if CATEGORY_CACHE_PATH.exists():
        cache = json.loads(CATEGORY_CACHE_PATH.read_text())

    cache_key = f"{domain}:{search_term.lower()}"
    if cache_key in cache:
        entry = cache[cache_key]
        return entry["id"], entry["name"]

    results = api.search_for_categories(search_term, domain=domain)
    if not results:
        raise RuntimeError(f"No Keepa category found for search term {search_term!r}")

    # Category search returns many loosely-related matches; the one with the
    # most products is almost always the actual top-level category we want.
    best_id, best = max(results.items(), key=lambda kv: kv[1].get("productCount", 0))
    name = best.get("name", search_term)

    cache[cache_key] = {"id": int(best_id), "name": name}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORY_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    logger.info("Resolved category %r -> id=%s name=%r (verify this looks right on first run)", search_term, best_id, name)
    return int(best_id), name


def _normalize_products(products: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    deals: list[dict[str, Any]] = []
    for p in products:
        stats = p.get("stats") or {}
        current = stats.get("current") or []
        avg90 = stats.get("avg90") or []

        # stats values come back in Keepa's raw wire units, NOT pre-converted
        # by the wrapper: price/rating are isfloat fields per
        # keepa.constants.csv_indices, meaning cents and rating-times-10
        # respectively. Confirmed against a live API call -- raw prices were
        # showing as e.g. 2999 for a $29.99 game before this conversion.
        price = _cents_to_dollars(_at(current, IDX_AMAZON_PRICE))
        typical_price = _cents_to_dollars(_at(avg90, IDX_AMAZON_PRICE))
        rating = _rating_to_stars(_at(current, IDX_RATING))
        review_count = _at(current, IDX_REVIEW_COUNT)  # plain count, not scaled

        if price is None or typical_price is None or typical_price <= 0:
            continue  # missing price data -- skip rather than guess
        if rating is not None and rating < filters["min_rating"]:
            continue
        if review_count is not None and review_count < filters["min_review_count"]:
            continue

        percent_off = round((1 - price / typical_price) * 100)
        if percent_off < filters["min_percent_off"]:
            continue

        images = (p.get("imagesCSV") or "").split(",")
        image_id = images[0] if images and images[0] else None

        deals.append({
            "asin": p.get("asin"),
            "title": p.get("title") or "Unknown title",
            "price": price,
            "typical_price": typical_price,
            "percent_off": percent_off,
            "rating": rating,
            "review_count": review_count,
            "image": f"https://images-na.ssl-images-amazon.com/images/I/{image_id}" if image_id else None,
        })

    deals.sort(key=lambda d: d["percent_off"], reverse=True)
    return deals


def _at(arr: list, idx: int) -> Any:
    """-1/-2 are Keepa's "no data" sentinels (see Keepa's product object
    docs) -- treat them as missing rather than as real values."""
    if idx >= len(arr):
        return None
    value = arr[idx]
    return None if value is None or value < 0 else value


def _cents_to_dollars(value: float | None) -> float | None:
    return None if value is None else value / 100


def _rating_to_stars(value: float | None) -> float | None:
    return None if value is None else value / 10
