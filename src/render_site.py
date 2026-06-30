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

SITE_NAME = "Board Game Black Market"
TAGLINE = "Underground deals on board games -- no markup, no nonsense."
DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases."

# filename in content/ -> (output filename, nav title, <meta description>)
EVERGREEN_PAGES: list[tuple[str, str, str, str]] = [
    ("about.html", "about.html", "About", "What Board Game Black Market is and why it exists."),
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Oswald:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="index.html">
      <svg class="brand-die" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" aria-hidden="true">
        <rect x="4" y="4" width="92" height="92" rx="14" fill="#e8b923"/>
        <rect x="4" y="4" width="92" height="44" rx="14" fill="#f0ca4a" opacity="0.3"/>
        <circle cx="30" cy="28" r="9" fill="#1c1a17"/>
        <circle cx="70" cy="28" r="9" fill="#1c1a17"/>
        <circle cx="30" cy="50" r="9" fill="#1c1a17"/>
        <circle cx="70" cy="50" r="9" fill="#1c1a17"/>
        <circle cx="30" cy="72" r="9" fill="#1c1a17"/>
        <circle cx="70" cy="72" r="9" fill="#1c1a17"/>
      </svg>{{ site_name }}</a>
    <p class="tagline">{{ tagline }}</p>
    <nav>
      <a href="index.html">Deals</a>
      <a href="about.html">About</a>
      <a href="how-we-pick-deals.html">How We Pick Deals</a>
      <a href="guides.html">Guides</a>
    </nav>
  </div>
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
  {# deal.image_url (the price-banner version) is for social posts, which have
     no surrounding page layout -- the site has its own price/rating block,
     so the plain branded thumbnail (no banner) fits better here #}
  {% set img = deal.site_image_url or deal.image %}
  {% if img %}<img src="{{ img }}" alt="" loading="lazy">{% endif %}
  <div class="deal-body">
    <h2 class="deal-title"><a href="{{ deal.link }}" rel="nofollow sponsored noopener" target="_blank">{{ deal.short_title or deal.title }}</a></h2>
    <p class="price">
      <span class="now">${{ "%.2f"|format(deal.price) }}</span>
      <span class="was">${{ "%.2f"|format(deal.typical_price) }}</span>
      <span class="off">{{ deal.percent_off }}% OFF</span>
    </p>
    {% if deal.rating %}
    <p class="rating">
      <span class="stars" aria-label="{{ deal.rating }} out of 5 stars">
        <span class="stars-track">&#9733;&#9733;&#9733;&#9733;&#9733;</span>
        <span class="stars-fill" style="width: {{ (deal.rating / 5 * 100) | round(1) }}%">&#9733;&#9733;&#9733;&#9733;&#9733;</span>
      </span>
      <span class="review-count">{{ deal.rating }}/5 &middot; {{ deal.review_count }} reviews</span>
    </p>
    {% endif %}
    {% if deal.summary_lines %}
    <ul class="facts">
      {% for line in deal.summary_lines %}<li{% if "Best Seller" in line %} class="best-seller"{% endif %}>{{ line }}</li>{% endfor %}
    </ul>
    {% endif %}
    <p class="deal-subtitle">{{ deal.title }}</p>
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
:root {
  color-scheme: dark;
  --bg: #121212;
  --panel: #1c1a17;
  --panel-border: #3a332b;
  --text: #ece6d6;
  --text-muted: #a89f8c;
  --gold: #e8b923;
  --gold-bright: #f7d774;
  --red: #b3242a;
  --display-font: 'Bebas Neue', Oswald, Impact, sans-serif;
  --heading-font: Oswald, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  --body-font: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
}

* { box-sizing: border-box; }

body {
  font-family: var(--body-font);
  background: var(--bg);
  color: var(--text);
  max-width: 1000px;
  margin: 0 auto;
  padding: 0 1rem 3rem;
  line-height: 1.55;
}

a { color: var(--gold); text-decoration: none; }
a:hover, a:focus { color: var(--gold-bright); text-decoration: underline; }

h1, h2, h3 { font-family: var(--heading-font); letter-spacing: .01em; }

.site-header {
  background: var(--panel);
  border-bottom: 3px solid var(--gold);
  margin: 0 -1rem 2rem;
  padding: 0 1rem;
}
.header-inner { max-width: 1000px; margin: 0 auto; padding: 1.75rem 0 1.1rem; }
.site-header .brand {
  font-family: var(--display-font);
  font-size: 2.6rem;
  letter-spacing: .04em;
  color: var(--gold);
  display: flex;
  align-items: center;
  gap: .5rem;
}
.brand-die {
  height: 2.4rem;
  width: 2.4rem;
  flex-shrink: 0;
  filter: drop-shadow(0 2px 6px rgba(232,185,35,.35));
}
.site-header .brand:hover { color: var(--gold-bright); text-decoration: none; }
.site-header .tagline { margin: .15rem 0 1rem; color: var(--text-muted); font-style: italic; }
.site-header nav a {
  margin-right: 1.25rem;
  font-family: var(--heading-font);
  font-weight: 500;
  font-size: .95rem;
  text-transform: uppercase;
  letter-spacing: .03em;
  color: var(--text);
}
.site-header nav a:hover { color: var(--gold); text-decoration: none; }

h1 { font-size: 1.8rem; }

.deal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.25rem; }

.deal {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: 10px;
  padding: 0;
  overflow: hidden;
  transition: border-color .15s ease;
}
.deal:hover { border-color: var(--gold); }
.deal img { width: 100%; aspect-ratio: 1 / 1; object-fit: cover; display: block; background: var(--panel); }
.deal-body { padding: 1rem; }

.deal-title { font-size: 1.3rem; font-family: var(--heading-font); line-height: 1.2; margin: 0 0 .6rem; }
.deal-title a { color: var(--text); }
.deal-title a:hover { color: var(--gold); text-decoration: none; }

.deal .price { display: flex; align-items: baseline; flex-wrap: wrap; gap: .5rem; margin: 0 0 .5rem; font-family: var(--display-font); }
.deal .price .now { font-size: 2rem; color: var(--gold); letter-spacing: .02em; line-height: 1; }
.deal .price .was { font-family: var(--body-font); font-size: .95rem; color: var(--text-muted); text-decoration: line-through; }
.deal .price .off { font-family: var(--body-font); background: var(--red); color: #fff; font-size: .7rem; font-weight: 700; letter-spacing: .03em; padding: .2rem .5rem; border-radius: 4px; }

.deal .rating { display: flex; align-items: center; gap: .5rem; margin: 0 0 .6rem; font-size: .82rem; color: var(--text-muted); }
.stars { position: relative; display: inline-block; font-size: 1rem; line-height: 1; letter-spacing: 1px; }
.stars-track { color: #3a332b; }
.stars-fill { position: absolute; top: 0; left: 0; overflow: hidden; white-space: nowrap; color: var(--gold); }

.deal .facts { list-style: none; padding: 0; margin: 0 0 .6rem; display: flex; flex-wrap: wrap; gap: .35rem; }
.deal .facts li {
  background: #2a241c;
  border: 1px solid var(--panel-border);
  color: var(--text-muted);
  border-radius: 999px;
  padding: .25rem .65rem;
  font-size: .76rem;
  max-width: 100%;
  overflow-wrap: break-word;
}
.deal .facts li.best-seller {
  background: var(--gold);
  border-color: var(--gold);
  color: var(--bg);
  font-weight: 700;
}

.deal-subtitle { font-size: .73rem; color: var(--text-muted); line-height: 1.4; margin: 0 0 .75rem;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.deal .buy {
  display: inline-block;
  font-family: var(--heading-font);
  font-weight: 600;
  text-transform: uppercase;
  font-size: .85rem;
  letter-spacing: .03em;
  color: var(--bg);
  background: var(--gold);
  padding: .5rem 1rem;
  border-radius: 5px;
}
.deal .buy:hover { background: var(--gold-bright); text-decoration: none; }

.guide-list { list-style: none; padding: 0; }
.guide-list li { margin-bottom: .75rem; padding-bottom: .75rem; border-bottom: 1px solid var(--panel-border); }

.site-footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--panel-border); color: var(--text-muted); font-size: .85rem; }
"""


def render_site(deals: list[dict[str, Any]], max_listed: int = 60) -> None:
    """Rebuilds the entire site/ directory. Safe to call every run."""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    (SITE_DIR / "style.css").write_text(STYLE_CSS.strip() + "\n", encoding="utf-8")

    deals = deals[:max_listed]
    cards = "\n".join(DEAL_CARD_TEMPLATE.render(deal=d) for d in deals)
    index_content = INDEX_CONTENT_TEMPLATE.render(tagline=TAGLINE, deals_html=cards)
    _write_page("index.html", "Board Game Deals", "Automatically tracked board game price drops on Amazon, updated every few hours.", index_content, updated)

    for content_filename, out_filename, _nav_title, description in EVERGREEN_PAGES:
        source = CONTENT_DIR / content_filename
        if not source.exists():
            continue  # don't fail the whole run over one missing evergreen page
        page_html = source.read_text(encoding="utf-8")
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
    (SITE_DIR / filename).write_text(html, encoding="utf-8")


def _title_from_html(html: str) -> str | None:
    start = html.find("<h1")
    if start == -1:
        return None
    start = html.find(">", start) + 1
    end = html.find("</h1>", start)
    if end == -1:
        return None
    return html[start:end].strip()
