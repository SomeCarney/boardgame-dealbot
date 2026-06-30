"""Regenerates the static GitHub Pages site.

content/*.html files are hand-written evergreen pages, copied through as-is
inside the shared layout. index.html is rebuilt from the current deal list
on every run. This keeps the site looking active (Amazon expects "recent"
content) without ever touching the hand-written pages.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
RANKINGS_CACHE = ROOT / "config" / "rankings_cache.json"
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
      <a href="best-board-games.html">Hot Board Games</a>
      <a href="guides.html">Guides</a>
      <a href="about.html">About</a>
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
<div class="deals-header">
  <h1>Current Board Game Deals</h1>
  <span class="deals-freshness">Re-checked every 4 hours</span>
</div>
<p>Genuine price drops on board games &mdash; tracked automatically against 90-day price history so nothing here is a fake &#8220;sale.&#8221;</p>
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
  <li><a href="{{ href }}">{{ title }}</a><span class="guide-desc">{{ description }}</span></li>
{% endfor %}
</ul>
""")

STYLE_CSS = """
:root {
  color-scheme: dark;
  --bg: #0e0d0b;
  --bg2: #161410;
  --panel: #1e1b17;
  --panel-hover: #252119;
  --panel-border: #38312a;
  --text: #ede7d5;
  --text-muted: #9e9282;
  --text-faint: #6b6256;
  --gold: #e8b923;
  --gold-bright: #f5d060;
  --gold-dim: #c49b18;
  --red: #b3242a;
  --red-bright: #d43030;
  --display-font: 'Bebas Neue', Oswald, Impact, sans-serif;
  --heading-font: Oswald, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  --body-font: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  --radius: 10px;
  --shadow: 0 2px 12px rgba(0,0,0,.45);
  --shadow-lg: 0 4px 24px rgba(0,0,0,.6);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--body-font);
  background: var(--bg);
  color: var(--text);
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 1.25rem 4rem;
  line-height: 1.6;
}

a { color: var(--gold); text-decoration: none; }
a:hover, a:focus { color: var(--gold-bright); text-decoration: underline; }

h1, h2, h3, h4 { font-family: var(--heading-font); letter-spacing: .01em; line-height: 1.2; }
h1 { font-size: 2rem; margin: 1.5rem 0 .6rem; }
h2 { font-size: 1.4rem; margin: 1.5rem 0 .5rem; }
h3 { font-size: 1.1rem; margin: 1.2rem 0 .4rem; }
p { margin: .75rem 0; }
ul, ol { padding-left: 1.4rem; margin: .75rem 0; }
li { margin-bottom: .35rem; }

/* ── HEADER ─────────────────────────────── */
.site-header {
  background: var(--panel);
  border-bottom: 3px solid var(--gold);
  margin: 0 -1.25rem 2.5rem;
  padding: 0 1.25rem;
  box-shadow: var(--shadow);
}
.header-inner { max-width: 1100px; margin: 0 auto; padding: 1.5rem 0 1rem; }
.site-header .brand {
  font-family: var(--display-font);
  font-size: 2.5rem;
  letter-spacing: .04em;
  color: var(--gold);
  display: flex;
  align-items: center;
  gap: .5rem;
  line-height: 1;
}
.brand-die {
  height: 2.2rem;
  width: 2.2rem;
  flex-shrink: 0;
  filter: drop-shadow(0 2px 8px rgba(232,185,35,.4));
}
.site-header .brand:hover { color: var(--gold-bright); text-decoration: none; }
.site-header .tagline {
  margin: .3rem 0 1rem;
  color: var(--text-muted);
  font-size: .9rem;
  letter-spacing: .015em;
}
.site-header nav {
  display: flex;
  flex-wrap: wrap;
  gap: .25rem .1rem;
}
.site-header nav a {
  font-family: var(--heading-font);
  font-weight: 500;
  font-size: .875rem;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--text-muted);
  padding: .3rem .7rem;
  border-radius: 4px;
  transition: color .15s, background .15s;
}
.site-header nav a:hover {
  color: var(--gold);
  background: rgba(232,185,35,.08);
  text-decoration: none;
}

/* ── DEAL GRID ──────────────────────────── */
.deals-header { display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
.deals-header h1 { margin: 0; }
.deals-freshness { font-size: .82rem; color: var(--text-faint); }

.deal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(265px, 1fr));
  gap: 1.25rem;
}

.deal {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow);
}
.deal:hover {
  border-color: var(--gold-dim);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
.deal img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  display: block;
  background: var(--bg2);
}
.deal-body { padding: 1rem 1.1rem 1.1rem; display: flex; flex-direction: column; flex: 1; }

.deal-title { font-size: 1.5rem; font-family: var(--heading-font); line-height: 1.2; margin: 0 0 .5rem; }
.deal-title a { color: #fff; }
.deal-title a:hover { color: var(--gold); text-decoration: none; }

.deal .price {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: .4rem .6rem;
  margin: 0 0 .5rem;
  font-family: var(--display-font);
}
.deal .price .now { font-size: 2.1rem; color: var(--gold); letter-spacing: .02em; line-height: 1; }
.deal .price .was {
  font-family: var(--body-font);
  font-size: .9rem;
  color: var(--text-faint);
  text-decoration: line-through;
}
.deal .price .off {
  font-family: var(--body-font);
  background: var(--red);
  color: #fff;
  font-size: .68rem;
  font-weight: 700;
  letter-spacing: .04em;
  padding: .2rem .55rem;
  border-radius: 4px;
  align-self: center;
}

.deal .rating, .game-rating {
  display: flex;
  align-items: center;
  gap: .45rem;
  margin: 0 0 .55rem;
  font-size: .8rem;
  color: var(--text-muted);
}
.stars { position: relative; display: inline-block; font-size: .95rem; line-height: 1; letter-spacing: 1.5px; }
.stars-track { color: #2e2820; }
.stars-fill { position: absolute; top: 0; left: 0; overflow: hidden; white-space: nowrap; color: var(--gold); }
.review-count { font-size: .78rem; }

.deal .facts {
  list-style: none;
  padding: 0;
  margin: 0 0 .6rem;
  display: flex;
  flex-wrap: wrap;
  gap: .3rem;
}
.deal .facts li {
  background: rgba(255,255,255,.04);
  border: 1px solid var(--panel-border);
  color: var(--text-muted);
  border-radius: 999px;
  padding: .2rem .6rem;
  font-size: .73rem;
  max-width: 100%;
  overflow-wrap: break-word;
}
.deal .facts li.best-seller {
  background: var(--gold);
  border-color: var(--gold);
  color: var(--bg);
  font-weight: 700;
}

.deal-subtitle {
  font-size: .72rem;
  color: var(--text-faint);
  line-height: 1.4;
  margin: 0 0 .8rem;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.buy {
  display: inline-block;
  font-family: var(--heading-font);
  font-weight: 600;
  text-transform: uppercase;
  font-size: .82rem;
  letter-spacing: .04em;
  color: var(--bg);
  background: var(--gold);
  padding: .55rem 1.1rem;
  border-radius: 6px;
  transition: background .15s, transform .1s;
  align-self: flex-start;
}
.buy:hover { background: var(--gold-bright); text-decoration: none; transform: translateY(-1px); }

/* ── GAME GRID (evergreen guides) ─────── */
.game-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
  margin-top: 1.75rem;
}

.game-card {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow);
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
.game-card:hover {
  border-color: var(--gold-dim);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
.game-img-link { display: block; flex-shrink: 0; }
.game-img-link img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: contain;
  display: block;
  background: var(--bg2);
  padding: .5rem;
}
.game-card-body {
  padding: 1rem 1.1rem 1.1rem;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.game-card-title {
  font-family: var(--heading-font);
  font-size: 1.3rem;
  line-height: 1.2;
  margin: 0 0 .4rem;
}
.game-card-title a { color: #fff; }
.game-card-title a:hover { color: var(--gold); text-decoration: none; }

.game-pills {
  list-style: none;
  padding: 0;
  margin: .4rem 0 .65rem;
  display: flex;
  flex-wrap: wrap;
  gap: .3rem;
}
.game-pills li {
  background: rgba(255,255,255,.04);
  border: 1px solid var(--panel-border);
  color: var(--text-muted);
  border-radius: 999px;
  padding: .2rem .6rem;
  font-size: .72rem;
}

.game-blurb {
  font-size: .88rem;
  color: var(--text-muted);
  line-height: 1.5;
  margin: 0 0 .9rem;
  flex: 1;
}

/* ── GUIDES INDEX ────────────────────── */
.guide-list { list-style: none; padding: 0; margin-top: .75rem; }
.guide-list li {
  display: flex;
  flex-direction: column;
  gap: .2rem;
  padding: .85rem 0;
  border-bottom: 1px solid var(--panel-border);
}
.guide-list li:last-child { border-bottom: none; }
.guide-list a { font-family: var(--heading-font); font-size: 1.05rem; letter-spacing: .01em; }
.guide-list .guide-desc { font-size: .85rem; color: var(--text-muted); }

.guide-section-title {
  font-family: var(--display-font);
  font-size: 1.1rem;
  letter-spacing: .05em;
  color: var(--gold);
  text-transform: uppercase;
  margin: 2rem 0 .5rem;
  padding-bottom: .4rem;
  border-bottom: 1px solid var(--panel-border);
}

/* ── RANKED LIST (Best Board Games pages) ── */
.ranked-list { list-style: none; padding: 0; margin-top: 1.5rem; }

.ranked-item {
  display: flex;
  gap: 1.1rem;
  align-items: center;
  padding: 1.25rem 0;
  border-bottom: 1px solid var(--panel-border);
}
.ranked-item:last-child { border-bottom: none; }

.ranked-num {
  font-family: var(--display-font);
  font-size: 3.4rem;
  line-height: 1;
  color: var(--gold);
  min-width: 3.6rem;
  text-align: right;
  flex-shrink: 0;
}

.ranked-img-wrap {
  flex-shrink: 0;
  width: 90px;
  height: 90px;
  background: var(--panel);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--panel-border);
}
.ranked-img-wrap img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 4px;
}
.ranked-img-wrap.no-image {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-faint);
  font-size: 2rem;
}

.ranked-body { flex: 1; min-width: 0; }
.ranked-title {
  font-family: var(--heading-font);
  font-size: 1.2rem;
  line-height: 1.25;
  margin: 0 0 .3rem;
}
.ranked-title a { color: #fff; }
.ranked-title a:hover { color: var(--gold); text-decoration: none; }

.ranked-meta {
  display: flex;
  flex-wrap: wrap;
  gap: .25rem .5rem;
  margin: 0 0 .5rem;
  font-size: .75rem;
  color: var(--text-muted);
}
.ranked-meta span { display: flex; align-items: center; gap: .25rem; }

.ranked-blurb {
  font-size: .85rem;
  color: var(--text-muted);
  line-height: 1.5;
  margin: 0 0 .6rem;
}

.ranked-buy {
  font-family: var(--heading-font);
  font-size: .75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .04em;
  color: var(--bg);
  background: var(--gold);
  padding: .3rem .75rem;
  border-radius: 5px;
  display: inline-block;
}
.ranked-buy:hover { background: var(--gold-bright); text-decoration: none; }

/* Best Board Games hub */
.bbg-hub { margin-top: 1.5rem; }
.bbg-section { margin-bottom: 2rem; }
.bbg-section-title {
  font-family: var(--display-font);
  font-size: 1rem;
  letter-spacing: .06em;
  color: var(--gold);
  text-transform: uppercase;
  border-bottom: 1px solid var(--panel-border);
  padding-bottom: .4rem;
  margin-bottom: .75rem;
}
.bbg-list { list-style: none; padding: 0; }
.bbg-list li { padding: .5rem 0; border-bottom: 1px solid rgba(255,255,255,.04); }
.bbg-list li:last-child { border-bottom: none; }
.bbg-list a { font-family: var(--heading-font); font-size: 1rem; letter-spacing: .01em; }
.bbg-list .bbg-desc { font-size: .82rem; color: var(--text-muted); display: block; margin-top: .1rem; }

@media (max-width: 600px) {
  .ranked-num { font-size: 2.6rem; min-width: 2.9rem; }
  .ranked-img-wrap { width: 70px; height: 70px; }
  .ranked-title { font-size: 1rem; }
}

/* ── FOOTER ─────────────────────────── */
.site-footer {
  margin-top: 4rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--panel-border);
  color: var(--text-faint);
  font-size: .82rem;
  display: flex;
  flex-wrap: wrap;
  gap: .5rem 2rem;
}

/* ── RESPONSIVE ─────────────────────── */
@media (max-width: 600px) {
  body { padding: 0 .85rem 3rem; }
  .site-header { margin: 0 -.85rem 1.75rem; padding: 0 .85rem; }
  .site-header .brand { font-size: 1.9rem; }
  h1 { font-size: 1.6rem; }
  .deal-grid, .game-grid { grid-template-columns: 1fr 1fr; gap: .85rem; }
  .deal-title { font-size: 1.2rem; }
  .deal .price .now { font-size: 1.7rem; }
}
@media (max-width: 400px) {
  .deal-grid, .game-grid { grid-template-columns: 1fr; }
}
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

    _render_rankings_section(updated)


def _render_rankings_section(updated: str) -> None:
    """Generate all Best Board Games pages from the rankings cache."""
    if not RANKINGS_CACHE.exists():
        return
    cache = json.loads(RANKINGS_CACHE.read_text(encoding="utf-8"))
    lists = cache.get("lists", {})

    # Hub page
    hub_sections = [
        ("All Time", ["all-time"]),
        ("Player Count", ["solo", "2p", "3p", "4p-plus"]),
        ("By Genre", ["strategy", "coop", "social-deduction", "party", "family", "gateway"]),
    ]
    hub_items_html = ""
    for section_label, keys in hub_sections:
        items_html = ""
        for key in keys:
            lst = lists.get(key)
            if not lst:
                continue
            slug = lst["slug"]
            title = lst["title"]
            desc = lst["description"].replace("\n", " ").strip()[:120]
            items_html += f'<li><a href="{slug}.html">{title}</a><span class="bbg-desc">{desc}</span></li>\n'
        if items_html:
            hub_items_html += f'<div class="bbg-section"><p class="bbg-section-title">{section_label}</p><ul class="bbg-list">{items_html}</ul></div>\n'

    criteria_html = "<p>Every list on this page is ranked by a weighted score combining Amazon star ratings, review count, and current sales rank.</p>"

    hub_content = f"<h1>Hot Board Games</h1>\n{criteria_html}\n<div class=\"bbg-hub\">{hub_items_html}</div>"
    _write_page("best-board-games.html", "Hot Board Games", "Ranked lists of the best board games by player count, genre, and all time.", hub_content, updated)

    # Individual ranked list pages
    for key, lst in lists.items():
        slug = lst["slug"]
        title = lst["title"]
        description = lst["description"].replace("\n", " ").strip()
        games = lst["games"]

        # Render countdown: #N (least impressive) at top, #1 (best) at bottom.
        # games is sorted BEST-FIRST; reverse it so #1 is revealed last.
        total = len(games)
        items_html = ""
        for i, game in enumerate(reversed(games)):
            rank_num = total - i
            img_id = game.get("image_id")
            if img_id:
                img_html = f'<img src="https://m.media-amazon.com/images/I/{img_id}" alt="{game["title"]}" loading="lazy">'
                img_wrap = f'<div class="ranked-img-wrap">{img_html}</div>'
            else:
                img_wrap = '<div class="ranked-img-wrap no-image">🎲</div>'

            rating = game.get("rating")
            reviews = game.get("reviews")
            stars_html = ""
            if rating:
                pct = round(rating / 5 * 100, 1)
                rev_txt = f" &middot; {reviews:,} reviews" if reviews else ""
                stars_html = f"""<span class="stars" aria-label="{rating}/5">
  <span class="stars-track">&#9733;&#9733;&#9733;&#9733;&#9733;</span>
  <span class="stars-fill" style="width:{pct}%">&#9733;&#9733;&#9733;&#9733;&#9733;</span>
</span><span class="review-count">{rating}/5{rev_txt}</span>"""

            meta_parts = []
            if game.get("players"):
                meta_parts.append(f'<span>&#128101; {game["players"]}</span>')
            if game.get("time"):
                meta_parts.append(f'<span>&#9201; {game["time"]}</span>')
            if game.get("age"):
                meta_parts.append(f'<span>Ages {game["age"]}</span>')
            if rating:
                meta_parts.append(f'<span>{stars_html}</span>')
            meta_html = "\n".join(meta_parts)

            blurb = game.get("blurb", "").strip()
            blurb_html = f'<p class="ranked-blurb">{blurb}</p>' if blurb else ""
            link = game.get("link", f'https://www.amazon.com/dp/{game["asin"]}?tag=carnivalgam06-20')

            items_html += f"""<li class="ranked-item">
  <span class="ranked-num">#{rank_num}</span>
  <a href="{link}" rel="nofollow sponsored noopener" target="_blank">{img_wrap}</a>
  <div class="ranked-body">
    <h2 class="ranked-title"><a href="{link}" rel="nofollow sponsored noopener" target="_blank">{game["title"]}</a></h2>
    <div class="ranked-meta">{meta_html}</div>
    {blurb_html}
    <a class="ranked-buy" href="{link}" rel="nofollow sponsored noopener" target="_blank">View on Amazon &rarr;</a>
  </div>
</li>"""

        refresh_note = f'<p style="font-size:.8rem;color:var(--text-faint);margin-top:1rem;">Rankings last updated: {cache.get("updated_at","")[:10]}. Refreshed monthly.</p>'
        page_content = f"<h1>{title}</h1>\n<p>{description}</p>\n{refresh_note}\n<ol class=\"ranked-list\">{items_html}</ol>"
        _write_page(f"{slug}.html", title, description, page_content, updated)


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
