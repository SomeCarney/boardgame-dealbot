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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import keepa

from safewrite import atomic_write_text

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CATEGORY_CACHE_PATH = CONFIG_DIR / "category_cache.json"
BEST_SELLERS_CACHE_PATH = CONFIG_DIR / "best_sellers_cache.json"
BEST_SELLERS_CACHE_TTL = timedelta(hours=24)  # Keepa's best-seller lists are themselves only updated daily

# keepa.constants.csv_indices -- index into stats["current"] / stats["avg90"]
IDX_AMAZON_PRICE = 0
IDX_SALES_RANK = 3
IDX_LIST_PRICE = 4   # MSRP -- the "was" price Amazon's own "-XX%" is measured against
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
        "description": "A relaxing, strategic engine-building game about birds for 1 to 5 players.",
        "features": ["Beautiful bird artwork", "Engine-building gameplay for 1-5 players", "Plays in about 40-70 minutes"],
        "price": 39.99,
        "typical_price": 59.99,
        "percent_off": 33,
        "rating": 4.8,
        "review_count": 12000,
        "sales_rank": 42,
        "is_best_seller": True,
        "image": None,
    },
    {
        "asin": "B00FIXTURE2",
        "title": "[SAMPLE FIXTURE DEAL] Catan: 5-6 Player Extension",
        "description": "Expands the classic Catan trading and building game to support 5 to 6 players.",
        "features": ["Adds 2 extra players to base Catan", "Compatible with Catan 5th edition"],
        "price": 24.50,
        "typical_price": 34.99,
        "percent_off": 30,
        "rating": 4.7,
        "review_count": 8500,
        "sales_rank": 8400,
        "is_best_seller": False,
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

    best_seller_asins = _fetch_best_seller_asins(api, category_id, domain)

    # history=False: we only ever read the `stats` summary (current/avg90),
    # never the full price/sales history -- pulling it was burning tokens
    # for data this code never looks at.
    products = api.query(asins, stats=90, rating=True, domain=domain, progress_bar=False, history=False)
    deals = _normalize_products(products, filters, best_seller_asins)
    logger.info("%d deals passed normalization/filtering", len(deals))
    return deals


def _fetch_best_seller_asins(api: "keepa.Keepa", category_id: int, domain: str) -> set[str]:
    """Cross-referencing deals against the category's actual best-sellers
    lets posting favor proven, high-velocity games over ones that merely
    cleared the discount threshold -- a deal on a popular game is far more
    likely to convert into a real, commission-earning sale. Keepa's
    best-seller lists are only updated daily, so this is cached for 24h
    rather than re-fetched every run. Fails soft: any error here should
    degrade to "no best-seller boost," never break a run over a ranking
    enhancement."""
    cache_key = f"{domain}:{category_id}"
    cache: dict[str, Any] = {}
    if BEST_SELLERS_CACHE_PATH.exists():
        try:
            cache = json.loads(BEST_SELLERS_CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("best-sellers cache corrupt -- rebuilding it")
            cache = {}

    entry = cache.get(cache_key)
    if entry:
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < BEST_SELLERS_CACHE_TTL:
            return set(entry["asins"])

    try:
        asins = api.best_sellers_query(str(category_id), domain=domain)
    except Exception:
        logger.exception("best_sellers_query failed, continuing without the best-seller boost this run")
        return set(entry["asins"]) if entry else set()

    cache[cache_key] = {"asins": asins, "fetched_at": datetime.now(timezone.utc).isoformat()}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(BEST_SELLERS_CACHE_PATH, json.dumps(cache, indent=2))
    logger.info("Refreshed best-sellers list for category %s: %d ASINs", category_id, len(asins))
    return set(asins)


def _resolve_category_id(api: "keepa.Keepa", search_term: str, domain: str) -> tuple[int, str]:
    """Resolve a human category name to a Keepa category id once, then cache
    it on disk so future runs don't spend tokens re-resolving it."""
    cache: dict[str, Any] = {}
    if CATEGORY_CACHE_PATH.exists():
        try:
            cache = json.loads(CATEGORY_CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("category cache corrupt -- re-resolving")
            cache = {}

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
    atomic_write_text(CATEGORY_CACHE_PATH, json.dumps(cache, indent=2))
    logger.info("Resolved category %r -> id=%s name=%r (verify this looks right on first run)", search_term, best_id, name)
    return int(best_id), name


def _normalize_products(products: list[dict[str, Any]], filters: dict[str, Any], best_seller_asins: set[str] | None = None) -> list[dict[str, Any]]:
    best_seller_asins = best_seller_asins or set()
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
        list_price = _cents_to_dollars(_at(current, IDX_LIST_PRICE))
        # min/maxInInterval hold the 90-day low/high per index as [ts, value] pairs
        low_90d = _cents_to_dollars(_interval_value(stats.get("minInInterval") or [], IDX_AMAZON_PRICE))
        high_90d = _cents_to_dollars(_interval_value(stats.get("maxInInterval") or [], IDX_AMAZON_PRICE))
        rating = _rating_to_stars(_at(current, IDX_RATING))
        review_count = _at(current, IDX_REVIEW_COUNT)  # plain count, not scaled
        sales_rank = _at(current, IDX_SALES_RANK)  # lower is better-selling; not a price, no cents conversion

        if price is None or typical_price is None or typical_price <= 0:
            continue  # missing price data -- skip rather than guess
        if rating is not None and rating < filters["min_rating"]:
            continue
        if review_count is not None and review_count < filters["min_review_count"]:
            continue

        percent_off = round((1 - price / typical_price) * 100)
        if percent_off < filters["min_percent_off"]:
            continue

        # ── deal verification ────────────────────────────────────────────────
        # Amazon's own headline discount ("-37%, was $34.99") is measured
        # against the LIST price (MSRP), not the real selling price. Record it
        # so every deal is cross-checkable against what a shopper sees on the
        # Amazon page -- and so a "deal" with no genuine markdown is exposed.
        amazon_percent_off = (
            round((1 - price / list_price) * 100) if list_price and list_price > price else 0
        )
        # A price can clear the 90-day *average* and still be a weak deal: when
        # an item is frequently discounted, those prior sales drag the average
        # down, so a mediocre price looks like a drop. Measuring against the
        # item's own 90-day low catches that -- if it's routinely far cheaper,
        # this isn't really a deal (Disney Villainous: avg $28 but a 90-day low
        # of $13.30 -- a $22 "deal" that history says is nothing special).
        percent_above_low = (
            round((price / low_90d - 1) * 100) if low_90d and low_90d > 0 else None
        )
        max_above_low = filters.get("max_percent_above_90d_low")
        if (max_above_low is not None and percent_above_low is not None
                and percent_above_low > max_above_low):
            logger.info(
                "Rejected %s: $%.2f is %d%% above its 90-day low $%.2f (weak; limit %d%%). "
                "Amazon shows %d%% off list, we'd have shown %d%% off 90-day avg.",
                p.get("asin"), price, percent_above_low, low_90d, max_above_low,
                amazon_percent_off, percent_off,
            )
            continue

        logger.info(
            "Verified %s: $%.2f = %d%% off 90-day avg $%.2f | Amazon %d%% off list %s | %s above 90-day low %s",
            p.get("asin"), price, percent_off, typical_price, amazon_percent_off,
            f"${list_price:.2f}" if list_price else "n/a",
            f"{percent_above_low}%" if percent_above_low is not None else "n/a",
            f"${low_90d:.2f}" if low_90d else "n/a",
        )

        # NOTE: "imagesCSV" (used in earlier versions of this code) doesn't
        # exist on this keepa package version's product object -- confirmed
        # against a live call. The real field is "images": a list of dicts
        # with large/medium filenames under "l"/"m". Every deal posted
        # before this fix had no image at all.
        images = p.get("images") or []
        image_filename = images[0].get("l") if images else None

        deals.append({
            "asin": p.get("asin"),
            "title": p.get("title") or "Unknown title",
            "brand": p.get("brand") or "",
            "description": p.get("description") or "",
            "features": p.get("features") or [],
            "price": price,
            "typical_price": typical_price,
            "percent_off": percent_off,
            "list_price": list_price,
            "amazon_percent_off": amazon_percent_off,
            "low_90d": low_90d,
            "high_90d": high_90d,
            "percent_above_low": percent_above_low,
            "rating": rating,
            "review_count": review_count,
            "sales_rank": sales_rank,
            "is_best_seller": p.get("asin") in best_seller_asins,
            "image": f"https://m.media-amazon.com/images/I/{image_filename}" if image_filename else None,
        })

    deals.sort(key=_deal_rank_key)
    return deals


def _deal_rank_key(d: dict[str, Any]) -> tuple[int, float, int]:
    """Orders deals so that, when more qualify than max_posts_per_run
    allows, the posted slots go to proven, high-velocity sellers rather
    than just whichever happened to have the biggest discount -- a deal on
    a popular game converts into a real (commission-earning) sale far more
    often than the same discount on an obscure one. Sorted ascending:
    confirmed best-sellers first, then by sales rank (lower = sells more),
    then by percent_off as a tiebreaker."""
    best_seller_rank = 0 if d.get("is_best_seller") else 1
    sales_rank = d.get("sales_rank")
    sales_rank_for_sort = sales_rank if sales_rank is not None else float("inf")
    return (best_seller_rank, sales_rank_for_sort, -d["percent_off"])


def _at(arr: list, idx: int) -> Any:
    """-1/-2 are Keepa's "no data" sentinels (see Keepa's product object
    docs) -- treat them as missing rather than as real values."""
    if idx >= len(arr):
        return None
    value = arr[idx]
    return None if value is None or value < 0 else value


def _interval_value(entries: list, idx: int) -> Any:
    """Pulls the value from Keepa's min/maxInInterval arrays, whose entries are
    [timestamp, value] pairs (or None / [-1, -1] for "no data in this window")."""
    if idx >= len(entries):
        return None
    entry = entries[idx]
    if not entry or not isinstance(entry, (list, tuple)) or len(entry) < 2:
        return None
    value = entry[1]
    return None if value is None or value < 0 else value


def _cents_to_dollars(value: float | None) -> float | None:
    return None if value is None else value / 100


def _rating_to_stars(value: float | None) -> float | None:
    return None if value is None else value / 10
