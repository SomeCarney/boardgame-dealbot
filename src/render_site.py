"""Regenerates the static GitHub Pages site.

content/*.html files are hand-written evergreen pages, copied through as-is
inside the shared layout. index.html is rebuilt from the current deal list
on every run. This keeps the site looking active (Amazon expects "recent"
content) without ever touching the hand-written pages.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import html as html_lib

from jinja2 import Environment

from safewrite import atomic_write_text

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
RANKINGS_CACHE = ROOT / "config" / "rankings_cache.json"
# GitHub Pages "deploy from a branch" only accepts / or /docs as the served
# path -- docs/ it is, even though "site" would have been a clearer name.
# DRY_RUN renders into docs_preview/ (gitignored) instead: a test run must never
# overwrite -- or leak fixture deals into -- the real, committed site, because
# the scheduler blindly `git add docs/` and would push whatever it finds there.
SITE_DIR = ROOT / ("docs_preview" if os.environ.get("DRY_RUN") == "1" else "docs")

SITE_NAME = "Board Game Black Market"
TAGLINE = "Underground deals on board games -- no markup, no nonsense."
DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases."
BASE_URL = "https://boardgameblackmarket.com"
FACEBOOK_URL = "https://www.facebook.com/profile.php?id=1225021374020132"
INSTAGRAM_URL = "https://www.instagram.com/boardgameblackmarket/"
PINTEREST_URL = "https://www.pinterest.com/BoardGameBlackMarket/"
TWITTER_URL = "https://x.com/BG_BlackMarket"
# Google Search Console ownership proof -- rendered into every page head.
# Not a secret (it is published in the HTML by design). Empty = tag omitted.
GOOGLE_SITE_VERIFICATION = "yL_iQ9hYbc0kDN2G9tMBb-88d995a5_5cz60ED4a-4w"

# Amazon OneLink "OneTag" geo-routing snippet, injected verbatim before </body>
# on every page. OneLink sends international visitors to their local Amazon
# store and swaps in the matching regional affiliate tag, so non-US clicks can
# actually earn (they earn $0 today). Get this from Associates Central ->
# Tools -> OneLink after linking your regional accounts, and paste it here.
# Not a secret (it's public JS). Empty = nothing injected (current behavior).
ONELINK_ONETAG = ""

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

# autoescape=True (not select_autoescape): from_string templates have no
# filename, so select_autoescape silently left escaping OFF and untrusted
# Amazon titles flowed raw into the HTML. Raw-HTML injection points all use
# the |safe filter explicitly.
env = Environment(autoescape=True)

BASE_TEMPLATE = env.from_string("""<!doctype html>
<html lang="en" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | {{ site_name }}</title>
<meta name="description" content="{{ description }}">
<meta name="theme-color" content="#0e0d0b">
{% if google_verification %}<meta name="google-site-verification" content="{{ google_verification }}">
{% endif %}<link rel="canonical" href="{{ canonical }}">
<meta property="og:site_name" content="{{ site_name }}">
<meta property="og:type" content="website">
<meta property="og:title" content="{{ title }}">
<meta property="og:description" content="{{ description }}">
<meta property="og:url" content="{{ canonical }}">
<meta property="og:image" content="{{ base_url }}/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{{ title }}">
<meta name="twitter:description" content="{{ description }}">
<meta name="twitter:image" content="{{ base_url }}/og-image.png">
<script>document.documentElement.className = 'js';</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Oswald:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="alternate" type="application/rss+xml" title="{{ site_name }} deal feed" href="{{ base_url }}/deals.xml">
{% if jsonld %}<script type="application/ld+json">{{ jsonld|safe }}</script>{% endif %}
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="index.html" aria-label="{{ site_name }} — home">
      <svg class="brand-die" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" aria-hidden="true">
        <rect x="4" y="4" width="92" height="92" rx="14" fill="#e8b923"/>
        <rect x="4" y="4" width="92" height="44" rx="14" fill="#f0ca4a" opacity="0.3"/>
        <circle cx="30" cy="28" r="9" fill="#1c1a17"/>
        <circle cx="70" cy="28" r="9" fill="#1c1a17"/>
        <circle cx="30" cy="50" r="9" fill="#1c1a17"/>
        <circle cx="70" cy="50" r="9" fill="#1c1a17"/>
        <circle cx="30" cy="72" r="9" fill="#1c1a17"/>
        <circle cx="70" cy="72" r="9" fill="#1c1a17"/>
      </svg>
      <span class="brand-text">
        <span class="brand-top">Board Game</span>
        <span class="brand-main">Black Market</span>
      </span>
    </a>
    <button class="nav-toggle" aria-expanded="false" aria-controls="site-nav" aria-label="Menu">
      <span></span><span></span><span></span>
    </button>
    <nav id="site-nav" class="site-nav">
      <a href="index.html"{% if active == 'deals' %} class="active" aria-current="page"{% endif %}>Deals</a>
      <a href="best-board-games.html"{% if active == 'hot' %} class="active" aria-current="page"{% endif %}>Hot Board Games</a>
      <a href="guides.html"{% if active == 'guides' %} class="active" aria-current="page"{% endif %}>Guides</a>
      <a href="gift-guide.html"{% if active == 'gifts' %} class="active" aria-current="page"{% endif %}>Gift Guide</a>
      <a href="about.html"{% if active == 'about' %} class="active" aria-current="page"{% endif %}>About</a>
      <span class="nav-social">
        <a href="{{ facebook_url }}" target="_blank" rel="noopener" aria-label="Facebook">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.6c-.3-.04-1.3-.12-2.45-.12-2.4 0-4.05 1.46-4.05 4.15v2.27H7.5V13h2.7v8h3.3z"/></svg>
        </a>
        <a href="{{ instagram_url }}" target="_blank" rel="noopener" aria-label="Instagram">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 4.3c2.5 0 2.8 0 3.8.06 2.55.11 3.74 1.32 3.85 3.85.05 1 .06 1.28.06 3.79 0 2.5-.01 2.8-.06 3.78-.11 2.53-1.3 3.74-3.85 3.86-1 .04-1.3.05-3.8.05s-2.8 0-3.79-.05c-2.55-.12-3.74-1.34-3.85-3.86-.05-1-.06-1.28-.06-3.79s.01-2.79.06-3.78C4.47 5.68 5.66 4.47 8.21 4.36c1-.05 1.29-.06 3.79-.06zM12 2.4c-2.55 0-2.87.01-3.87.06C4.72 2.62 2.83 4.5 2.67 7.92c-.05 1-.06 1.32-.06 3.87s.01 2.88.06 3.88c.16 3.41 2.04 5.3 5.46 5.46 1 .04 1.32.06 3.87.06s2.87-.02 3.87-.06c3.41-.16 5.31-2.04 5.46-5.46.05-1 .06-1.33.06-3.88s-.01-2.87-.06-3.87c-.15-3.41-2.04-5.3-5.45-5.46-1-.05-1.33-.06-3.88-.06zm0 4.57a5.03 5.03 0 1 0 0 10.06 5.03 5.03 0 0 0 0-10.06zm0 8.3a3.27 3.27 0 1 1 0-6.53 3.27 3.27 0 0 1 0 6.54zm5.23-9.68a1.18 1.18 0 1 0 0 2.35 1.18 1.18 0 0 0 0-2.35z"/></svg>
        </a>
        <a href="{{ pinterest_url }}" target="_blank" rel="noopener" aria-label="Pinterest">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12c0 4.24 2.64 7.86 6.36 9.3-.09-.79-.17-2 .03-2.86.18-.78 1.17-4.97 1.17-4.97s-.3-.6-.3-1.48c0-1.39.8-2.42 1.8-2.42.85 0 1.26.64 1.26 1.4 0 .86-.54 2.14-.83 3.33-.24 1 .5 1.81 1.48 1.81 1.78 0 3.14-1.87 3.14-4.57 0-2.39-1.72-4.06-4.17-4.06-2.84 0-4.51 2.13-4.51 4.33 0 .86.33 1.78.74 2.28.08.1.09.19.07.29-.08.32-.25 1-.28 1.14-.04.18-.15.22-.34.13-1.25-.58-2.03-2.4-2.03-3.87 0-3.15 2.29-6.04 6.6-6.04 3.47 0 6.16 2.47 6.16 5.77 0 3.45-2.17 6.22-5.19 6.22-1.01 0-1.97-.53-2.3-1.15l-.62 2.39c-.23.86-.83 1.94-1.24 2.6.94.29 1.92.44 2.95.44 5.52 0 10-4.48 10-10S17.52 2 12 2z"/></svg>
        </a>
        <a href="{{ twitter_url }}" target="_blank" rel="noopener" aria-label="X">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.9 1.15h3.68l-8.04 9.19L24 22.85h-7.41l-5.8-7.58-6.64 7.58H.46l8.6-9.83L0 1.15h7.6l5.24 6.93 6.06-6.93zm-1.29 19.5h2.04L6.49 3.24H4.3L17.61 20.65z"/></svg>
        </a>
      </span>
    </nav>
  </div>
</header>
<main id="main" class="wrap">
{{ content|safe }}
</main>
<footer class="site-footer">
  <div class="wrap">
    <div class="footer-grid">
      <div class="footer-brand">
        <p class="footer-logo">Board Game <span>Black Market</span></p>
        <p class="footer-tag">{{ tagline }}</p>
        <p class="footer-social">
          <a href="{{ facebook_url }}" target="_blank" rel="noopener" aria-label="Facebook"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.6c-.3-.04-1.3-.12-2.45-.12-2.4 0-4.05 1.46-4.05 4.15v2.27H7.5V13h2.7v8h3.3z"/></svg></a>
          <a href="{{ instagram_url }}" target="_blank" rel="noopener" aria-label="Instagram"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 4.3c2.5 0 2.8 0 3.8.06 2.55.11 3.74 1.32 3.85 3.85.05 1 .06 1.28.06 3.79 0 2.5-.01 2.8-.06 3.78-.11 2.53-1.3 3.74-3.85 3.86-1 .04-1.3.05-3.8.05s-2.8 0-3.79-.05c-2.55-.12-3.74-1.34-3.85-3.86-.05-1-.06-1.28-.06-3.79s.01-2.79.06-3.78C4.47 5.68 5.66 4.47 8.21 4.36c1-.05 1.29-.06 3.79-.06zM12 2.4c-2.55 0-2.87.01-3.87.06C4.72 2.62 2.83 4.5 2.67 7.92c-.05 1-.06 1.32-.06 3.87s.01 2.88.06 3.88c.16 3.41 2.04 5.3 5.46 5.46 1 .04 1.32.06 3.87.06s2.87-.02 3.87-.06c3.41-.16 5.31-2.04 5.46-5.46.05-1 .06-1.33.06-3.88s-.01-2.87-.06-3.87c-.15-3.41-2.04-5.3-5.45-5.46-1-.05-1.33-.06-3.88-.06zm0 4.57a5.03 5.03 0 1 0 0 10.06 5.03 5.03 0 0 0 0-10.06zm0 8.3a3.27 3.27 0 1 1 0-6.53 3.27 3.27 0 0 1 0 6.54zm5.23-9.68a1.18 1.18 0 1 0 0 2.35 1.18 1.18 0 0 0 0-2.35z"/></svg></a>
          <a href="{{ pinterest_url }}" target="_blank" rel="noopener" aria-label="Pinterest"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12c0 4.24 2.64 7.86 6.36 9.3-.09-.79-.17-2 .03-2.86.18-.78 1.17-4.97 1.17-4.97s-.3-.6-.3-1.48c0-1.39.8-2.42 1.8-2.42.85 0 1.26.64 1.26 1.4 0 .86-.54 2.14-.83 3.33-.24 1 .5 1.81 1.48 1.81 1.78 0 3.14-1.87 3.14-4.57 0-2.39-1.72-4.06-4.17-4.06-2.84 0-4.51 2.13-4.51 4.33 0 .86.33 1.78.74 2.28.08.1.09.19.07.29-.08.32-.25 1-.28 1.14-.04.18-.15.22-.34.13-1.25-.58-2.03-2.4-2.03-3.87 0-3.15 2.29-6.04 6.6-6.04 3.47 0 6.16 2.47 6.16 5.77 0 3.45-2.17 6.22-5.19 6.22-1.01 0-1.97-.53-2.3-1.15l-.62 2.39c-.23.86-.83 1.94-1.24 2.6.94.29 1.92.44 2.95.44 5.52 0 10-4.48 10-10S17.52 2 12 2z"/></svg></a>
          <a href="{{ twitter_url }}" target="_blank" rel="noopener" aria-label="X"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.9 1.15h3.68l-8.04 9.19L24 22.85h-7.41l-5.8-7.58-6.64 7.58H.46l8.6-9.83L0 1.15h7.6l5.24 6.93 6.06-6.93zm-1.29 19.5h2.04L6.49 3.24H4.3L17.61 20.65z"/></svg></a>
        </p>
      </div>
      <div class="footer-col">
        <p class="footer-heading">Browse</p>
        <a href="index.html">Current deals</a>
        <a href="biggest-drops.html">Biggest drops this week</a>
        <a href="gift-guide.html">Gift guide</a>
        <a href="best-board-games.html">Hot board games</a>
        <a href="guides.html">Buying guides</a>
        <a href="about.html">About</a>
      </div>
      <div class="footer-col">
        <p class="footer-heading">Popular guides</p>
        <a href="guide-reading-price-history.html">Is this deal actually good?</a>
        <a href="guide-gateway-games.html">Gateway games</a>
        <a href="guide-seasonal-sales.html">When sales actually happen</a>
        <a href="how-we-pick-deals.html">How we pick deals</a>
      </div>
      <div class="footer-col">
        <p class="footer-heading">Never miss a drop</p>
        <p class="footer-note">Every deal is posted to Facebook and Instagram the moment we find it. Follow there, or grab the <a href="deals.xml">RSS feed</a>.</p>
      </div>
    </div>
    <div class="footer-bottom">
      <p>{{ disclosure }}</p>
      <p>&copy; {{ year }} {{ site_name }} &middot; Last updated {{ updated }} UTC</p>
    </div>
  </div>
</footer>
<button class="to-top" aria-label="Back to top">&uarr;</button>
<script src="site.js" defer></script>
{% if onelink_onetag %}{{ onelink_onetag|safe }}{% endif %}
</body>
</html>
""")

DEAL_CARD_TEMPLATE = env.from_string("""
<article class="deal reveal" data-off="{{ deal.percent_off }}" data-price="{{ deal.price }}" data-rating="{{ deal.rating or 0 }}" data-bs="{{ '1' if deal.is_best_seller else '0' }}">
  {# deal.image_url (the price-banner version) is for social posts, which have
     no surrounding page layout -- the site has its own price/rating block,
     so the plain branded thumbnail (no banner) fits better here #}
  {% set img = deal.site_image_url or deal.image %}
  {% if img %}<div class="deal-img"><img src="{{ img }}" alt="" loading="lazy"></div>{% endif %}
  <div class="deal-body">
    <h2 class="deal-title"><a href="{{ deal.link }}" rel="nofollow sponsored noopener" target="_blank">{{ deal.short_title or deal.title }}</a></h2>
    <p class="price">
      <span class="now">${{ "%.2f"|format(deal.price) }}</span>
      <span class="was">${{ "%.2f"|format(deal.typical_price) }}</span>
      <span class="off">{{ deal.percent_off }}% OFF</span>
    </p>
    <p class="price-note">
      {% if at_low %}<span class="low-badge">&#128293; Lowest in 90 days</span>{% endif %}
      <span class="ctx">vs 90-day average{% if fresh %} &middot; found {{ fresh }}{% endif %}{% if deal.low_90d and not at_low %} &middot; 90-day low ${{ "%.2f"|format(deal.low_90d) }}{% endif %}</span>
    </p>
    {% if bar %}
    <div class="price-bar" aria-hidden="true">
      <span class="pb-track">
        <span class="pb-fill" style="width: {{ bar.now_pct }}%"></span>
        <span class="pb-avg" style="left: {{ bar.avg_pct }}%"></span>
        <span class="pb-now" style="left: {{ bar.now_pct }}%"></span>
      </span>
      <span class="pb-ends"><span>${{ "%.0f"|format(bar.low) }}</span><span class="pb-mid">90-day range</span><span>${{ "%.0f"|format(bar.high) }}</span></span>
    </div>
    {% endif %}
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
    {% if deal.detailed_description %}<p class="deal-description">{{ deal.detailed_description }}</p>{% endif %}
    <p class="deal-subtitle">{{ deal.title }}</p>
    <a class="buy" href="{{ deal.link }}" rel="nofollow sponsored noopener" target="_blank">View on Amazon &rarr;</a>
  </div>
</article>
""")

INDEX_CONTENT_TEMPLATE = env.from_string("""
<section class="hero">
  <div class="hero-copy">
    <p class="hero-kicker">The underground price index</p>
    <h1 class="hero-title">Great games.<br><span class="hero-gold">Black market prices.</span></h1>
    <p class="hero-sub">Every deal below is checked against 90 days of real Amazon price history.
    No inflated &#8220;was&#8221; prices, no fake sales &mdash; just genuine drops on games worth owning.</p>
    <div class="hero-cta">
      <a class="btn btn-gold" href="#deals">Browse today's deals</a>
      <a class="btn btn-ghost" href="best-board-games.html">Hot board games</a>
    </div>
    {% if stats %}
    <dl class="hero-stats">
      <div><dt>{{ stats.count }}</dt><dd>deals live now</dd></div>
      <div><dt>{{ stats.avg_off }}%</dt><dd>average discount</dd></div>
      <div><dt>{{ stats.max_off }}%</dt><dd>deepest cut</dd></div>
    </dl>
    {% endif %}
  </div>
  <svg class="hero-die" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" aria-hidden="true">
    <rect x="4" y="4" width="92" height="92" rx="14" fill="#e8b923"/>
    <rect x="4" y="4" width="92" height="44" rx="14" fill="#f0ca4a" opacity="0.3"/>
    <circle cx="30" cy="28" r="9" fill="#1c1a17"/>
    <circle cx="70" cy="28" r="9" fill="#1c1a17"/>
    <circle cx="30" cy="50" r="9" fill="#1c1a17"/>
    <circle cx="70" cy="50" r="9" fill="#1c1a17"/>
    <circle cx="30" cy="72" r="9" fill="#1c1a17"/>
    <circle cx="70" cy="72" r="9" fill="#1c1a17"/>
  </svg>
</section>

<div class="deals-header" id="deals">
  <h2 class="section-heading">Current Deals</h2>
  <span class="deals-freshness"><span class="pulse-dot" aria-hidden="true"></span>Re-checked every 4 hours</span>
</div>
<p class="section-links"><a href="biggest-drops.html">This week's biggest drops &rarr;</a><a href="gift-guide.html">Gift guide &rarr;</a></p>
{% if deals_html %}
<div class="filter-bar" role="group" aria-label="Filter and sort deals">
  <button class="chip is-active" data-filter="all">Newest deals</button>
  <button class="chip" data-sort="off-desc">Biggest cuts</button>
  <button class="chip" data-sort="rating-desc">Highest rated</button>
  <button class="chip" data-filter="under25">Under $25</button>
  <button class="chip" data-filter="bestseller">Best sellers</button>
</div>
<div class="deal-grid">{{ deals_html|safe }}</div>
<p class="filter-empty" hidden>Nothing matches that filter right now &mdash; try another.</p>
{% else %}
<p>No qualifying deals right now &mdash; check back soon.</p>
{% endif %}
""")

GUIDES_INDEX_TEMPLATE = env.from_string("""
{{ hero|safe }}
<div class="guide-grid">
{% for href, title, description in guides %}
  <a class="guide-card reveal" href="{{ href }}">
    <span class="guide-num">{{ "%02d"|format(loop.index) }}</span>
    <span class="guide-body">
      <h3>{{ title }}</h3>
      <p>{{ description }}</p>
      <span class="bbg-cta">Read the guide</span>
    </span>
  </a>
{% endfor %}
</div>
""")


def _crumbs(*parts: tuple[str, str | None]) -> str:
    items = [
        f'<a href="{href}">{html_lib.escape(label)}</a>' if href
        else f'<span class="crumb-here">{html_lib.escape(label)}</span>'
        for label, href in parts
    ]
    return '<nav class="crumbs">' + '<span class="crumb-sep">/</span>'.join(items) + "</nav>"


def _page_hero(kicker: str, title: str, sub: str = "", crumbs: str = "", note: str = "") -> str:
    # kicker/note are our own strings and may carry entities (&middot;);
    # title/sub can contain arbitrary text -> escape those
    sub_html = f'<p class="page-sub">{html_lib.escape(sub)}</p>' if sub else ""
    note_html = f'<p class="page-note">{note}</p>' if note else ""
    return (
        f'<div class="page-hero">{crumbs}'
        f'<p class="hero-kicker">{kicker}</p>'
        f"<h1>{html_lib.escape(title)}</h1>{sub_html}{note_html}</div>"
    )


def _strip_leading_h1(page_html: str) -> str:
    return re.sub(r"<h1[^>]*>.*?</h1>\s*", "", page_html, count=1, flags=re.DOTALL)


def _deal_freshness(posted_at: str | None) -> str | None:
    """Human 'found Xh/Xd ago' for a deal card -- a small urgency + freshness cue."""
    if not posted_at:
        return None
    try:
        dt = datetime.fromisoformat(str(posted_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    if hours < 1:
        return "just now"
    if hours < 24:
        return f"{int(hours)}h ago"
    return f"{int(hours // 24)}d ago"


def _price_bar(deal: dict[str, Any]) -> dict[str, Any] | None:
    """Geometry for a small 90-day price-range bar: where the current price and
    the 90-day average sit between the 90-day low and high. Visual proof of the
    'below the 90-day average' promise. None when we lack the low to anchor it."""
    low = deal.get("low_90d")
    price = deal.get("price")
    avg = deal.get("typical_price")
    if not low or not price or not avg or low <= 0:
        return None
    high = deal.get("high_90d") or deal.get("list_price") or avg
    high = max(high, avg, price)
    span = high - low
    if span <= 0:
        return None
    return {
        "low": low,
        "high": high,
        "now_pct": round(max(0, min(100, (price - low) / span * 100)), 1),
        "avg_pct": round(max(0, min(100, (avg - low) / span * 100)), 1),
    }

STYLE_CSS = """
:root {
  color-scheme: dark;
  --bg: #0e0d0b;
  --bg2: #131109;
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
  --live: #46d369;
  --display-font: 'Bebas Neue', Oswald, Impact, sans-serif;
  --heading-font: Oswald, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  --body-font: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  --radius: 10px;
  --shadow: 0 2px 12px rgba(0,0,0,.45);
  --shadow-lg: 0 4px 24px rgba(0,0,0,.6);
  --ease: cubic-bezier(.2,.6,.2,1);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

html {
  scroll-behavior: smooth;
  /* hidden = fallback for older mobile browsers; clip = modern, keeps
     position:sticky working. Insurance against any element ever making
     phones horizontally pannable. */
  overflow-x: hidden;
  overflow-x: clip;
}

body {
  font-family: var(--body-font);
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  overflow-x: clip;
}
/* gold hairline pinned to the very top of the viewport */
body::before {
  content: "";
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--gold-dim), var(--gold-bright) 50%, var(--gold-dim));
  z-index: 60;
}

.wrap { max-width: 1160px; margin: 0 auto; padding: 0 1.5rem; }
main.wrap { padding-bottom: 4rem; }

a { color: var(--gold); text-decoration: none; }
a:hover, a:focus { color: var(--gold-bright); text-decoration: underline; }

:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; border-radius: 2px; }

/* The site has no text inputs, so the blinking text caret that appears when you
   click on page text (and always-on with browser caret-browsing) is just noise.
   Hide it while keeping text selectable; restore it for any real field later. */
html { caret-color: transparent; }
input, textarea, [contenteditable] { caret-color: auto; }
::selection { background: var(--gold); color: var(--bg); }

h1, h2, h3, h4 { font-family: var(--heading-font); letter-spacing: .01em; line-height: 1.2; }
h1 { font-size: 2rem; margin: 1.5rem 0 .6rem; }
h2 { font-size: 1.4rem; margin: 1.5rem 0 .5rem; }
h3 { font-size: 1.1rem; margin: 1.2rem 0 .4rem; }
p { margin: .75rem 0; }
ul, ol { padding-left: 1.4rem; margin: .75rem 0; }
li { margin-bottom: .35rem; }

.skip-link {
  position: absolute;
  left: -9999px;
  top: 0;
  background: var(--gold);
  color: var(--bg);
  padding: .5rem 1rem;
  z-index: 100;
  font-weight: 600;
}
.skip-link:focus { left: 0; }

/* scroll-reveal (JS adds .in; no-JS builds skip the hidden state entirely) */
html.js .reveal {
  opacity: 0;
  transform: translateY(16px);
  transition: opacity .55s var(--ease), transform .55s var(--ease);
}
html.js .reveal.in { opacity: 1; transform: none; }

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  html.js .reveal { opacity: 1; transform: none; transition: none; }
  * { animation-duration: .01ms !important; animation-iteration-count: 1 !important; }
}

/* ── HEADER ─────────────────────────────── */
.site-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background:
    repeating-linear-gradient(-45deg, rgba(232,185,35,.02) 0 1px, transparent 1px 9px),
    rgba(16,14,11,.88);
  backdrop-filter: blur(14px) saturate(1.3);
  -webkit-backdrop-filter: blur(14px) saturate(1.3);
  border-bottom: 1px solid var(--panel-border);
  margin-bottom: 2.5rem;
}
.header-inner {
  max-width: 1160px;
  margin: 0 auto;
  padding: .95rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  transition: padding .25s var(--ease);
}
.site-header.scrolled .header-inner { padding-top: .5rem; padding-bottom: .5rem; }
.site-header.scrolled { box-shadow: var(--shadow-lg); }

.brand { display: flex; align-items: center; gap: .7rem; line-height: 1; }
.brand:hover { text-decoration: none; }
.brand-die {
  height: 2.6rem;
  width: 2.6rem;
  flex-shrink: 0;
  transform: rotate(-8deg);
  filter: drop-shadow(0 2px 10px rgba(232,185,35,.35));
  transition: transform .45s var(--ease);
}
.brand:hover .brand-die { transform: rotate(8deg) scale(1.06); }
.brand-text { display: flex; flex-direction: column; gap: .18rem; }
.brand-top {
  font-family: var(--heading-font);
  font-weight: 600;
  font-size: .62rem;
  text-transform: uppercase;
  letter-spacing: .42em;
  color: var(--text-muted);
}
.brand-main {
  font-family: var(--display-font);
  font-size: 1.8rem;
  letter-spacing: .05em;
  color: var(--gold);
  transition: color .2s;
}
.brand:hover .brand-main { color: var(--gold-bright); }

.site-nav { display: flex; align-items: center; gap: .25rem; }
.site-nav a {
  position: relative;
  font-family: var(--heading-font);
  font-weight: 500;
  font-size: .85rem;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--text-muted);
  padding: .5rem .8rem;
  transition: color .18s;
}
.site-nav a::after {
  content: "";
  position: absolute;
  left: .8rem; right: .8rem; bottom: .2rem;
  height: 2px;
  background: var(--gold);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform .25s var(--ease);
}
.site-nav a:hover { color: var(--text); text-decoration: none; }
.site-nav a:hover::after, .site-nav a.active::after { transform: scaleX(1); }
.site-nav a.active { color: var(--gold); }

.nav-social {
  display: flex;
  align-items: center;
  gap: .35rem;
  margin-left: .6rem;
  padding-left: .9rem;
  border-left: 1px solid var(--panel-border);
}
.nav-social a { padding: .4rem; color: var(--text-muted); display: inline-flex; transition: color .18s, transform .18s; }
.nav-social a:hover { color: var(--gold); transform: translateY(-2px); }
.nav-social svg { width: 18px; height: 18px; }

.nav-toggle {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  width: 44px;
  height: 44px;
  padding: 10px;
  background: none;
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  cursor: pointer;
}
.nav-toggle span {
  display: block;
  height: 2px;
  width: 100%;
  background: var(--gold);
  border-radius: 2px;
  transition: transform .25s var(--ease), opacity .2s;
}
.nav-toggle[aria-expanded="true"] span:nth-child(1) { transform: translateY(7px) rotate(45deg); }
.nav-toggle[aria-expanded="true"] span:nth-child(2) { opacity: 0; }
.nav-toggle[aria-expanded="true"] span:nth-child(3) { transform: translateY(-7px) rotate(-45deg); }

/* ── HERO ───────────────────────────────── */
.hero {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  padding: 2.5rem 0 3rem;
  margin-bottom: 1.5rem;
}
.hero::before {
  content: "";
  position: absolute;
  /* full-width layer with the light source painted INSIDE it (centered on
     the die) -- no glow box near the viewport edge, so nothing to cut off
     and nothing for phones to scroll into */
  inset: -4rem 0 -2rem 0;
  background: radial-gradient(34rem 26rem at 84% 45%, rgba(232,185,35,.13), rgba(232,185,35,.04) 45%, transparent 70%);
  /* the ellipse is still faintly gold where it meets the layer's right edge,
     which reads as a hard vertical seam -- fade the layer itself out first */
  -webkit-mask-image: linear-gradient(to right, #000 78%, transparent 99%);
  mask-image: linear-gradient(to right, #000 78%, transparent 99%);
  pointer-events: none;
}
.hero-copy { max-width: 40rem; }
.hero-kicker {
  font-family: var(--heading-font);
  font-weight: 600;
  font-size: .74rem;
  text-transform: uppercase;
  letter-spacing: .34em;
  color: var(--gold-dim);
  margin: 0 0 1rem;
  display: flex;
  align-items: center;
  gap: .7rem;
}
.hero-kicker::before { content: ""; width: 28px; height: 2px; background: var(--gold-dim); }
.hero-title {
  font-family: var(--display-font);
  font-size: clamp(3.2rem, 7vw, 5rem);
  font-weight: 400;
  line-height: .95;
  letter-spacing: .02em;
  color: #fff;
  margin: 0 0 1.1rem;
}
.hero-gold {
  color: var(--gold);
  text-shadow: 0 0 34px rgba(232,185,35,.35);
}
.hero-sub { font-size: 1.02rem; color: var(--text-muted); max-width: 33rem; margin: 0 0 1.6rem; }
.hero-cta { display: flex; flex-wrap: wrap; gap: .8rem; }

.hero-stats {
  display: flex;
  gap: 2.6rem;
  margin: 2.2rem 0 0;
}
.hero-stats dt {
  font-family: var(--display-font);
  font-size: 2.3rem;
  line-height: 1;
  color: var(--gold);
}
.hero-stats dd {
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .12em;
  color: var(--text-faint);
  margin-top: .3rem;
}

.hero-die {
  width: clamp(170px, 22vw, 270px);
  flex-shrink: 0;
  opacity: .92;
  transform: rotate(12deg);
  /* the gold aura rides on the die itself, so it follows the float */
  filter: drop-shadow(0 18px 40px rgba(0,0,0,.55)) drop-shadow(0 0 38px rgba(232,185,35,.22));
  animation: die-float 7s ease-in-out infinite;
}
@keyframes die-float {
  50% { transform: rotate(9deg) translateY(-14px); }
}

/* ── BUTTONS ────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: .5rem;
  font-family: var(--heading-font);
  font-weight: 600;
  font-size: .85rem;
  text-transform: uppercase;
  letter-spacing: .07em;
  padding: .72rem 1.5rem;
  border-radius: 8px;
  transition: background .18s, color .18s, border-color .18s, transform .18s, box-shadow .18s;
}
.btn:hover { text-decoration: none; transform: translateY(-2px); }
.btn-gold { background: var(--gold); color: var(--bg); }
.btn-gold:hover { background: var(--gold-bright); color: var(--bg); box-shadow: 0 6px 22px rgba(232,185,35,.3); }
.btn-ghost { border: 1px solid var(--panel-border); color: var(--text); }
.btn-ghost:hover { border-color: var(--gold); color: var(--gold); }

/* ── SECTION HEADINGS / FILTERS ─────────── */
.section-heading {
  font-family: var(--display-font);
  font-size: 2.1rem;
  font-weight: 400;
  letter-spacing: .03em;
  color: #fff;
  margin: 0;
}
.pulse-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--live);
  margin-right: .45rem;
  animation: pulse 2.2s ease-out infinite;
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(70,211,105,.45); }
  70% { box-shadow: 0 0 0 9px rgba(70,211,105,0); }
  100% { box-shadow: 0 0 0 0 rgba(70,211,105,0); }
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
  margin: 0 0 1.5rem;
}
.chip {
  font-family: var(--body-font);
  font-weight: 500;
  font-size: .82rem;
  color: var(--text-muted);
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: 999px;
  padding: .45rem 1.05rem;
  cursor: pointer;
  transition: color .15s, border-color .15s, background .15s, transform .15s;
}
.chip:hover { color: var(--text); border-color: var(--gold-dim); transform: translateY(-1px); }
.chip.is-active {
  background: var(--gold);
  border-color: var(--gold);
  color: var(--bg);
  font-weight: 600;
}
.filter-empty { color: var(--text-muted); padding: 1.5rem 0; }

/* ── DEAL GRID ──────────────────────────── */
.deals-header { display: flex; align-items: center; gap: 1.1rem; flex-wrap: wrap; margin-bottom: 1.1rem; scroll-margin-top: 90px; }
.deals-freshness { font-size: .82rem; color: var(--text-faint); display: inline-flex; align-items: center; }
.section-links { display: flex; flex-wrap: wrap; gap: 1.25rem; margin: 0 0 1.4rem; }
.section-links a { font-family: var(--heading-font); font-size: .82rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--gold); }
.section-links a:hover { color: var(--gold-bright); text-decoration: none; }

.deal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(265px, 1fr));
  gap: 1.25rem;
}

.deal {
  position: relative;      /* anchors the whole-card stretched link below */
  cursor: pointer;         /* the entire card is clickable -> Amazon */
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow);
}
/* Whole-card click: the deal title's link stretches an invisible layer across
   the entire card, so a click anywhere on the card follows it to Amazon (with
   the same rel="nofollow sponsored" affiliate link). The "View on Amazon"
   button sits above it so it still works as its own target. */
.deal-title a::after { content: ""; position: absolute; inset: 0; z-index: 1; }
.deal .buy { position: relative; z-index: 2; }
.deal:hover {
  border-color: var(--gold-dim);
  box-shadow: var(--shadow-lg);
  transform: translateY(-3px);
}
.deal.filtered-out { display: none; }
.deal-img { overflow: hidden; background: var(--bg2); }
.deal-img img, .deal > img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  display: block;
  background: var(--bg2);
  transition: transform .45s var(--ease);
}
.deal:hover .deal-img img { transform: scale(1.05); }
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

/* trust/urgency line under the price: clarifies the struck price is the
   90-day AVERAGE (our honest metric, not an inflated list price), flags a
   90-day low, and shows how fresh the deal is */
.price-note {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .35rem .5rem;
  margin: -.15rem 0 .6rem;
  font-size: .72rem;
  color: var(--text-faint);
  line-height: 1.3;
}
.price-note .low-badge {
  color: var(--gold-bright);
  border: 1px solid var(--gold-dim);
  background: rgba(232,185,35,.08);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .03em;
  font-size: .66rem;
  padding: .12rem .5rem;
  border-radius: 4px;
}

/* 90-day price-range bar: shows where the current price (gold dot) and the
   90-day average (tick) sit between the 90-day low and high -- visual proof
   the price is near its floor */
.price-bar { margin: 0 0 .7rem; }
.pb-track {
  position: relative;
  display: block;
  height: 5px;
  border-radius: 3px;
  background: linear-gradient(90deg, rgba(232,185,35,.10), var(--panel-border));
}
.pb-fill {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--gold-bright), var(--gold));
}
.pb-now {
  position: absolute;
  top: 50%;
  width: 12px; height: 12px;
  margin: -6px 0 0 -6px;
  border-radius: 50%;
  background: var(--gold-bright);
  border: 2px solid var(--bg);
  box-shadow: 0 0 0 1px var(--gold);
}
.pb-avg {
  position: absolute;
  top: -2px; bottom: -2px;
  width: 2px;
  margin-left: -1px;
  background: var(--text-muted);
}
.pb-ends {
  display: flex;
  justify-content: space-between;
  margin-top: .3rem;
  font-size: .64rem;
  color: var(--text-faint);
}
.pb-ends .pb-mid { color: var(--text-faint); letter-spacing: .04em; text-transform: uppercase; }

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

.deal-description {
  font-size: .85rem;
  color: var(--text-muted);
  line-height: 1.5;
  margin: 0 0 .7rem;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
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
  transition: color .15s, background .15s, box-shadow .15s, transform .1s;
  align-self: flex-start;
}
/* Hover inverts to white text on a dark fill (with a gold ring so it still
   reads as the gold button). Plain white on the gold background is only ~1.5:1
   contrast -- as unreadable as the gold-on-gold it replaced -- so the fill has
   to darken for the white to actually be legible. */
.buy:hover {
  color: #fff;
  background: var(--bg);
  box-shadow: inset 0 0 0 2px var(--gold);
  text-decoration: none;
  transform: translateY(-1px);
}

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
  object-fit: cover;
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
  transition: color .15s, background .15s, box-shadow .15s;
}
/* Same inverted hover as .buy -- plain white on the gold would be unreadable. */
.ranked-buy:hover { color: #fff; background: var(--bg); box-shadow: inset 0 0 0 2px var(--gold); text-decoration: none; }

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

/* ── PAGE HERO (interior pages) ───────── */
.page-hero {
  position: relative;
  padding: 1.6rem 0 2rem;
  margin-bottom: 2rem;
  border-bottom: 1px solid var(--panel-border);
}
.page-hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(26rem 12rem at 88% 8%, rgba(232,185,35,.07), transparent 65%);
  -webkit-mask-image: linear-gradient(to right, #000 80%, transparent 99%);
  mask-image: linear-gradient(to right, #000 80%, transparent 99%);
  pointer-events: none;
}
.crumbs {
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .12em;
  color: var(--text-faint);
  margin-bottom: 1.3rem;
}
.crumbs a { color: var(--text-muted); }
.crumbs a:hover { color: var(--gold); text-decoration: none; }
.crumb-sep { margin: 0 .35rem; color: var(--text-faint); }
.crumb-here { color: var(--gold-dim); }
.page-hero h1 {
  font-family: var(--display-font);
  font-weight: 400;
  font-size: clamp(2.4rem, 5vw, 3.5rem);
  line-height: .95;
  letter-spacing: .02em;
  color: #fff;
  margin: 0 0 .8rem;
}
.page-sub { color: var(--text-muted); max-width: 46rem; margin: 0; font-size: 1rem; }
.page-note { font-size: .75rem; color: var(--text-faint); margin: .9rem 0 0; }

/* ── HOT BOARD GAMES HUB CARDS ────────── */
.bbg-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
}
.bbg-card {
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
  padding: 1.4rem 1.4rem 1.25rem;
  box-shadow: var(--shadow);
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
.bbg-card:hover {
  border-color: var(--gold-dim);
  box-shadow: var(--shadow-lg);
  transform: translateY(-3px);
  text-decoration: none;
}
.bbg-card-imgs { display: flex; margin-bottom: 1.1rem; }
.bbg-card-imgs img {
  width: 58px;
  height: 58px;
  border-radius: 12px;
  border: 2px solid var(--panel-border);
  background: var(--bg2);
  object-fit: cover;
  margin-left: -16px;
  box-shadow: 0 4px 12px rgba(0,0,0,.45);
  transition: transform .25s var(--ease);
}
.bbg-card-imgs img:first-child { margin-left: 0; }
.bbg-card:hover .bbg-card-imgs img:nth-child(1) { transform: translateY(-4px) rotate(-3deg); }
.bbg-card:hover .bbg-card-imgs img:nth-child(2) { transform: translateY(-6px); }
.bbg-card:hover .bbg-card-imgs img:nth-child(3) { transform: translateY(-4px) rotate(3deg); }
.bbg-card:hover .bbg-card-imgs img:nth-child(4) { transform: translateY(-6px) rotate(-2deg); }
.bbg-card:hover .bbg-card-imgs img:nth-child(5) { transform: translateY(-4px) rotate(2deg); }
.bbg-card-body { display: flex; flex-direction: column; flex: 1; }
.bbg-count {
  font-family: var(--heading-font);
  font-weight: 600;
  font-size: .66rem;
  text-transform: uppercase;
  letter-spacing: .18em;
  color: var(--gold-dim);
  margin-bottom: .4rem;
}
.bbg-card h3 {
  font-family: var(--heading-font);
  font-size: 1.15rem;
  line-height: 1.25;
  color: #fff;
  margin: 0 0 .45rem;
}
.bbg-card p { font-size: .84rem; color: var(--text-muted); line-height: 1.55; margin: 0 0 1rem; flex: 1; }
.bbg-cta {
  font-family: var(--heading-font);
  font-weight: 600;
  font-size: .76rem;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--gold);
  display: inline-flex;
  align-items: center;
  gap: .4rem;
}
.bbg-cta::after { content: "\\2192"; transition: transform .2s var(--ease); }
.bbg-card:hover .bbg-cta::after, .guide-card:hover .bbg-cta::after, .related-card:hover .bbg-cta::after { transform: translateX(4px); }

.bbg-card.featured {
  grid-column: 1 / -1;
  flex-direction: row;
  align-items: center;
  gap: 2.25rem;
  padding: 1.9rem 2.2rem;
  background:
    radial-gradient(circle at 85% 20%, rgba(232,185,35,.08), transparent 55%),
    var(--panel);
}
.bbg-card.featured .bbg-card-imgs { margin-bottom: 0; flex-shrink: 0; }
.bbg-card.featured .bbg-card-imgs img { width: 76px; height: 76px; }
.bbg-card.featured h3 { font-size: 1.55rem; }
.bbg-card.featured p { font-size: .92rem; }

/* ── GUIDES INDEX CARDS ───────────────── */
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}
.guide-card {
  display: flex;
  gap: 1.3rem;
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
  padding: 1.5rem;
  box-shadow: var(--shadow);
  transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
.guide-card:hover {
  border-color: var(--gold-dim);
  box-shadow: var(--shadow-lg);
  transform: translateY(-3px);
  text-decoration: none;
}
.guide-num {
  font-family: var(--display-font);
  font-size: 2.5rem;
  line-height: 1;
  color: var(--gold);
  opacity: .5;
  min-width: 2.4rem;
  transition: opacity .2s;
}
.guide-card:hover .guide-num { opacity: 1; }
.guide-body { display: flex; flex-direction: column; }
.guide-card h3 { font-family: var(--heading-font); font-size: 1.08rem; line-height: 1.3; color: #fff; margin: 0 0 .4rem; }
.guide-card p { font-size: .85rem; color: var(--text-muted); line-height: 1.55; margin: 0 0 .9rem; flex: 1; }

/* ── PROSE (article pages) ────────────── */
.prose { max-width: 46rem; line-height: 1.75; }
.prose > p:first-of-type { font-size: 1.13rem; color: #e5ddc8; }
.prose h2 {
  font-size: 1.35rem;
  color: #fff;
  margin: 2.3rem 0 .8rem;
  padding-left: .85rem;
  border-left: 3px solid var(--gold);
}
.prose h3 { font-size: 1.08rem; color: #fff; margin: 1.7rem 0 .5rem; }
.prose p { margin: .95rem 0; }
.prose ul, .prose ol { margin: 1rem 0; padding-left: 1.5rem; }
.prose li { margin-bottom: .5rem; }
.prose li::marker { color: var(--gold); }
.prose a { text-decoration: underline; text-decoration-color: rgba(232,185,35,.45); text-underline-offset: 3px; }
.prose a:hover { text-decoration-color: var(--gold-bright); }
.prose strong { color: #fff; }
.prose blockquote {
  border-left: 3px solid var(--gold-dim);
  padding: .25rem 1.1rem;
  margin: 1.2rem 0;
  color: var(--text-muted);
}
.prose table { border-collapse: collapse; margin: 1.2rem 0; width: 100%; font-size: .9rem; }
.prose th, .prose td { border: 1px solid var(--panel-border); padding: .55rem .8rem; text-align: left; }
.prose th { background: var(--panel); font-family: var(--heading-font); font-weight: 600; }

/* ── MORE / RELATED BLOCKS ────────────── */
.more-block { margin-top: 3.5rem; padding-top: 1.75rem; border-top: 1px solid var(--panel-border); }
.more-title {
  font-family: var(--display-font);
  font-size: 1.05rem;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--gold);
  margin: 0 0 1.1rem;
}
.more-pills { display: flex; flex-wrap: wrap; gap: .5rem; }
.more-pills a {
  font-size: .84rem;
  font-weight: 500;
  color: var(--text-muted);
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: 999px;
  padding: .45rem 1.05rem;
  transition: color .15s, border-color .15s, transform .15s;
}
.more-pills a:hover { color: var(--gold); border-color: var(--gold-dim); transform: translateY(-1px); text-decoration: none; }

.related-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
.related-card {
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
  padding: 1.15rem 1.2rem;
  transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease;
}
.related-card:hover {
  border-color: var(--gold-dim);
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
  text-decoration: none;
}
.related-card h4 { font-family: var(--heading-font); font-size: .96rem; line-height: 1.3; color: #fff; margin: 0 0 .35rem; }
.related-card p { font-size: .78rem; color: var(--text-muted); line-height: 1.5; margin: 0 0 .8rem; flex: 1; }

/* ranked list rows: subtle hover */
.ranked-item { border-radius: 8px; transition: background .2s; padding-left: .5rem; padding-right: .5rem; margin: 0 -.5rem; }
.ranked-item:hover { background: rgba(255,255,255,.025); }

@media (max-width: 900px) {
  .bbg-grid { grid-template-columns: 1fr 1fr; }
  .bbg-card.featured { flex-direction: column; align-items: flex-start; gap: 1.2rem; }
  .related-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .bbg-grid, .guide-grid { grid-template-columns: 1fr; }
  .bbg-card.featured { padding: 1.4rem; gap: 1rem; }
  .bbg-card.featured .bbg-card-imgs img { width: 56px; height: 56px; }
  .bbg-card.featured h3 { font-size: 1.25rem; }
  .guide-card { padding: 1.2rem; gap: 1rem; }
  .guide-num { font-size: 2rem; min-width: 2rem; }
  .page-hero { padding: 1rem 0 1.5rem; margin-bottom: 1.5rem; }
  .page-hero h1 { font-size: clamp(1.9rem, 8.5vw, 2.6rem); }
  .crumbs { font-size: .66rem; margin-bottom: 1rem; }
  .more-block { margin-top: 2.5rem; }
}

/* ── FOOTER ─────────────────────────── */
.site-footer {
  margin-top: 5rem;
  border-top: 1px solid var(--panel-border);
  background: var(--bg2);
  padding: 3rem 0 2rem;
  font-size: .88rem;
}
.footer-grid {
  display: grid;
  grid-template-columns: 1.6fr 1fr 1.2fr 1.4fr;
  gap: 2.5rem;
}
.footer-logo {
  font-family: var(--display-font);
  font-size: 1.45rem;
  letter-spacing: .05em;
  color: var(--text);
  margin: 0 0 .4rem;
  line-height: 1.1;
}
.footer-logo span { color: var(--gold); }
.footer-tag { color: var(--text-faint); font-size: .84rem; margin: 0 0 1rem; }
.footer-social { display: flex; gap: .9rem; margin: 0; }
.footer-social a { color: var(--text-muted); display: inline-flex; transition: color .18s, transform .18s; }
.footer-social a:hover { color: var(--gold); transform: translateY(-2px); }
.footer-social svg { width: 20px; height: 20px; }

.footer-col { display: flex; flex-direction: column; gap: .5rem; }
.footer-heading {
  font-family: var(--heading-font);
  font-weight: 600;
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .22em;
  color: var(--gold-dim);
  margin: 0 0 .4rem;
}
.footer-col a { color: var(--text-muted); font-size: .86rem; }
.footer-col a:hover { color: var(--gold); text-decoration: none; }
.footer-note { color: var(--text-muted); font-size: .84rem; margin: 0; line-height: 1.55; }

.footer-bottom {
  margin-top: 2.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid rgba(255,255,255,.05);
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: .5rem 2rem;
  color: var(--text-faint);
  font-size: .76rem;
}
.footer-bottom p { margin: 0; }

/* ── BACK TO TOP ─────────────────────── */
.to-top {
  position: fixed;
  bottom: 1.4rem;
  right: 1.4rem;
  z-index: 40;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: var(--panel);
  border: 1px solid var(--panel-border);
  color: var(--gold);
  font-size: 1.15rem;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transform: translateY(10px);
  transition: opacity .25s, transform .25s, background .18s, color .18s;
  box-shadow: var(--shadow);
}
.to-top.show { opacity: 1; pointer-events: auto; transform: none; }
.to-top:hover { background: var(--gold); color: var(--bg); border-color: var(--gold); }

/* ── RESPONSIVE ─────────────────────── */
@media (max-width: 900px) {
  .hero-die { display: none; }
  /* the die (the glow's anchor) is hidden here -- fall back to a soft
     top-right corner wash instead of a light source over empty space */
  .hero::before { background: radial-gradient(24rem 14rem at 100% 0%, rgba(232,185,35,.08), transparent 65%); }
  .footer-grid { grid-template-columns: 1fr 1fr; gap: 2rem; }
}
@media (max-width: 820px) {
  .nav-toggle { display: flex; }
  .site-nav {
    display: none;
    position: absolute;
    top: 100%;
    left: 0; right: 0;
    flex-direction: column;
    align-items: stretch;
    gap: 0;
    background: rgba(16,14,11,.98);
    border-bottom: 1px solid var(--panel-border);
    padding: .5rem 1.25rem 1rem;
    box-shadow: var(--shadow-lg);
  }
  .site-nav.open { display: flex; }
  .site-nav a { padding: .8rem .4rem; border-bottom: 1px solid rgba(255,255,255,.04); }
  .site-nav a::after { display: none; }
  .nav-social { margin: .6rem 0 0; padding: .6rem 0 0; border-left: none; border-top: 1px solid var(--panel-border); }
}
@media (max-width: 600px) {
  .wrap, .header-inner { padding-left: 1rem; padding-right: 1rem; }
  .brand-main { font-size: 1.5rem; }
  .brand-top { font-size: .55rem; letter-spacing: .34em; }
  .brand-die { height: 2.1rem; width: 2.1rem; }
  h1 { font-size: 1.6rem; }
  .hero { padding: 1.5rem 0 2rem; }
  .hero-title { font-size: clamp(2.2rem, 10.5vw, 3.2rem); }
  .hero-stats { gap: 1.6rem; }
  .hero-stats dt { font-size: 1.9rem; }
  .section-heading { font-size: 1.7rem; }
  .deal-grid, .game-grid { grid-template-columns: 1fr 1fr; gap: .85rem; }
  .deal-title { font-size: 1.2rem; }
  .deal .price .now { font-size: 1.7rem; }
  .footer-grid { grid-template-columns: 1fr; gap: 1.75rem; }
}
@media (max-width: 400px) {
  .deal-grid, .game-grid { grid-template-columns: 1fr; }
}
"""

SITE_JS = """
(function () {
  var header = document.querySelector('.site-header');
  var toTop = document.querySelector('.to-top');

  // Hysteresis: shrink at 48px, expand only back at 8px. A single threshold
  // makes the header's own height change re-cross the threshold and the page
  // visibly vibrates when resting near the top.
  var shrunk = false;
  function onScroll() {
    var y = window.scrollY;
    if (header) {
      if (!shrunk && y > 48) { shrunk = true; header.classList.add('scrolled'); }
      else if (shrunk && y < 8) { shrunk = false; header.classList.remove('scrolled'); }
    }
    if (toTop) toTop.classList.toggle('show', y > 600);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  if (toTop) {
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  var toggle = document.querySelector('.nav-toggle');
  var nav = document.getElementById('site-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        nav.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  // Deal filter/sort chips (index page only)
  var chips = document.querySelectorAll('.chip');
  var grid = document.querySelector('.deal-grid');
  var cards = document.querySelectorAll('.deal-grid .deal');
  var order = Array.prototype.slice.call(cards);  // original DOM order (newest first)
  var empty = document.querySelector('.filter-empty');
  var tests = {
    all: function () { return true; },
    under25: function (c) { return parseFloat(c.dataset.price) < 25; },
    bestseller: function (c) { return c.dataset.bs === '1'; }
  };
  var sorts = {
    'off-desc': function (a, b) { return parseFloat(b.dataset.off) - parseFloat(a.dataset.off); },
    'rating-desc': function (a, b) { return parseFloat(b.dataset.rating) - parseFloat(a.dataset.rating); }
  };
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { c.classList.remove('is-active'); });
      chip.classList.add('is-active');
      var shown = 0;
      var sortFn = sorts[chip.dataset.sort];
      if (sortFn) {
        // Sort mode: show every card, reordered (deepest cut / highest rating first).
        order.slice().sort(sortFn).forEach(function (card) {
          card.classList.remove('filtered-out');
          card.classList.add('in');
          if (grid) grid.appendChild(card);
          shown++;
        });
      } else {
        // Restore the original newest-first order, then apply the filter.
        var test = tests[chip.dataset.filter] || tests.all;
        order.forEach(function (card) {
          if (grid) grid.appendChild(card);
          var ok = test(card);
          card.classList.toggle('filtered-out', !ok);
          if (ok) { shown++; card.classList.add('in'); }
        });
      }
      if (empty) empty.hidden = shown !== 0;
    });
  });

  // Scroll-reveal
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var revealEls = document.querySelectorAll('.reveal');
  if (reduced || !('IntersectionObserver' in window)) {
    revealEls.forEach(function (el) { el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -40px 0px', threshold: 0.05 });
    revealEls.forEach(function (el) { io.observe(el); });
  }
})();
"""


def render_site(deals: list[dict[str, Any]], max_listed: int = 60) -> None:
    """Rebuilds the entire site/ directory. Safe to call every run."""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    (SITE_DIR / "style.css").write_text(STYLE_CSS.strip() + "\n", encoding="utf-8")
    (SITE_DIR / "site.js").write_text(SITE_JS.strip() + "\n", encoding="utf-8")

    # skip deals whose discount has ended (kept in the log as sale history)
    # and deals without box art (a bare card looks broken)
    deals = [d for d in deals if not d.get("expired_at") and (d.get("site_image_url") or d.get("image"))]
    deals = deals[:max_listed]
    stats = None
    if deals:
        offs = [d.get("percent_off") or 0 for d in deals]
        stats = {
            "count": len(deals),
            "avg_off": round(sum(offs) / len(offs)),
            "max_off": max(offs),
        }
    cards = "\n".join(
        DEAL_CARD_TEMPLATE.render(
            deal=d,
            fresh=_deal_freshness(d.get("posted_at")),
            at_low=d.get("percent_above_low") == 0,
            bar=_price_bar(d),
        )
        for d in deals
    )
    index_content = INDEX_CONTENT_TEMPLATE.render(tagline=TAGLINE, deals_html=cards, stats=stats)
    _write_page(
        "index.html", "Board Game Deals", "Automatically tracked board game price drops on Amazon, updated every few hours.",
        index_content, updated, active="deals", jsonld=_index_jsonld(deals),
    )

    guides = [
        (out_filename, _title_from_html((CONTENT_DIR / content_filename).read_text()) or out_filename, description)
        for content_filename, out_filename, _nav_title, description in EVERGREEN_PAGES
        if content_filename.startswith("guide-") and (CONTENT_DIR / content_filename).exists()
    ]

    for content_filename, out_filename, _nav_title, description in EVERGREEN_PAGES:
        source = CONTENT_DIR / content_filename
        if not source.exists():
            continue  # don't fail the whole run over one missing evergreen page
        page_html = source.read_text(encoding="utf-8")
        title = _title_from_html(page_html) or out_filename
        body = f'<article class="prose">{_strip_leading_h1(page_html)}</article>'

        if content_filename.startswith("guide-"):
            active = "guides"
            crumbs = _crumbs(("Home", "index.html"), ("Guides", "guides.html"), (title, None))
            hero = _page_hero("Field manual", title, description, crumbs)
            body += _related_guides_html(out_filename, guides)
        else:
            active = "about"
            kicker = "The method" if out_filename.startswith("how-we-pick") else "The operation"
            crumbs = _crumbs(("Home", "index.html"), (title, None))
            hero = _page_hero(kicker, title, description, crumbs)
        _write_page(out_filename, title, description, hero + body, updated, active=active)

    guides_hero = _page_hero(
        "The field manual",
        "Guides",
        "Practical, no-nonsense answers to the questions every board game buyer eventually asks.",
        _crumbs(("Home", "index.html"), ("Guides", None)),
    )
    guides_content = GUIDES_INDEX_TEMPLATE.render(guides=guides, hero=guides_hero)
    _write_page("guides.html", "Guides", "Practical board-game buying guides.", guides_content, updated, active="guides")

    _render_rankings_section(updated)
    _render_biggest_drops(deals, updated)
    _render_gift_guide(deals, updated)
    _write_seo_files(deals, updated)


def _related_guides_html(current: str, guides: list[tuple[str, str, str]]) -> str:
    """Three other guides, picked cyclically from the current one's position."""
    others = [g for g in guides if g[0] != current]
    if not others:
        return ""
    idx = next((i for i, g in enumerate(guides) if g[0] == current), 0)
    picks = [others[(idx + i) % len(others)] for i in range(min(3, len(others)))]
    cards = "".join(
        f'<a class="related-card reveal" href="{href}"><h4>{html_lib.escape(title)}</h4>'
        f'<p>{html_lib.escape(desc)}</p><span class="bbg-cta">Read</span></a>'
        for href, title, desc in picks
    )
    return f'<div class="more-block"><p class="more-title">More from the field manual</p><div class="related-grid">{cards}</div></div>'


def _index_jsonld(deals: list[dict[str, Any]]) -> str:
    """WebSite + Organization + ItemList structured data for the homepage.

    Deliberately NOT Product/Offer markup: that classifies the page as a
    merchant listing and Google then demands merchant-only fields (return
    policy, shipping, GTINs) that only Amazon -- the actual merchant -- can
    provide. Search Console flagged exactly that (2026-07-04). A plain
    ItemList, like the ranked-list pages use, carries no such obligations."""
    items = []
    for i, d in enumerate(deals[:20], start=1):
        entry: dict[str, Any] = {
            "@type": "ListItem",
            "position": i,
            "name": d.get("short_title") or d.get("title", ""),
            "url": d.get("link", ""),
        }
        img = d.get("site_image_url") or d.get("image")
        if img:
            entry["image"] = f"{BASE_URL}/{img}" if not str(img).startswith("http") else img
        items.append(entry)

    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": SITE_NAME,
                "url": BASE_URL,
                "description": TAGLINE.replace("--", "—"),
            },
            {
                "@type": "Organization",
                "name": SITE_NAME,
                "url": BASE_URL,
                "logo": f"{BASE_URL}/og-image.png",
                "sameAs": [FACEBOOK_URL, INSTAGRAM_URL, PINTEREST_URL, TWITTER_URL],
            },
            {"@type": "ItemList", "itemListElement": items},
        ],
    }
    return json.dumps(graph, ensure_ascii=False)


LASTMOD_STATE = ROOT / "config" / "page_lastmod.json"

# Bits of every page that change on every run without the content really
# changing: the footer clock and the "found Xh ago" deal freshness labels.
# They must not count as a modification, or every page would claim it changed
# on every run -- which is exactly what made our sitemap lastmod meaningless.
_VOLATILE_RE = re.compile(r"Last updated \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC|found [^<]*ago")


def _page_lastmods(pages: list[str], today: str) -> dict[str, str]:
    """Real per-page lastmod dates for the sitemap.

    Google only honours lastmod when it's accurate; claiming all 27 pages
    changed today on every 4-hourly run trains it to distrust the sitemap and
    deprioritise crawling (pages sit in "Discovered - currently not indexed").
    So hash each page with the volatile bits stripped and only advance its date
    when the meaningful content actually changed."""
    import hashlib

    try:
        state = json.loads(LASTMOD_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}

    out: dict[str, str] = {}
    for name in pages:
        try:
            html = (SITE_DIR / name).read_text(encoding="utf-8")
        except OSError:
            out[name] = today
            continue
        digest = hashlib.sha1(_VOLATILE_RE.sub("", html).encode("utf-8")).hexdigest()
        prev = state.get(name) or {}
        if prev.get("hash") == digest and prev.get("lastmod"):
            out[name] = prev["lastmod"]          # unchanged -- keep the old date
        else:
            out[name] = today                    # genuinely changed today
        state[name] = {"hash": digest, "lastmod": out[name]}

    state = {k: v for k, v in state.items() if k in set(pages)}  # drop deleted pages
    try:
        LASTMOD_STATE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(LASTMOD_STATE, json.dumps(state, indent=2, sort_keys=True))
    except OSError:
        pass  # a stale lastmod is never worth failing a render over
    return out


def _write_seo_files(deals: list[dict[str, Any]], updated: str) -> None:
    """sitemap.xml, robots.txt, and an RSS feed of current deals."""
    from email.utils import format_datetime
    from xml.sax.saxutils import escape

    today = updated[:10]
    pages = sorted(p.name for p in SITE_DIR.glob("*.html"))
    lastmods = _page_lastmods(pages, today)
    url_entries = "\n".join(
        f"  <url><loc>{BASE_URL}/{'' if name == 'index.html' else name}</loc>"
        f"<lastmod>{lastmods.get(name, today)}</lastmod></url>"
        for name in pages
    )
    sitemap = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{url_entries}\n</urlset>\n'
    (SITE_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    robots = f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n"
    (SITE_DIR / "robots.txt").write_text(robots, encoding="utf-8")

    now_utc = datetime.now(timezone.utc)
    items_xml = ""
    for d in deals[:25]:
        title = f"{d.get('short_title') or d.get('title', '')} — ${d.get('price', 0):.2f} ({d.get('percent_off', 0)}% off)"
        pub = now_utc
        if d.get("posted_at"):
            try:
                pub = datetime.fromisoformat(str(d["posted_at"]).replace("Z", "+00:00"))
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        desc_bits = [f"${d.get('price', 0):.2f}, was ${d.get('typical_price', 0):.2f} — {d.get('percent_off', 0)}% off."]
        if d.get("rating"):
            desc_bits.append(f"{d['rating']}/5 stars ({d.get('review_count') or 0} reviews).")
        items_xml += (
            "  <item>\n"
            f"    <title>{escape(title)}</title>\n"
            f"    <link>{escape(d.get('link', BASE_URL))}</link>\n"
            f"    <guid isPermaLink=\"false\">{escape(str(d.get('asin', '')))}-{d.get('price', 0)}</guid>\n"
            f"    <pubDate>{format_datetime(pub)}</pubDate>\n"
            f"    <description>{escape(' '.join(desc_bits))}</description>\n"
            "  </item>\n"
        )
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n<channel>\n'
        f"  <title>{escape(SITE_NAME)} — Deal Feed</title>\n"
        f"  <link>{BASE_URL}</link>\n"
        "  <description>Genuine board game price drops, checked against 90-day Amazon price history.</description>\n"
        f"  <lastBuildDate>{format_datetime(now_utc)}</lastBuildDate>\n"
        f"{items_xml}"
        "</channel>\n</rss>\n"
    )
    (SITE_DIR / "deals.xml").write_text(rss, encoding="utf-8")


def _ranked_thumb_src(game: dict[str, Any]) -> str | None:
    """Branded thumbnail URL for a ranked game; falls back to the raw Amazon
    image if compositing isn't possible."""
    image_id = game.get("image_id")
    if not image_id:
        return None
    try:
        import image_compose
        rel = image_compose.compose_ranked_thumb(game["asin"], image_id)
    except Exception:
        rel = None
    return rel or f"https://m.media-amazon.com/images/I/{image_id}"


def _render_rankings_section(updated: str) -> None:
    """Generate all Best Board Games pages from the rankings cache."""
    if not RANKINGS_CACHE.exists():
        return
    cache = json.loads(RANKINGS_CACHE.read_text(encoding="utf-8"))
    lists = cache.get("lists", {})

    # Hub page: one collage card per list, top games' box art stacked
    hub_sections = [
        ("Hot Right Now", ["all-time"]),
        ("Player Count", ["solo", "2p", "3p", "4p", "5p", "6p-plus"]),
        ("By Genre", ["strategy", "coop", "social-deduction", "party", "family", "gateway"]),
    ]

    # Cross-list frequency: staples like Catan appear in many lists, so
    # collages prefer each list's DISTINCTIVE games (fewest appearances)
    # to keep the hub visually varied. List order itself is unchanged.
    freq: dict[str, int] = {}
    for lst in lists.values():
        for g in lst.get("games", []):
            freq[g["asin"]] = freq.get(g["asin"], 0) + 1

    hub_items_html = ""
    for section_label, keys in hub_sections:
        cards_html = ""
        for key in keys:
            lst = lists.get(key)
            if not lst:
                continue
            slug = lst["slug"]
            title = lst["title"]
            desc = lst["description"].replace("\n", " ").strip()
            games = lst.get("games", [])
            featured = key == "all-time"
            n_thumbs = 5 if featured else 3
            # rarest-first, rank as tiebreaker, only games with box art
            thumb_imgs = sorted(
                (g for g in games if g.get("image_id")),
                key=lambda g, _games=games: (freq.get(g["asin"], 0), _games.index(g)),
            )[:n_thumbs]
            thumbs = "".join(
                f'<img src="{_ranked_thumb_src(g)}" alt="" loading="lazy">'
                for g in thumb_imgs
            )
            feat_cls = " featured" if featured else ""
            cards_html += (
                f'<a class="bbg-card{feat_cls} reveal" href="{slug}.html">'
                f'<div class="bbg-card-imgs">{thumbs}</div>'
                f'<div class="bbg-card-body">'
                f'<span class="bbg-count">{len(games)} games ranked</span>'
                f"<h3>{html_lib.escape(title)}</h3><p>{html_lib.escape(desc)}</p>"
                f'<span class="bbg-cta">See the countdown</span>'
                f"</div></a>"
            )
        if cards_html:
            hub_items_html += f'<div class="bbg-section"><p class="bbg-section-title">{section_label}</p><div class="bbg-grid">{cards_html}</div></div>\n'

    hub_hero = _page_hero(
        "Ranked. Refreshed monthly.",
        "Hot Board Games",
        "Every list on this page is ranked by a weighted score combining Amazon star ratings, review count, and current sales rank.",
        _crumbs(("Home", "index.html"), ("Hot Board Games", None)),
    )
    hub_content = f'{hub_hero}\n<div class="bbg-hub">{hub_items_html}</div>'
    _write_page("best-board-games.html", "Hot Board Games", "Ranked lists of the best board games by player count, genre, and all time.", hub_content, updated, active="hot")

    def _list_label(list_title: str) -> str:
        label = list_title.replace("Hottest ", "").replace(" Board Games", "").strip()
        return "Hot Right Now" if label in ("", "of All Time") else label

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
            safe_title = html_lib.escape(game["title"])
            thumb_src = _ranked_thumb_src(game)
            if thumb_src:
                img_html = f'<img src="{thumb_src}" alt="{safe_title}" loading="lazy">'
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
            blurb_html = f'<p class="ranked-blurb">{html_lib.escape(blurb)}</p>' if blurb else ""
            link = game.get("link", f'https://www.amazon.com/dp/{game["asin"]}?tag=carnivalgam06-20')

            items_html += f"""<li class="ranked-item reveal">
  <span class="ranked-num">#{rank_num}</span>
  <a href="{link}" rel="nofollow sponsored noopener" target="_blank">{img_wrap}</a>
  <div class="ranked-body">
    <h2 class="ranked-title"><a href="{link}" rel="nofollow sponsored noopener" target="_blank">{safe_title}</a></h2>
    <div class="ranked-meta">{meta_html}</div>
    {blurb_html}
    <a class="ranked-buy" href="{link}" rel="nofollow sponsored noopener" target="_blank">View on Amazon &rarr;</a>
  </div>
</li>"""

        hero = _page_hero(
            f"Ranked countdown &middot; {total} games",
            title,
            description,
            _crumbs(("Home", "index.html"), ("Hot Board Games", "best-board-games.html"), (_list_label(title), None)),
            note=f'Rankings last updated {cache.get("updated_at", "")[:10]} &middot; refreshed monthly &middot; scroll for #1',
        )
        pills = "".join(
            f'<a href="{other["slug"]}.html">{_list_label(other["title"])}</a>'
            for other_key, other in lists.items() if other_key != key
        )
        more_block = f'<div class="more-block"><p class="more-title">More hot lists</p><div class="more-pills">{pills}</div></div>'
        page_content = f'{hero}\n<ol class="ranked-list">{items_html}</ol>\n{more_block}'

        # ItemList structured data: best-first, matching the list's true ranking
        jsonld_items = []
        for pos, game in enumerate(games, start=1):
            entry: dict[str, Any] = {
                "@type": "ListItem",
                "position": pos,
                "name": game["title"],
                "url": game.get("link", ""),
            }
            if game.get("image_id"):
                entry["image"] = f"https://m.media-amazon.com/images/I/{game['image_id']}"
            jsonld_items.append(entry)
        jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": title,
            "description": description,
            "itemListElement": jsonld_items,
        }, ensure_ascii=False)

        _write_page(f"{slug}.html", title, description, page_content, updated, active="hot", jsonld=jsonld)


def _render_deal_cards(deal_list: list[dict[str, Any]]) -> str:
    return "\n".join(
        DEAL_CARD_TEMPLATE.render(
            deal=d, fresh=_deal_freshness(d.get("posted_at")),
            at_low=d.get("percent_above_low") == 0, bar=_price_bar(d),
        )
        for d in deal_list
    )


def _render_biggest_drops(deals: list[dict[str, Any]], updated: str) -> None:
    """A standalone, shareable page of the deepest current discounts -- ranked by
    how far below the 90-day average each has fallen. Targets 'biggest board game
    deals' searches and gives Reddit/social a single link worth sharing."""
    top = sorted((d for d in deals if d.get("percent_off")),
                 key=lambda d: -(d.get("percent_off") or 0))[:24]
    if not top:
        return
    hero = _page_hero(
        "Refreshed every few hours",
        "This Week's Biggest Board Game Price Drops",
        "The deepest verified discounts on the board right now, ranked by how far "
        "below their real 90-day average they've dropped — not off an inflated list price.",
        _crumbs(("Home", "index.html"), ("Biggest drops", None)),
    )
    content = f'{hero}\n<div class="deal-grid">{_render_deal_cards(top)}</div>'
    _write_page(
        "biggest-drops.html", "This Week's Biggest Board Game Price Drops",
        "The biggest verified board game discounts right now, ranked by how far below their 90-day average price they've fallen.",
        content, updated, active="deals", jsonld=_index_jsonld(top),
    )


# gift-guide framing: (rankings-list key, gift heading, blurb)
GIFT_SECTIONS = [
    ("family", "For families & mixed ages", "Crowd-pleasers that teach in minutes and pull in everyone from 8 to 80."),
    ("2p", "For couples & two players", "Games built for exactly two — date-night staples and head-to-head duels."),
    ("gateway", "For total beginners", "The best first 'real' board games: easy to learn, impossible to put down."),
    ("strategy", "For strategy lovers", "Meaty, decision-rich games for the person who takes game night seriously."),
    ("party", "For party crowds", "Loud, fast, and easy — games that work with a house full of people."),
    ("solo", "For solo players", "Genuinely great one-player games, not afterthought solo modes."),
]


def _render_gift_guide(deals: list[dict[str, Any]], updated: str) -> None:
    """Evergreen gift-guide landing page (spikes hard at the holidays): the right
    game for each kind of recipient, linking into the ranked lists, plus a few
    live deals as gift ideas. Every pick carries the 90-day-history promise."""
    if not RANKINGS_CACHE.exists():
        return
    lists = json.loads(RANKINGS_CACHE.read_text(encoding="utf-8")).get("lists", {})
    hero = _page_hero(
        "Gift guide",
        "Board Game Gift Guide",
        "The right board game for anyone on your list — every pick checked against 90 "
        "days of real Amazon price history, so a 'deal' is actually a deal.",
        _crumbs(("Home", "index.html"), ("Gift guide", None)),
    )
    cards = ""
    for key, heading, blurb in GIFT_SECTIONS:
        lst = lists.get(key)
        if not lst:
            continue
        thumbs = "".join(
            f'<img src="{_ranked_thumb_src(g)}" alt="" loading="lazy">'
            for g in lst.get("games", [])[:3] if g.get("image_id")
        )
        cards += (
            f'<a class="bbg-card reveal" href="{lst["slug"]}.html">'
            f'<div class="bbg-card-imgs">{thumbs}</div>'
            f'<div class="bbg-card-body"><span class="bbg-count">Gift pick</span>'
            f"<h3>{html_lib.escape(heading)}</h3><p>{html_lib.escape(blurb)}</p>"
            f'<span class="bbg-cta">See the picks</span></div></a>'
        )
    grid = f'<div class="bbg-section"><div class="bbg-grid">{cards}</div></div>' if cards else ""

    on_sale = sorted((d for d in deals if d.get("percent_off")),
                     key=lambda d: -(d.get("percent_off") or 0))[:6]
    sale = ""
    if on_sale:
        sale = ('<h2 class="section-heading" style="margin-top:2.5rem">On sale right now</h2>'
                f'<div class="deal-grid">{_render_deal_cards(on_sale)}</div>')
    content = f'{hero}\n<div class="bbg-hub">{grid}</div>\n{sale}'
    _write_page(
        "gift-guide.html", "Board Game Gift Guide",
        "The best board games to gift by recipient — families, couples, strategy fans, party crowds, and solo players — with prices verified against 90-day history.",
        content, updated, active="gifts",
    )


def _write_page(
    filename: str,
    title: str,
    description: str,
    content_html: str,
    updated: str,
    active: str = "",
    jsonld: str | None = None,
) -> None:
    canonical = BASE_URL + "/" + ("" if filename == "index.html" else filename)
    html = BASE_TEMPLATE.render(
        title=title,
        description=description,
        site_name=SITE_NAME,
        tagline=TAGLINE,
        disclosure=DISCLOSURE,
        content=content_html,
        updated=updated,
        active=active,
        canonical=canonical,
        base_url=BASE_URL,
        facebook_url=FACEBOOK_URL,
        instagram_url=INSTAGRAM_URL,
        pinterest_url=PINTEREST_URL,
        twitter_url=TWITTER_URL,
        year=datetime.now(timezone.utc).year,
        jsonld=jsonld,
        google_verification=GOOGLE_SITE_VERIFICATION,
        onelink_onetag=ONELINK_ONETAG,
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


if __name__ == "__main__":
    # Re-render the whole site from posted_log.json with the pipeline's config.
    # A real entry point so scripts can call `python src/render_site.py` instead
    # of an inline `python -c "..."` (Start-Process mangles multi-word -c args
    # on Windows, which silently broke the monthly rankings render).
    import yaml

    _cfg = yaml.safe_load((ROOT / "config" / "niche.yaml").read_text(encoding="utf-8"))
    _log = json.loads((ROOT / "posted_log.json").read_text(encoding="utf-8"))
    render_site(_log, max_listed=_cfg["posting"]["site_max_listed_deals"])
    print(f"Rendered {SITE_DIR} from {len(_log)} logged deals")
