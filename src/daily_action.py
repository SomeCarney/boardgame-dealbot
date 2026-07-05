"""Picks ONE deal to post to r/boardgamedeals and hands back everything needed
to post it with near-zero effort: a pre-filled Reddit submit URL, the ready-to-
paste price-history comment, and the day-specific bonus task.

This is the engine behind the Mon/Wed/Fri routine (see marketing/GROWTH_PLAYBOOK.md).
The playbook deliberately keeps posting HUMAN-driven -- automated link posting on
a young account gets filtered/banned -- so this does the selection and drafting,
never the submitting. scripts/post_today.ps1 turns its output into one click.

Selection: the best currently-listed deal (deepest discount, tie-broken toward
proven best-sellers, then review count) that hasn't already been offered for
Reddit in the last OFFER_COOLDOWN_DAYS -- so each run surfaces something new
instead of re-suggesting the same deal every time.

Usage:
    python src/daily_action.py            # human-readable summary -> stdout + daily_action.md
    python src/daily_action.py --json     # machine-readable JSON (used by post_today.ps1)
    python src/daily_action.py --mark ASIN # record ASIN as offered so it isn't re-picked
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from safewrite import atomic_write_text

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "posted_log.json"
OFFERED_PATH = ROOT / "logs" / "reddit_offered.json"
OUT_PATH = ROOT / "daily_action.md"

SUBREDDIT = "boardgamedeals"
SUBMIT_BASE = f"https://www.reddit.com/r/{SUBREDDIT}/submit"
OFFER_COOLDOWN_DAYS = 30  # don't re-surface the same deal for Reddit within this window

# Day-specific bonus from the playbook's weekly routine. Monday is just the core
# post; Wed/Fri add a second light task.
BONUS_BY_DAY = {
    "Monday": "That's the whole task today — one clean post.",
    "Wednesday": "Bonus (10 min): answer 2-3 questions in r/boardgames' Daily Discussion thread. "
                 "Answer genuinely first; only link a guide if it directly answers the question.",
    "Friday": "Bonus (5 min): Instagram sweep — reply to every comment and follow 10-15 accounts "
              "that recently posted under #boardgamedeals or #boardgamenight.",
}
DEFAULT_BONUS = "Post the clean link to r/boardgamedeals; that's the core task."


def _clean_link(link: str) -> str:
    """Strip the affiliate tag -- Reddit bans affiliate links. Handles the tag
    appearing as the first (?tag=) or a later (&tag=) parameter without leaving
    a dangling separator behind."""
    no_tag = re.sub(r"([?&])tag=[^&]*", r"\1", link)
    no_tag = no_tag.replace("?&", "?").replace("&&", "&")
    return no_tag.rstrip("?&")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _offered_asins() -> dict[str, str]:
    """{asin: iso_timestamp} of deals already offered for Reddit, pruned to the
    cooldown window so a genuinely-still-great deal can eventually resurface."""
    raw = _load_json(OFFERED_PATH, {})
    if not isinstance(raw, dict):
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=OFFER_COOLDOWN_DAYS)
    kept: dict[str, str] = {}
    for asin, ts in raw.items():
        try:
            when = datetime.fromisoformat(str(ts))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if when >= cutoff:
            kept[asin] = ts
    return kept


def _rank_key(deal: dict):
    """Best-for-a-deal-community first: deepest discount, then proven best
    sellers, then most-reviewed (popularity travels furthest on r/boardgamedeals)."""
    return (
        -(deal.get("percent_off") or 0),
        0 if deal.get("is_best_seller") else 1,
        -(deal.get("review_count") or 0),
    )


def pick_deal() -> dict | None:
    log = _load_json(LOG_PATH, [])
    offered = _offered_asins()
    active = [
        d for d in log
        if not d.get("expired_at")
        and d.get("link")
        and d.get("asin") not in offered
        and (d.get("percent_off") or 0) > 0
    ]
    if not active:
        return None
    active.sort(key=_rank_key)
    return active[0]


# ── subreddit routing ────────────────────────────────────────────────────────
# A deal goes to ONE best-fit subreddit (instead of, not in addition to,
# r/boardgamedeals). This list is deliberately small: it only contains subs that
# actually WELCOME deal posts. Posting a deal to a sub that bans self-promo gets
# the account filtered/banned (see GROWTH_PLAYBOOK.md) -- so extend with care,
# only after checking a sub's rules allow price/deal posts. Each entry maps a
# subreddit to (comment_prefix, use_retailer_title_prefix).
_SUB_PRESENTATION = {
    "boardgamedeals":      ("", True),                          # catch-all; deals are the whole point
    "soloboardgaming":     ("Fellow solo gamers — ", False),    # 1-player-only games
    "twoplayerboardgames": ("For the 2-player shelf — ", False),  # 2-player-only games
}


def choose_subreddit(deal: dict) -> str:
    """Pick the single best-fit deal-friendly subreddit for a game, from its
    extracted player count. Only niche subs known to welcome deals are used;
    everything else falls back to r/boardgamedeals."""
    try:
        from describe import extract_facts
        facts = extract_facts(deal)
    except Exception:
        return "boardgamedeals"
    maxp = facts.get("max_players")
    if maxp == 1:
        return "soloboardgaming"        # designed for one player, not just "supports solo"
    if maxp == 2:
        return "twoplayerboardgames"    # strictly two-player (duels, 2p-only games)
    return "boardgamedeals"


def build_action(deal: dict) -> dict:
    title_name = deal.get("short_title") or deal.get("title", "")
    price = deal.get("price", 0) or 0
    was = deal.get("typical_price", 0) or 0          # 90-day average -- the number we stand on
    off = deal.get("percent_off", 0) or 0            # % BELOW the 90-day average
    rating = deal.get("rating")
    reviews = deal.get("review_count")
    clean = _clean_link(deal.get("link", ""))

    # Verification data (present on deals posted after the deal-verification
    # change; absent on older log entries -- fall back gracefully).
    has_amazon = "amazon_percent_off" in deal and deal.get("list_price")
    amazon_off = deal.get("amazon_percent_off")
    list_price = deal.get("list_price")
    low_90d = deal.get("low_90d")
    above_low = deal.get("percent_above_low")
    at_90d_low = above_low == 0

    # Send the deal to the single best-fit deal-friendly subreddit (see
    # choose_subreddit). Niche subs (solo, 2-player) aren't deal-first and have
    # no "[Retailer]" title convention, so they get a plainer title.
    subreddit = choose_subreddit(deal)
    comment_prefix, use_retailer_prefix = _SUB_PRESENTATION.get(subreddit, ("", True))

    # Title carries the brand's whole thesis: the discount is measured against
    # the real 90-day average, not a sticker. "Lowest in 90 days" is a genuine,
    # widely-respected deal-hunter signal (only claimed when it's actually true).
    low_tag = " — lowest in 90 days" if at_90d_low else ""
    if use_retailer_prefix:
        post_title = f"[Amazon] {title_name} - ${price:.2f} ({off}% below 90-day avg{low_tag})"
    else:
        post_title = f"{title_name} - ${price:.2f} ({off}% below 90-day avg{low_tag})"

    # Comment: the "90 Day Average" voice -- data first, confident, not preachy.
    core = f"Against the real 90-day average of ${was:.2f}, this is {off}% below."
    if has_amazon and amazon_off and amazon_off > off + 3:
        body = (
            f"That \"{amazon_off}% off\" badge is theater -- it's measured against a "
            f"${list_price:.2f} list price this game basically never sells at. {core}"
        )
    elif has_amazon and not amazon_off:
        body = (
            f"Amazon isn't even flagging this as a sale, but {core[0].lower()}{core[1:]} "
            "The kind of quiet drop a sticker price will never show you."
        )
    else:
        body = f"You can't trust the sticker \"% off\" online. {core}"

    extras = []
    if at_90d_low:
        extras.append("It's also the lowest it's been in the last 90 days.")
    elif low_90d:
        extras.append(f"(90-day low was ${low_90d:.2f} — full transparency.)")
    if rating and reviews:
        extras.append(f"{rating}/5 from {reviews:,} ratings.")
    comment = " ".join([body, *extras])
    if comment_prefix:
        comment = comment_prefix + comment

    submit_base = f"https://www.reddit.com/r/{subreddit}/submit"
    submit_url = f"{submit_base}?url={quote(clean, safe='')}&title={quote(post_title, safe='')}"
    day = datetime.now().strftime("%A")
    return {
        "has_deal": True,
        "asin": deal.get("asin", ""),
        "title": post_title,
        "clean_link": clean,
        "comment": comment,
        "submit_url": submit_url,
        "subreddit": subreddit,
        "bonus": BONUS_BY_DAY.get(day, DEFAULT_BONUS),
        "day": day,
    }


def mark_offered(asin: str) -> None:
    offered = _offered_asins()
    offered[asin] = datetime.now(timezone.utc).isoformat()
    OFFERED_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(OFFERED_PATH, json.dumps(offered, indent=2))


def _write_markdown(action: dict) -> None:
    if not action.get("has_deal"):
        body = (
            "# Today's Reddit post\n\n"
            "No fresh, un-shared deal to post right now. Skipping today is fine — "
            "consistency matters more than forcing a post. Check back after the next bot run.\n"
        )
    else:
        body = f"""# Today's Reddit post — r/{action.get('subreddit', SUBREDDIT)}

**1. Post this as a LINK post** (the desktop shortcut / phone button opens it pre-filled):

- Title: `{action['title']}`
- URL:   `{action['clean_link']}`

**2. Then paste this as the top comment** (already on your clipboard if you used the shortcut):

> {action['comment']}

**Today ({action['day']}):** {action['bonus']}

One-click submit link:
{action['submit_url']}
"""
    atomic_write_text(OUT_PATH, body)


def main() -> int:
    if "--mark" in sys.argv:
        i = sys.argv.index("--mark")
        if i + 1 < len(sys.argv):
            mark_offered(sys.argv[i + 1])
            return 0
        print("--mark requires an ASIN", file=sys.stderr)
        return 1

    deal = pick_deal()
    action = build_action(deal) if deal else {"has_deal": False}
    _write_markdown(action)

    if "--json" in sys.argv:
        print(json.dumps(action))
    elif action.get("has_deal"):
        print(f"Today's pick: {action['title']}")
        print(f"  Link:    {action['clean_link']}")
        print(f"  Comment: {action['comment']}")
        print(f"  Submit:  {action['submit_url']}")
        print(f"  {action['day']}: {action['bonus']}")
    else:
        print("No fresh, un-shared deal to post right now — skipping today is fine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
