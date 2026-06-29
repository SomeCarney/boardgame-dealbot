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
    text = (
        f"<b>{_escape(deal['title'])}</b>\n"
        f"${deal['price']:.2f} (was ~${deal['typical_price']:.2f}, {deal['percent_off']}% off)\n"
        f"{deal['link']}"
    )
    payload = {
        "chat_id": channel_id,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "text": text,
    }

    if deal.get("image"):
        endpoint = f"{API_BASE}/bot{bot_token}/sendPhoto"
        payload["photo"] = deal["image"]
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
