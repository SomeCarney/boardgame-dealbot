"""Generates ready-to-paste community post drafts from recent deals.

Writes social_drafts.md (gitignored) with per-platform text for the freshest
deals. Reddit/BGG drafts use CLEAN Amazon links (no affiliate tag) because
those communities ban affiliate links -- the site link only appears in the
formats where it's allowed. Run automatically after each bot run, or manually:

    python src/make_social_drafts.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "posted_log.json"
OUT_PATH = ROOT / "social_drafts.md"
SITE_URL = "https://somecarney.github.io/boardgame-dealbot/"

MAX_DRAFTS = 3
FRESH_WINDOW_HOURS = 26  # a bit over the 24h cadence so nothing slips through


def _clean_link(link: str) -> str:
    """Strip the affiliate tag -- Reddit and BGG ban affiliate links."""
    return re.sub(r"[?&]tag=[^&]+", "", link).rstrip("?&")


def _fresh_deals() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESH_WINDOW_HOURS)
    fresh = []
    for d in log:
        try:
            posted = datetime.fromisoformat(str(d.get("posted_at", "")).replace("Z", "+00:00"))
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if posted >= cutoff:
            fresh.append(d)
    # deepest discounts first -- those travel furthest in deal communities
    fresh.sort(key=lambda d: d.get("percent_off") or 0, reverse=True)
    return fresh[:MAX_DRAFTS]


def _draft_for(deal: dict) -> str:
    title = deal.get("short_title") or deal.get("title", "")
    full_title = deal.get("title", "")
    price = deal.get("price", 0)
    was = deal.get("typical_price", 0)
    off = deal.get("percent_off", 0)
    rating = deal.get("rating")
    reviews = deal.get("review_count")
    clean = _clean_link(deal.get("link", ""))

    rating_line = f" {rating}/5 from {reviews:,} reviews." if rating and reviews else ""

    return f"""### {title} — ${price:.2f} ({off}% off)

**Reddit r/boardgamedeals** (submit as LINK post to the clean Amazon URL; no affiliate links allowed there)

> Title: `[Amazon] {title} - ${price:.2f} ({off}% off, usually ~${was:.2f})`
> Link:  `{clean}`
> Comment to add after posting: `Price is checked against 90-day price history, so the "was" price is real, not an inflated list price.{rating_line}`

**BoardGameGeek — Bargains forum** (clean link only)

> {title} is ${price:.2f} on Amazon right now, down from a 90-day typical of ${was:.2f} ({off}% off).{rating_line}
> {clean}

**Facebook group / Discord** (casual, site mention okay where group rules allow)

> Solid drop on {full_title[:80]} — ${price:.2f}, usually closer to ${was:.2f}. We track these against real price history over at {SITE_URL} if you want the full list.

**X / Twitter**

> {title} just dropped to ${price:.2f} ({off}% off the 90-day typical). More verified drops: {SITE_URL} #boardgames #boardgamedeals

---
"""


def main() -> None:
    deals = _fresh_deals()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not deals:
        body = f"# Social drafts — {now}\n\nNo deals posted in the last {FRESH_WINDOW_HOURS}h. Nothing to share right now.\n"
    else:
        intro = (
            f"# Social drafts — {now}\n\n"
            f"Copy-paste-ready posts for the {len(deals)} freshest deal(s), deepest discount first.\n"
            "Reddit/BGG drafts use CLEAN links (no affiliate tag) — their rules require it.\n"
            "Post at most ONE deal per community per day. See marketing/GROWTH_PLAYBOOK.md.\n\n"
        )
        body = intro + "\n".join(_draft_for(d) for d in deals)
    OUT_PATH.write_text(body, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(deals)} draft(s))")


if __name__ == "__main__":
    main()
