"""Posts a deal photo to a Facebook Page via the Graph API. No-ops cleanly
if not configured, matching the Telegram/Instagram pattern.

Needs a Page access token with pages_manage_posts -- see README.md for the
Meta app setup. The image is referenced by public URL (Facebook fetches it
server-side), so it must already be live on GitHub Pages before this runs.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
STATE_PATH = Path(__file__).resolve().parent.parent / "config" / "facebook_post_state.json"

# Meta fetches the image server-side. Right after a push, GitHub Pages' CDN
# can still 404 (propagation delay) or an edge can hold a stale cached 404 --
# both surface as 400s here. Retrying after a wait, with a cache-busting query
# string so Meta's fetcher can't reuse the stale edge entry, recovers them.
RETRY_DELAYS_SECONDS = (45, 90)


def select_for_posting(deals: list[dict[str, Any]], max_per_day: int) -> list[dict[str, Any]]:
    """Facebook gets a curated subset of new_deals, not every qualifying one.
    Unlike the site (lists everything) or Telegram (an opt-in channel whose
    subscribers expect frequent updates), a brand-new Page with no following
    yet is sensitive to post frequency -- posting too often reads as spam,
    suppresses organic reach, and drives unfollows. deals arrives already
    sorted best-first (see fetch_deals._deal_rank_key: confirmed best-sellers,
    then sales rank, then % off), so this just keeps the strongest ones that
    still fit in today's remaining quota."""
    today = datetime.now(timezone.utc).date().isoformat()
    state = {"date": today, "count": 0}
    if STATE_PATH.exists():
        saved = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if saved.get("date") == today:
            state = saved

    remaining = max(0, max_per_day - state["count"])
    selected = deals[:remaining]

    state["count"] += len(selected)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return selected


def post_deals(deals: list[dict[str, Any]], page_id: str | None, access_token: str | None) -> None:
    if not page_id or not access_token:
        logger.info("Facebook not configured (no page id / access token) -- skipping")
        return

    for deal in deals:
        for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
            attempt_deal = deal
            if attempt:
                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                attempt_deal = dict(deal)
                attempt_deal["image_url"] = f"{deal['image_url']}?cb={attempt}"
            try:
                _post_one(attempt_deal, page_id, access_token)
                if attempt:
                    logger.info("Facebook post for %s succeeded on retry %d", deal.get("asin"), attempt)
                break
            except requests.RequestException:
                if attempt == len(RETRY_DELAYS_SECONDS):
                    logger.exception("Failed to post deal %s to Facebook after %d attempts, continuing with the rest", deal.get("asin"), attempt + 1)
                else:
                    logger.warning("Facebook post for %s failed (attempt %d) -- retrying with cache-buster", deal.get("asin"), attempt + 1)


def _post_one(deal: dict[str, Any], page_id: str, access_token: str) -> None:
    if not deal.get("image_url"):
        logger.info("No composited image for %s, skipping Facebook post", deal.get("asin"))
        return

    caption = _build_caption(deal)
    response = requests.post(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photos",
        data={"url": deal["image_url"], "caption": caption, "access_token": access_token},
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        logger.warning("Facebook API returned an error for deal %s: %s", deal.get("asin"), body["error"])


def _build_caption(deal: dict[str, Any]) -> str:
    """Mirrors the info on the site's deal card: short title, price/rating,
    fact pills (incl. the Best Seller badge), full Amazon title, then the link."""
    lines = [deal.get("short_title") or deal["title"]]
    lines.append(f"${deal['price']:.2f} (was ${deal['typical_price']:.2f}) -- {deal['percent_off']}% OFF")
    if deal.get("rating"):
        lines.append(f"{deal['rating']}/5 stars -- {deal.get('review_count') or 0} reviews")
    lines.append("")
    lines.extend(deal.get("summary_lines", []))
    lines.append("")
    lines.append(deal["title"])
    lines.append("")
    lines.append(deal["link"])
    lines.append("")
    lines.append("As an Amazon Associate I earn from qualifying purchases.")
    lines.append("")
    # Facebook rewards fewer, targeted tags than Instagram
    lines.append("#boardgames #boardgamedeals #gamenight")
    return "\n".join(lines)
