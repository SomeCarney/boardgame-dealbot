"""Posts a deal photo to a Facebook Page via the Graph API. No-ops cleanly
if not configured, matching the Telegram/Instagram pattern.

Needs a Page access token with pages_manage_posts -- see README.md for the
Meta app setup. The image is referenced by public URL (Facebook fetches it
server-side), so it must already be live on GitHub Pages before this runs.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"


def post_deals(deals: list[dict[str, Any]], page_id: str | None, access_token: str | None) -> None:
    if not page_id or not access_token:
        logger.info("Facebook not configured (no page id / access token) -- skipping")
        return

    for deal in deals:
        try:
            _post_one(deal, page_id, access_token)
        except requests.RequestException:
            logger.exception("Failed to post deal %s to Facebook, continuing with the rest", deal.get("asin"))


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
    lines = [deal["title"], ""]
    lines.extend(deal.get("summary_lines", []))
    if deal.get("detailed_description"):
        lines.append("")
        lines.append(deal["detailed_description"])
    lines.append("")
    lines.append(deal["link"])
    lines.append("")
    lines.append("As an Amazon Associate I earn from qualifying purchases.")
    return "\n".join(lines)
