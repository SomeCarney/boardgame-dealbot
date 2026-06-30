"""Regenerates descriptions and composited images for every deal already in
posted_log.json, using the current describe.py / image_compose.py logic,
then re-renders the site. Re-run this any time the visual design changes
(new color theme, new card layout, etc.) so already-posted deals pick up
the new look immediately instead of waiting for new deals to trickle in.

Usage: .venv\\Scripts\\python.exe scripts\\rebuild_visuals.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import describe  # noqa: E402
import image_compose  # noqa: E402
import render_site  # noqa: E402
import yaml  # noqa: E402

LOG_PATH = ROOT / "posted_log.json"
CONFIG_PATH = ROOT / "config" / "niche.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    site_base_url = config["site"]["base_url"].rstrip("/")
    deals = json.loads(LOG_PATH.read_text(encoding="utf-8"))

    for i, deal in enumerate(deals, 1):
        description = describe.generate_description(deal)
        deal["summary_lines"] = description["summary_lines"]
        deal["detailed_description"] = description["detailed"]

        social_path, thumb_path = image_compose.compose_images(deal)
        deal["image_url"] = f"{site_base_url}/{social_path}" if social_path else None
        deal["site_image_url"] = thumb_path
        print(f"[{i}/{len(deals)}] {deal['asin']}: {deal['title'][:50]}")

    LOG_PATH.write_text(json.dumps(deals, indent=2), encoding="utf-8")
    max_listed = config["posting"]["site_max_listed_deals"]
    render_site.render_site(deals, max_listed=max_listed)
    print(f"Done. Rebuilt visuals for {len(deals)} deals and re-rendered the site.")


if __name__ == "__main__":
    main()
