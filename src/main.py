"""Orchestrates one run: fetch -> filter -> dedupe -> render -> post -> log.

Usage:
    python src/main.py            # real run (needs KEEPA_API_KEY, AMAZON_ASSOCIATE_TAG)
    DRY_RUN=1 python src/main.py  # fixture data, no credentials needed, no posting
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import affiliate  # noqa: E402
import fetch_deals  # noqa: E402
import render_site  # noqa: E402
import telegram_post  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "niche.yaml"
LOG_PATH = ROOT / "posted_log.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text())


def load_log() -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    return json.loads(LOG_PATH.read_text())


def save_log(entries: list[dict[str, Any]]) -> None:
    LOG_PATH.write_text(json.dumps(entries, indent=2))


def main() -> None:
    dry_run = os.environ.get("DRY_RUN") == "1"
    config = load_config()
    log = load_log()
    already_posted = {entry["asin"] for entry in log}

    candidates = fetch_deals.fetch_deals(config)
    logger.info("Fetched %d candidate deals", len(candidates))

    new_deals = [d for d in candidates if d["asin"] not in already_posted]
    max_per_run = config["posting"]["max_posts_per_run"]
    new_deals = new_deals[:max_per_run]
    logger.info("%d new deals to post this run (capped at %d)", len(new_deals), max_per_run)

    amazon_domain = config["affiliate"]["amazon_domain"]
    now = datetime.now(timezone.utc).isoformat()
    for deal in new_deals:
        deal["link"] = affiliate.build_affiliate_link(deal["asin"], amazon_domain)
        deal["posted_at"] = now

    if new_deals and not dry_run:
        telegram_post.post_deals(
            new_deals,
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            channel_id=os.environ.get("TELEGRAM_CHANNEL_ID"),
        )
    elif new_deals and dry_run:
        logger.info("DRY_RUN=1 -- skipping Telegram post for %d deal(s)", len(new_deals))

    updated_log = new_deals + log  # newest first
    max_listed = config["posting"]["site_max_listed_deals"]
    render_site.render_site(updated_log, max_listed=max_listed)

    if dry_run:
        logger.info("DRY_RUN=1 -- not writing posted_log.json (site/ was still rebuilt for inspection)")
    else:
        save_log(updated_log)

    logger.info("Done. %d total logged deals, site rebuilt at %s", len(updated_log), render_site.SITE_DIR)


if __name__ == "__main__":
    main()
