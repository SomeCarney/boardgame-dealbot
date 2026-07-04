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

from fetch_deals import IDX_AMAZON_PRICE, _at, _cents_to_dollars, _interval_value

logger = logging.getLogger(__name__)


def mark_expired(log: list[dict[str, Any]], config: dict[str, Any]) -> int:
    """Marks stale listed deals in place. Returns how many expired."""
    max_listed = config["posting"]["site_max_listed_deals"]
    min_off = config["deal_filters"]["min_percent_off"]
    max_above_low = config["deal_filters"].get("max_percent_above_90d_low")
    listed = [d for d in log if not d.get("expired_at")][:max_listed]
    if not listed:
        return 0

    import keepa
    api = keepa.Keepa(os.environ["KEEPA_API_KEY"])
    try:
        products = api.query(
            [d["asin"] for d in listed],
            stats=90, rating=True, domain=config["niche"]["domain"],
            progress_bar=False, history=False,
        )
    except Exception:
        logger.exception("Deal refresh query failed -- keeping all listed deals this run")
        return 0

    by_asin = {p.get("asin"): p for p in products}
    now = datetime.now(timezone.utc).isoformat()
    expired = 0
    for d in listed:
        p = by_asin.get(d["asin"])
        if p is None:
            continue  # no data returned: benefit of the doubt, re-check next run
        stats = p.get("stats") or {}
        price = _cents_to_dollars(_at(stats.get("current") or [], IDX_AMAZON_PRICE))
        typical = _cents_to_dollars(_at(stats.get("avg90") or [], IDX_AMAZON_PRICE))
        low_90d = _cents_to_dollars(_interval_value(stats.get("minInInterval") or [], IDX_AMAZON_PRICE))

        reason = None
        if price is None:
            reason = "unavailable"
        elif typical and typical > 0 and round((1 - price / typical) * 100) < min_off:
            reason = "discount_ended"
        elif (max_above_low is not None and low_90d and low_90d > 0
              and round((price / low_90d - 1) * 100) > max_above_low):
            # Held to the same standard as new deals: if the item is routinely
            # far cheaper than it's listed at now, it's no longer a real deal.
            reason = "weak_vs_history"

        if reason:
            d["expired_at"] = now
            d["expired_reason"] = reason
            d["last_checked_price"] = price
            expired += 1
            title = (d.get("short_title") or d.get("title") or "")[:50]
            logger.info("Deal expired (%s): %s %s", reason, d["asin"], title)

    if expired:
        logger.info("%d listed deal(s) no longer qualify -- removed from the site, kept as history", expired)
    return expired
