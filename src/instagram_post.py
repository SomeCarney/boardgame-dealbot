"""Posts a deal photo to Instagram via the Graph API. No-ops cleanly if not
configured, matching the Telegram/Facebook pattern.

Needs an Instagram Business/Creator account linked to a Facebook Page, a
Meta app, and instagram_content_publish permission -- this specifically
requires Meta App Review (commonly rejected on the first submission, no
fixed timeline) -- see README.md. The image must already be live on GitHub
Pages before this runs, since Instagram fetches it by URL server-side.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from safewrite import atomic_write_text

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
POLL_INTERVAL_SECONDS = 2
POLL_MAX_ATTEMPTS = 15
STATE_PATH = Path(__file__).resolve().parent.parent / "config" / "instagram_post_state.json"

# Instagram fetches the image server-side. Right after a push, GitHub Pages'
# CDN can still 404 (propagation delay) or an edge can hold a stale cached
# 404 -- both surface as 400 "media could not be fetched" errors. Retrying
# after a wait, with a cache-busting query string so Meta's fetcher can't
# reuse the stale edge entry, recovers them (verified live 2026-07-02).
RETRY_DELAYS_SECONDS = (45, 90)


def select_for_posting(deals: list[dict[str, Any]], max_per_day: int) -> list[dict[str, Any]]:
    """Same reasoning as facebook_post.select_for_posting: a brand-new account
    with no following is sensitive to post frequency, so Instagram gets a
    curated subset of the day's best-ranked deals rather than every one."""
    today = datetime.now(timezone.utc).date().isoformat()
    state = {"date": today, "count": 0}
    if STATE_PATH.exists():
        try:
            saved = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if saved.get("date") == today:
                state = saved
        except json.JSONDecodeError:
            logger.warning("daily post-quota state corrupt -- resetting")

    remaining = max(0, max_per_day - state["count"])
    selected = deals[:remaining]

    state["count"] += len(selected)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(STATE_PATH, json.dumps(state, indent=2))
    return selected


def post_deals(deals: list[dict[str, Any]], ig_user_id: str | None, access_token: str | None) -> None:
    if not ig_user_id or not access_token:
        logger.info("Instagram not configured (no business account id / access token) -- skipping")
        return

    for deal in deals:
        for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
            attempt_deal = deal
            if attempt:
                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                attempt_deal = dict(deal)
                attempt_deal["image_url"] = f"{deal['image_url']}?cb={attempt}"
            try:
                _post_one(attempt_deal, ig_user_id, access_token)
                if attempt:
                    logger.info("Instagram post for %s succeeded on retry %d", deal.get("asin"), attempt)
                break
            except requests.RequestException as exc:
                if attempt == len(RETRY_DELAYS_SECONDS):
                    logger.exception("Failed to post deal %s to Instagram after %d attempts, continuing with the rest", deal.get("asin"), attempt + 1)
                    from facebook_post import record_failure
                    record_failure(deal.get("asin"), "instagram", str(exc))
                else:
                    logger.warning("Instagram post for %s failed (attempt %d) -- retrying with cache-buster", deal.get("asin"), attempt + 1)


def _post_one(deal: dict[str, Any], ig_user_id: str, access_token: str) -> None:
    if not deal.get("image_url"):
        logger.info("No composited image for %s, skipping Instagram post", deal.get("asin"))
        return

    base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_user_id}"
    caption = _build_caption(deal)

    create_response = requests.post(
        f"{base_url}/media",
        data={"image_url": deal["image_url"], "caption": caption, "access_token": access_token},
        timeout=20,
    )
    create_response.raise_for_status()
    container_id = create_response.json().get("id")
    if not container_id:
        logger.warning("Instagram media container creation returned no id for %s: %s", deal.get("asin"), create_response.text)
        return

    if not _wait_until_ready(base_url, container_id, access_token):
        logger.warning("Instagram media container for %s never finished processing, skipping publish", deal.get("asin"))
        return

    publish_response = requests.post(
        f"{base_url}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=20,
    )
    publish_response.raise_for_status()
    body = publish_response.json()
    if "error" in body:
        logger.warning("Instagram publish returned an error for deal %s: %s", deal.get("asin"), body["error"])


def _wait_until_ready(base_url: str, container_id: str, access_token: str) -> bool:
    for _ in range(POLL_MAX_ATTEMPTS):
        status_response = requests.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=15,
        )
        status_response.raise_for_status()
        status = status_response.json().get("status_code")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            return False
        time.sleep(POLL_INTERVAL_SECONDS)
    return False


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
    # Discovery hashtags: mix of large (reach) and mid-size (ranking) tags.
    lines.append(
        "#boardgames #boardgamedeals #tabletopgames #boardgamegeek #gamenight "
        "#familygamenight #boardgamer #tabletopgaming #boardgamesofinstagram #boardgameaddict"
    )
    caption = "\n".join(lines)
    # Instagram rejects captions over 2,200 chars. Degrade gracefully: drop
    # the verbose Amazon listing title first, never the link or disclosure.
    if len(caption) > 2200:
        caption = "\n".join(line for line in lines if line != deal["title"])
    if len(caption) > 2200:
        caption = caption[:2197] + "..."
    return caption
