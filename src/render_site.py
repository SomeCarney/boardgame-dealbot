"""Regenerates the static GitHub Pages site.

content/*.html files are hand-written evergreen pages, copied through as-is
inside the shared layout. index.html is rebuilt from the current deal list
on every run. This keeps the site looking active (Amazon expects "recent"
content) without ever touching the hand-written pages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
# GitHub Pages "deploy from a branch" only accepts / or /docs as the served
# path -- docs/ it is, even though "site" would have been a clearer name.
SITE_DIR = ROOT / "docs"

SITE_NAME = "Tabletop Tracker"
TAGLINE = "Automatically tracked board game price drops on Amazon."
DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases."

# filename in content/ -> (output filename, nav title, <meta description>)
EVERGREEN_PAGES: list[tuple[str, str, str, str]] = [
    ("about.html", "about.html", "About", "What Tabletop Tracker is and why it exists."),
    ("how-we-pick-deals.html", "how-we-pick-deals.html", "How We Pick Deals", "The exact criteria a deal has to clear before it's posted."),
    ("guide-reading-price-history.html", "guide-reading-price-history.html", "Is This Deal Actually Good?", "How to read a price history before trusting a 'deal'."),
    ("guide-2-player-games.html", "guide-2-player-games.html", "Best 2-Player Games", "Which 2-player board games are worth buying at full price."),
    ("guide-party-vs-strategy.html", "guide-party-vs-strategy.html", "Party vs. Strategy Games", "What to buy for different group sizes and crowds."),
    ("guide-storage-sleeving.html", "guide-storage-sleeving.html", "Storage & Sleeving", "Whether card sleeves and storage inserts are worth it."),
    ("guide-seasonal-sales.html", "guide-seasonal-sales.html", "When Sales Actually Happen", "Seasonal patterns in board game pricing worth knowing."),
    ("guide-kickstarter-vs-retail.html", "guide-kickstarter-vs-retail.html", "Kickstarter vs. Retail", "What changes between a Kickstarter exclusive and the retail edition."),
    ("guide-gateway-games.html", "guide-gateway-games.html", "Gateway Games", "What to buy someone who's never played a 'real' board game."),
    ("guide-warehouse-used.html", "guide-warehouse-used.html", "Amazon Warehouse & Used", "How used/warehouse listings work and when they're worth it."),
]

GUIDE_SLUGS = {f for f in EVERGREEN_PAGES if f[0].startswith("guide-")}

env = Environment(autoescape=select_autoescape(["html"]))

BASE_TEMPLATE = env.from_string("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | {{ site_name }}</title>
<meta name="description" content="{{ description }}">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="site-header">
  <a class="brand" href="index.html">{{ site_name }}</a>
  <p class="tagline">{{ tagline }}</p>
  <nav>
    <a href="index.html">Deals</a>
    <a href="about.html">About</a>
    <a href="how-we-pick-deals.html">How We Pick Deals</a>
    <a href="guides.html">Guides</a>
  </nav>
</header>
<main>
{{ content|safe }}
</main>
<footer class="site-footer">
  <p>{{ disclosure }}</p>
  <p>Last updated {{ updated }} UTC.</p>
</footer>
</body>
</html>
""")

DEAL_CARD_TEMPLATE = env.from_string("""
<article class="deal">
  {# the composited price-banner image (deal.image_url) is for social posts,
     which have no separate price text around them -- the site already has
     its own price/rating block below, so the plain product photo fits better #}
  {% if deal.image %}<img src="{{ deal.image }}" alt="" loading="lazy">{% endif %}
  <div class="deal-body">
    <h2><a href="{{ deal.link }}" rel="nofollow sponsored noopener" target="_blank">{{ deal.title }}</a></h2>
    <p class="price">
      <span class="now">${{ "%.2f"|format(deal.price) }}</span>
      <span class="was">was ~${{ "%.2f"|format(deal.typical_price) }}</span>
      <span class="off">{{ deal.percent_off }}% off</span>
    </p>
    {% if deal.rating %}<p class="rating">{{ deal.rating }}/5 ({{ deal.review_count }} reviews)</p>{% endif %}
    {% if deal.summary_lines %}
    <ul class="facts">
      {% for line in deal.summary_lines %}<li>{{ line }}</li>{% endfor %}
    </ul>
    {% endif %}
    {% if deal.detailed_description %}<p class="detail">{{ deal.detailed_description }}</p>{% endif %}
    <a class="buy" href="{{ deal.link }}" rel="nofollow sponsored noopener" target="_blank">View on Amazon &rarr;</a>
  </div>
</article>
""")

INDEX_CONTENT_TEMPLATE = env.from_string("""
<h1>Current Board Game Deals</h1>
<p>{{ tagline }} Re-checked every few hours; nothing here is older than a few days.</p>
{% if deals_html %}
<div class="deal-grid">{{ deals_html|safe }}</div>
{% else %}
<p>No qualifying deals right now &mdash; check back soon.</p>
{% endif %}
""")

GUIDES_INDEX_TEMPLATE = env.from_string("""
<h1>Guides</h1>
<ul class="guide-list">
{% for href, title, description in guides %}
  <li><a href="{{ href }}">{{ title }}</a> &mdash; {{ description }}</li>
{% endfor %}
</ul>
""")

STYLE_CSS = """
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 0 1rem 3rem; line-height: 1.5; }
.site-header { padding: 1.5rem 0 1rem; border-bottom: 1px solid #8884; margin-bottom: 1.5rem; }
.site-header .brand { font-size: 1.4rem; font-weight: 700; text-decoration: none; }
.site-header .tagline { margin: .25rem 0 .75rem; opacity: .75; }
.site-header nav a { margin-right: 1rem; text-decoration: none; font-weight: 600; }
.deal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1rem; }
.deal { border: 1px solid #8884; border-radius: 8px; padding: 1rem; }
.deal img { max-width: 100%; height: 160px; object-fit: contain; display: block; margin: 0 auto .5rem; }
.deal h2 { font-size: 1rem; margin: 0 0 .5rem; }
.deal .price .now { font-weight: 700; font-size: 1.1rem; }
.deal .price .was { text-decoration: line-through; opacity: .6; margin-left: .4rem; }
.deal .price .off { color: #1a7a1a; margin-left: .4rem; font-weight: 600; }
.deal .facts { list-style: none; padding: 0; margin: .4rem 0; font-size: .85rem; opacity: .85; }
.deal .detail { font-size: .85rem; opacity: .8; margin: .4rem 0; }
.deal .buy { display: inline-block; margin-top: .5rem; font-weight: 600; text-decoration: none; }
.guide-list li { margin-bottom: .6rem; }
.site-footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #8884; opacity: .8; font-size: .9rem; }
"""


def render_site(deals: list[dict[str, Any]], max_listed: int = 60) -> None:
    """Rebuilds the entire site/ directory. Safe to call every run."""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    (SITE_DIR / "style.css").write_text(STYLE_CSS.strip() + "\n")

    deals = deals[:max_listed]
    cards = "\n".join(DEAL_CARD_TEMPLATE.render(deal=d) for d in deals)
    index_content = INDEX_CONTENT_TEMPLATE.render(tagline=TAGLINE, deals_html=cards)
    _write_page("index.html", "Board Game Deals", "Automatically tracked board game price drops on Amazon, updated every few hours.", index_content, updated)

    for content_filename, out_filename, _nav_title, description in EVERGREEN_PAGES:
        source = CONTENT_DIR / content_filename
        if not source.exists():
            continue  # don't fail the whole run over one missing evergreen page
        page_html = source.read_text()
        title = _title_from_html(page_html) or out_filename
        _write_page(out_filename, title, description, page_html, updated)

    guides = [
        (out_filename, _title_from_html((CONTENT_DIR / content_filename).read_text()) or out_filename, description)
        for content_filename, out_filename, _nav_title, description in EVERGREEN_PAGES
        if content_filename.startswith("guide-") and (CONTENT_DIR / content_filename).exists()
    ]
    guides_content = GUIDES_INDEX_TEMPLATE.render(guides=guides)
    _write_page("guides.html", "Guides", "Practical board-game buying guides.", guides_content, updated)


def _write_page(filename: str, title: str, description: str, content_html: str, updated: str) -> None:
    html = BASE_TEMPLATE.render(
        title=title,
        description=description,
        site_name=SITE_NAME,
        tagline=TAGLINE,
        disclosure=DISCLOSURE,
        content=content_html,
        updated=updated,
    )
    (SITE_DIR / filename).write_text(html)


def _title_from_html(html: str) -> str | None:
    start = html.find("<h1")
    if start == -1:
        return None
    start = html.find(">", start) + 1
    end = html.find("</h1>", start)
    if end == -1:
        return None
    return html[start:end].strip()
