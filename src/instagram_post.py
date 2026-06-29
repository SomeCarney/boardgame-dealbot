"""Posts a deal photo to Instagram via the Graph API. No-ops cleanly if not
configured, matching the Telegram/Facebook pattern.

Needs an Instagram Business/Creator account linked to a Facebook Page, a
Meta app, and instagram_content_publish permission -- this specifically
requires Meta App Review (commonly rejected on the first submission, no
fixed timeline) -- see README.md. The image must already be live on GitHub
Pages before this runs, since Instagram fetches it by URL server-side.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
POLL_INTERVAL_SECONDS = 2
POLL_MAX_ATTEMPTS = 15


def post_deals(deals: list[dict[str, Any]], ig_user_id: str | None, access_token: str | None) -> None:
    if not ig_user_id or not access_token:
        logger.info("Instagram not configured (no business account id / access token) -- skipping")
        return

    for deal in deals:
        try:
            _post_one(deal, ig_user_id, access_token)
        except requests.RequestException:
            logger.exception("Failed to post deal %s to Instagram, continuing with the rest", deal.get("asin"))


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
