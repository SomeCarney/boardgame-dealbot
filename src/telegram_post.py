"""Optional secondary push channel. No-ops cleanly if not configured so the
core pipeline (site generation) never depends on Telegram being set up."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def post_deals(deals: list[dict[str, Any]], bot_token: str | None, channel_id: str | None) -> None:
    if not bot_token or not channel_id:
        logger.info("Telegram not configured (no bot token / channel id) -- skipping")
        return

    for deal in deals:
        try:
            _send_one(deal, bot_token, channel_id)
        except requests.RequestException:
            logger.exception("Failed to post deal %s to Telegram, continuing with the rest", deal.get("asin"))


def _send_one(deal: dict[str, Any], bot_token: str, channel_id: str) -> None:
    lines = [
        f"<b>{_escape(deal['title'])}</b>",
        f"${deal['price']:.2f} (was ~${deal['typical_price']:.2f}, {deal['percent_off']}% off)",
    ]
    lines.extend(_escape(line) for line in deal.get("summary_lines", []))
    if deal.get("detailed_description"):
        lines.append(_escape(deal["detailed_description"]))
    lines.append(deal["link"])
    text = "\n".join(lines)

    payload = {
        "chat_id": channel_id,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "text": text,
    }

    # Prefer the composited price-banner image (consistent look across
    # every channel); fall back to the raw Amazon image if compositing
    # didn't produce one for some reason.
    image = deal.get("image_url") or deal.get("image")
    if image:
        endpoint = f"{API_BASE}/bot{bot_token}/sendPhoto"
        payload["photo"] = image
        payload["caption"] = text
        payload["parse_mode"] = "HTML"
        del payload["text"]
        del payload["disable_web_page_preview"]
    else:
        endpoint = f"{API_BASE}/bot{bot_token}/sendMessage"

    response = requests.post(endpoint, data=payload, timeout=15)
    response.raise_for_status()
    if not response.json().get("ok", False):
        logger.warning("Telegram API returned ok=false for deal %s: %s", deal.get("asin"), response.text)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
