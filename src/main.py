"""Orchestrates one run: fetch -> filter -> dedupe -> enrich -> render -> post -> log.

Usage:
    python src/main.py            # real run (needs KEEPA_API_KEY, AMAZON_ASSOCIATE_TAG)
    DRY_RUN=1 python src/main.py  # fixture data, no credentials needed, no posting
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

import affiliate  # noqa: E402
import describe  # noqa: E402
import facebook_post  # noqa: E402
import fetch_deals  # noqa: E402
import image_compose  # noqa: E402
import instagram_post  # noqa: E402
import refresh_deals  # noqa: E402
import render_site  # noqa: E402
import telegram_post  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "niche.yaml"
LOG_PATH = ROOT / "posted_log.json"

# No-op in GitHub Actions (no .env file there -- secrets come in as real env
# vars already). Lets local/Task-Scheduler runs read credentials from .env
# instead of needing them set machine-wide.
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text())


def load_log() -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    return json.loads(LOG_PATH.read_text(encoding="utf-8"))


def save_log(entries: list[dict[str, Any]]) -> None:
    LOG_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _enrich(deal: dict[str, Any], site_base_url: str) -> None:
    """Adds summary_lines / detailed_description (describe.py), image_url
    (composited price-banner image, for social posts) and site_image_url
    (plain branded thumbnail, for the website card) to a deal, in place."""
    description = describe.generate_description(deal)
    deal["summary_lines"] = description["summary_lines"]
    deal["detailed_description"] = description["detailed"]
    deal["short_title"] = description["short_title"]

    social_path, thumb_path = image_compose.compose_images(deal)
    # image_url needs to be absolute -- Facebook/Instagram's APIs fetch it
    # from their own servers. site_image_url is used by the site's own
    # <img> tags, which already live at that root, so a relative path keeps
    # working even if the domain/base path ever changes.
    deal["image_url"] = f"{site_base_url}/{social_path}" if social_path else None
    deal["site_image_url"] = thumb_path


def _push_images_if_needed(new_deals: list[dict[str, Any]]) -> None:
    """Facebook/Instagram fetch images by public URL server-side, so the
    composited images have to already be live on Pages before those API
    calls happen -- this commits+pushes mid-run, but only when at least one
    of those platforms is actually configured (otherwise it's a no-op, same
    as before this feature existed; the wrapper script's own end-of-run
    commit still covers everything else)."""
    fb_configured = bool(os.environ.get("FACEBOOK_PAGE_ID") and os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN"))
    ig_configured = bool(os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID") and os.environ.get("INSTAGRAM_ACCESS_TOKEN"))
    if not (fb_configured or ig_configured):
        return
    if not any(d.get("image_url") for d in new_deals):
        return

    logger.info("Facebook/Instagram configured -- pushing images early so their APIs can fetch them")
    subprocess.run(["git", "add", "docs/images"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode != 0:
        subprocess.run(
            ["git", "-c", "user.name=boardgame-dealbot", "-c", "user.email=actions@users.noreply.github.com",
             "commit", "-q", "-m", "Add deal images for social posting"],
            cwd=ROOT, check=True,
        )
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
    else:
        logger.info("No new images to push")


def main() -> None:
    dry_run = os.environ.get("DRY_RUN") == "1"
    config = load_config()
    log = load_log()

    # Re-check the deals currently on the site; discounts that ended come off
    # the site but stay in the log as history (see refresh_deals.py).
    if not dry_run:
        try:
            if refresh_deals.mark_expired(log, config):
                save_log(log)  # persist immediately so a later crash can't lose it
        except Exception:
            logger.exception("Deal refresh failed -- continuing with all listed deals")

    # A game whose deal expired may genuinely go on sale again later -- but
    # only after a cooldown. Without it, products whose Amazon offer flickers
    # in and out of stock bounce between expired and "new deal" every few
    # hours and spam the site/socials with reposts (seen live with Dominion
    # Prosperity on 2026-07-03).
    REPOST_COOLDOWN_DAYS = 7
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=REPOST_COOLDOWN_DAYS)
    already_posted: set[str] = set()
    for entry in log:
        expired_at = entry.get("expired_at")
        if not expired_at:
            already_posted.add(entry["asin"])
            continue
        try:
            expired = datetime.fromisoformat(expired_at)
            if expired.tzinfo is None:
                expired = expired.replace(tzinfo=timezone.utc)
            if expired >= cooldown_cutoff:
                already_posted.add(entry["asin"])
        except ValueError:
            already_posted.add(entry["asin"])  # unparseable: err on not reposting

    candidates = fetch_deals.fetch_deals(config)
    logger.info("Fetched %d candidate deals", len(candidates))

    new_deals = [d for d in candidates if d["asin"] not in already_posted]
    max_per_run = config["posting"]["max_posts_per_run"]
    new_deals = new_deals[:max_per_run]
    logger.info("%d new deals to post this run (capped at %d)", len(new_deals), max_per_run)

    amazon_domain = config["affiliate"]["amazon_domain"]
    site_base_url = config["site"]["base_url"].rstrip("/")
    now = datetime.now(timezone.utc).isoformat()
    for deal in new_deals:
        deal["link"] = affiliate.build_affiliate_link(deal["asin"], amazon_domain)
        deal["posted_at"] = now
        _enrich(deal, site_base_url)

    updated_log = new_deals + log  # newest first
    max_listed = config["posting"]["site_max_listed_deals"]
    render_site.render_site(updated_log, max_listed=max_listed)

    if new_deals and not dry_run:
        _push_images_if_needed(new_deals)
        telegram_post.post_deals(
            new_deals,
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            channel_id=os.environ.get("TELEGRAM_CHANNEL_ID"),
        )
        fb_page_id = os.environ.get("FACEBOOK_PAGE_ID")
        fb_access_token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN")
        fb_deals = (
            facebook_post.select_for_posting(new_deals, max_per_day=config["posting"]["facebook_max_posts_per_day"])
            if fb_page_id and fb_access_token
            else []
        )
        facebook_post.post_deals(fb_deals, page_id=fb_page_id, access_token=fb_access_token)
        ig_user_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        ig_access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
        ig_deals = (
            instagram_post.select_for_posting(new_deals, max_per_day=config["posting"]["instagram_max_posts_per_day"])
            if ig_user_id and ig_access_token
            else []
        )
        instagram_post.post_deals(ig_deals, ig_user_id=ig_user_id, access_token=ig_access_token)
    elif new_deals and dry_run:
        logger.info("DRY_RUN=1 -- skipping all social posting for %d deal(s)", len(new_deals))

    if dry_run:
        logger.info("DRY_RUN=1 -- not writing posted_log.json (site/ was still rebuilt for inspection)")
    else:
        save_log(updated_log)

    logger.info("Done. %d total logged deals, site rebuilt at %s", len(updated_log), render_site.SITE_DIR)


if __name__ == "__main__":
    main()
