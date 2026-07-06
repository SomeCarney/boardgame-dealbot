"""Posts each new deal to X (Twitter) via the API v2 create-tweet endpoint.
No-ops cleanly if not configured, matching the Telegram/Facebook/Instagram
pattern -- the core pipeline never depends on X being set up.

Unlike Reddit/BGG, X *allows* affiliate links, so the tweet uses the real
tagged link (deal["link"]) and includes an #ad disclosure.

Auth is OAuth 1.0a user-context, signed with the standard library (hmac +
hashlib) so there's no extra dependency. Needs four values in the environment
(from an X developer app with Read+Write, see README/notes):
    TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
import urllib.parse
from typing import Any

import requests

logger = logging.getLogger(__name__)

TWEET_ENDPOINT = "https://api.twitter.com/2/tweets"
MAX_TWEET_LEN = 280


# X shortens every URL to a t.co link of this fixed length, regardless of the
# real URL length, when counting toward the 280 limit.
TCO_LEN = 23


class CreditsExhausted(RuntimeError):
    """X returned 402 / a credits problem -- the API account can't post without a
    paid plan or credits it doesn't have. Not a bug on our side; auth is fine."""


def post_deals(deals: list[dict[str, Any]], api_key: str | None, api_secret: str | None,
               access_token: str | None, access_secret: str | None) -> None:
    if not (api_key and api_secret and access_token and access_secret):
        logger.info("X/Twitter not configured (missing API keys) -- skipping")
        return
    creds = (api_key, api_secret, access_token, access_secret)
    for deal in deals:
        try:
            _post_one(deal, creds)
        except CreditsExhausted:
            # X now meters posting; a free account with no credits can't post.
            # One calm line, then stop trying this run -- no per-deal error spam.
            logger.warning("X posting skipped -- the API account has no posting credits "
                           "(X requires a paid/credited plan to post). Auth is fine.")
            return
        except requests.RequestException:
            logger.exception("Failed to post deal %s to X, continuing with the rest", deal.get("asin"))


def _post_one(deal: dict[str, Any], creds: tuple[str, str, str, str]) -> None:
    text = _build_tweet(deal)
    auth = _oauth_header("POST", TWEET_ENDPOINT, creds)
    resp = requests.post(
        TWEET_ENDPOINT,
        json={"text": text},
        headers={"Authorization": auth, "Content-Type": "application/json"},
        timeout=20,
    )
    if resp.status_code == 402 or "problems/credits" in resp.text:
        raise CreditsExhausted(resp.text[:200])
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        logger.warning("X API returned an error for deal %s: %s", deal.get("asin"), body["errors"])
    else:
        logger.info("Tweeted deal %s", deal.get("asin"))


def _build_tweet(deal: dict[str, Any]) -> str:
    """Concise 'below the 90-day average' tweet with the affiliate link + #ad."""
    title = deal.get("short_title") or deal.get("title", "")
    price = deal.get("price", 0) or 0
    off = deal.get("percent_off", 0) or 0
    link = deal.get("link", "")
    low_tag = " · lowest in 90 days" if deal.get("percent_above_low") == 0 else ""
    tags = "#boardgames #boardgamedeals #ad"

    # budget the title so the whole tweet fits 280 (link counts as TCO_LEN)
    fixed = f"🎲  — ${price:.2f} ({off}% below its 90-day average{low_tag})\n\n\n{tags}"
    room = MAX_TWEET_LEN - len(fixed) - TCO_LEN
    if len(title) > room and room > 3:
        title = title[:room - 1].rstrip() + "…"
    return f"🎲 {title} — ${price:.2f} ({off}% below its 90-day average{low_tag})\n{link}\n\n{tags}"


# ── OAuth 1.0a signing (stdlib) ──────────────────────────────────────────────

def _pct(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~")


def _oauth_header(method: str, url: str, creds: tuple[str, str, str, str]) -> str:
    api_key, api_secret, access_token, access_secret = creds
    oauth = {
        "oauth_consumer_key": api_key,
        "oauth_token": access_token,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": secrets.token_hex(16),
        "oauth_version": "1.0",
    }
    # For a JSON body the request body is NOT part of the signature base string;
    # only the oauth_* params (and any query params, of which there are none) are.
    param_str = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(oauth.items()))
    base = "&".join([method.upper(), _pct(url), _pct(param_str)])
    signing_key = f"{_pct(api_secret)}&{_pct(access_secret)}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    oauth["oauth_signature"] = signature
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))
