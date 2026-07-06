"""Marks listed deals whose Amazon discount has ended.

Runs at the start of every pipeline run: one Keepa batch query (~1 token per
listed deal) re-checks every deal currently visible on the site. A deal
expires when the product is no longer buyable or its discount vs the 90-day
average has fallen below the posting threshold.

Entries are never deleted: expired deals stay in posted_log.json with an
expired_at timestamp and their last seen price. That removes them from the
site while quietly accumulating the dataset for a future searchable
"sale history" feature.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fetch_deals import customer_price_from_stats

logger = logging.getLogger(__name__)


def mark_expired(log: list[dict[str, Any]], config: dict[str, Any]) -> int:
    """Re-checks every listed deal against the current BUY BOX price (what the
    shopper actually sees), in place. Expires ones that no longer qualify, and
    RE-PRICES the survivors to current values so the site never shows a stale or
    wrong price/discount. Returns the number of entries changed (expired +
    re-priced) so the caller knows to persist."""
    max_listed = config["posting"]["site_max_listed_deals"]
    min_off = config["deal_filters"]["min_percent_off"]
    max_above_low = config["deal_filters"].get("max_percent_above_90d_low")
    listed = [d for d in log if not d.get("expired_at")][:max_listed]
    if not listed:
        return 0

    import keepa
    api = keepa.Keepa(os.environ["KEEPA_API_KEY"], timeout=60)  # 10s default times out on big stats+buybox queries
    try:
        products = api.query(
            [d["asin"] for d in listed],
            stats=90, rating=True, buybox=True, domain=config["niche"]["domain"],
            progress_bar=False, history=False,
        )
    except Exception:
        logger.exception("Deal refresh query failed -- keeping all listed deals this run")
        return 0

    by_asin = {p.get("asin"): p for p in products}
    now = datetime.now(timezone.utc).isoformat()
    expired = 0
    repriced = 0
    for d in listed:
        p = by_asin.get(d["asin"])
        if p is None:
            continue  # no data returned: benefit of the doubt, re-check next run
        price, typical, low_90d, high_90d = customer_price_from_stats(p.get("stats") or {})

        reason = None
        percent_off_now = percent_above_low = None
        if price is None or typical is None or typical <= 0:
            reason = "unavailable"
        else:
            percent_off_now = round((1 - price / typical) * 100)
            if low_90d and low_90d > 0:
                percent_above_low = round((price / low_90d - 1) * 100)
            if percent_off_now < min_off:
                reason = "discount_ended"
            elif (max_above_low is not None and percent_above_low is not None
                  and percent_above_low > max_above_low):
                # Held to the same standard as new deals: routinely far cheaper
                # than it's listed at now -> no longer a real deal.
                reason = "weak_vs_history"

        if reason:
            d["expired_at"] = now
            d["expired_reason"] = reason
            d["last_checked_price"] = price
            expired += 1
            title = (d.get("short_title") or d.get("title") or "")[:50]
            logger.info("Deal expired (%s): %s %s", reason, d["asin"], title)
        else:
            # Still qualifies -- refresh stored numbers to the current buy-box
            # reality so the live site matches what the shopper sees on Amazon.
            if (d.get("price") != price or d.get("typical_price") != typical
                    or d.get("percent_off") != percent_off_now):
                repriced += 1
            d["price"] = price
            d["typical_price"] = typical
            d["percent_off"] = percent_off_now
            d["low_90d"] = low_90d
            d["high_90d"] = high_90d
            d["percent_above_low"] = percent_above_low

    if expired:
        logger.info("%d listed deal(s) no longer qualify -- removed from the site, kept as history", expired)
    if repriced:
        logger.info("%d listed deal(s) re-priced to current buy-box values", repriced)
    return expired + repriced
