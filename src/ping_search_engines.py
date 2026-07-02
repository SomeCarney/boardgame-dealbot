"""Notifies search engines of new/changed pages via IndexNow.

IndexNow is a free, no-account protocol supported by Bing, DuckDuckGo,
Yandex, Seznam, and Naver. (Google does not support it -- Google discovery
comes from Search Console + the sitemap.) The key file in docs/ proves we
own the URLs we submit.

Usage:
    python src/ping_search_engines.py          # homepage + deal feed (per-run)
    python src/ping_search_engines.py --all    # every sitemap URL (monthly / after big changes)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SITEMAP = ROOT / "docs" / "sitemap.xml"

HOST = "somecarney.github.io"
BASE_URL = f"https://{HOST}/boardgame-dealbot"
KEY = "a030601df76890afffddfac483957bef"
KEY_LOCATION = f"{BASE_URL}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"


def sitemap_urls() -> list[str]:
    if not SITEMAP.exists():
        return []
    return re.findall(r"<loc>(.*?)</loc>", SITEMAP.read_text(encoding="utf-8"))


def ping(urls: list[str]) -> int:
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }
    resp = requests.post(ENDPOINT, json=payload, timeout=20)
    print(f"IndexNow: submitted {len(urls)} URL(s) -> HTTP {resp.status_code}")
    if resp.status_code not in (200, 202):
        print(resp.text[:500])
        return 1
    return 0


def main() -> int:
    if "--all" in sys.argv:
        urls = sitemap_urls()
        if not urls:
            print("No sitemap URLs found -- run a site render first.")
            return 1
    else:
        # Per-run: only the pages whose content actually changed this run.
        urls = [f"{BASE_URL}/", f"{BASE_URL}/deals.xml"]
    return ping(urls)


if __name__ == "__main__":
    sys.exit(main())
