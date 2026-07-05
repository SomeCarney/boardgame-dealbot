# Audience Growth Playbook

The bot finds and publishes deals automatically. It cannot manufacture an audience —
that takes a small amount of real human presence in places board gamers already gather.
This playbook is designed so that presence costs you **~30 minutes a week**.

**The one rule that protects everything:** never post an affiliate link where a community
bans them, and never pretend the site isn't yours. Getting banned from r/boardgamedeals
or BGG is permanent and unrecoverable; being a known, honest deal-poster is an asset that
compounds. When in doubt, post the clean link and skip the site plug.

---

## What's already automated (no action needed)

| Lever | Status |
|---|---|
| SEO: sitemap.xml, robots.txt, canonical URLs, meta descriptions | Regenerated every run |
| Structured data (Google rich results): Product/ItemList JSON-LD on the homepage and all 11 ranked lists | Regenerated every run |
| Social share cards (Open Graph + Twitter): branded card shows when anyone shares any page | Live (`og-image.png`) |
| RSS feed of current deals (`deals.xml`) | Regenerated every run |
| Instagram hashtags (10 discovery tags per post) | Automatic on every IG post |
| Facebook hashtags (3 per post) | Automatic on every FB post |
| **Post drafts**: `social_drafts.md` in the repo root is rewritten after every bot run with copy-paste-ready Reddit/BGG/FB/X text for the freshest deals | Automatic |
| **IndexNow pings**: every run notifies Bing/DuckDuckGo/Yandex that the homepage changed; the monthly rankings refresh resubmits every page | Automatic |

The ranked lists ("Hottest X Board Games") are the SEO engine: they target long-tail
searches like "best social deduction board games" and refresh monthly, which Google likes.
Give them 2-3 months to index and climb.

---

## The weekly routine (now driven by your phone)

**Deal posts — event-driven, no fixed days.** You no longer post on a schedule. The bot
watches every run and, whenever a genuinely good deal comes up, pushes your phone with the
post ready to go: tap **Open Reddit** (title + link pre-filled), hit Post, paste the comment.
Two kinds of push:
- **"Good deal to post"** (normal) — a solid deal; spaced to ~3-4/week so you're never
  posting to Reddit more than every other day (Reddit penalizes frequent self-posts).
- **"HOT DEAL — post now"** (urgent) — an exceptional deal (~once/week). Post it fast;
  being first is the biggest upvote multiplier.
- **Best-fit subreddit, automatically.** Each alert points you to the single best home for
  that game (instead of always r/boardgamedeals): **solo-only** games (designed for 1 player)
  → **r/soloboardgaming**; **2-player-only** games → **r/twoplayerboardgames**; everything
  else → **r/boardgamedeals**. The list is small on purpose — only subs that welcome deal
  posts. (Niche subs may want a "Sale"/"Deal" flair; pick it when you post.) To add another,
  first confirm the sub's rules allow price posts, then add it to `_SUB_PRESENTATION` /
  `choose_subreddit` in `src/daily_action.py`.

**Wednesday (auto-reminder, ~10 min):** your phone buzzes with a link to r/boardgames' daily
discussion. Answer 2-3 questions genuinely; link one of our guides/ranked lists ONLY when it
directly answers the question (e.g. "best games for 2 players?" → 3 titles in text, then
"fuller ranked list here if useful: [link]").

**Friday (auto-reminder, ~5 min):** your phone buzzes with a link to Instagram. Reply to every
comment, follow 10-15 accounts that recently posted under #boardgamedeals or #boardgamenight.

That's it. Consistency beats volume — a few great posts a week outperforms a burst of ten.

---

## Platform-by-platform

### Reddit (highest-intent audience, strictest rules)

- **r/boardgamedeals** — the core target. Deal posts are the entire point of the sub.
  - NO affiliate links. Ever. Post the clean Amazon URL (drafts file already strips the tag).
  - **The angle (this is the whole account):** the u/90-Day-Average persona. The "% off"
    a retailer shows is measured against an inflated list price you can't trust; the real
    signal is how far BELOW the 90-day average the price is. Every post makes that case.
  - Title format: `[Amazon] Game Name - $XX.XX (XX% below 90-day avg)`, with
    "— lowest in 90 days" appended when true. (If AutoMod ever rejects the title for not
    matching a `(XX% off)` pattern, fall back to `(XX% off)` and keep the angle in the
    comment — tell Claude and it's a one-line change.)
  - After posting, add the comment from the drafts file / desktop shortcut. Lead with the
    numbers, let the username carry the attitude — no one else verifies against 90-day
    history, and the data-first tone avoids the arguments a "retailers lie!" rant invites.
  - Put the site URL in your Reddit **profile bio**, not in posts (suggested: "I check
    board game deals against 90-day Amazon price history — no inflated 'list prices.'
    Full list: boardgameblackmarket.com"). People who trust your posts click through.
- **r/boardgames** — huge (millions of members), strict 10:1 self-promotion rule.
  - Participate in discussion threads as a hobbyist. Guides/lists only as answers to
    direct questions, at most 1 link per week.
- **r/soloboardgaming** — our "Hottest Solo Board Games" list is a genuinely good answer
  to their most-asked question. Same value-first rules.
- **Account hygiene:** the account is u/90-Day-Average (a branded persona is fine here —
  a consistent, honest deal-poster becomes a trusted fixture). Still build a little comment
  karma before hammering links: new accounts posting links on day one get auto-filtered.
  Spend the first week genuinely answering "is this a good price?" questions with price
  history — that IS the brand, and it seasons the account before the first deal post.

### BoardGameGeek

- The **Bargains** forum welcomes deal posts (clean links only — BGG bans referral links).
- Set the site URL in your BGG profile signature once.
- Later (optional): turn each monthly ranked-list refresh into a GeekList — BGG users love
  ranked lists and GeekLists get internal traffic for years.

### Facebook groups (biggest untapped channel for this niche)

- Search Facebook for "board game deals" and "board game bargains" groups; join the 3-4
  most active ones **with your personal profile** (groups often block Pages).
- Share genuinely good deals with the clean link. Where group rules allow pages, share the
  Page's post instead — that converts group members into Page followers.
- After a week of normal participation, most groups tolerate an occasional "I run a small
  deal-tracking site" mention. Ask a mod first; mods who say yes become allies.

### Instagram (the account we already post to 3x/day)

- Hashtags are now automatic. The remaining growth levers are manual:
  - Reply to every comment within a day (the algorithm heavily rewards this).
  - Follow/engage accounts in the niche (10-15/day max — more looks like a bot).
  - Once comfortable: convert the daily deal image into a 5-second Reel (static image +
    price-drop text animation). Reels reach non-followers; static posts mostly don't.
- Bio should say what followers get: "3 verified board game price drops a day. No fake sales."

### Pinterest (do when you have an hour — high ROI for this exact content)

Board game gift guides are a massive Pinterest category and our 11 ranked lists are
ready-made pin content. Requires a (free) business account signup — that's your part.
Once it exists, pin generation from the ranked lists can be automated in a future session.

### The RSS feed enables free syndication

`deals.xml` means services like IFTTT/Zapier (free tier) can auto-post every new deal to
an X/Twitter account with zero code. If you make an X account for the brand, say the word
and the automation gets built.

---

## What NOT to do

- No bought followers, engagement pods, or mass-DM anything — kills organic reach and
  risks the Meta accounts the whole pipeline depends on.
- No affiliate links on Reddit/BGG, even disguised through the site — mods check.
- No posting the same deal to many subreddits at once (crossposting spam is detectable).
- Don't argue with anyone about a deal's quality. "Fair point" and move on.

## How you'll know it's working (check monthly)

- **Amazon Associates dashboard:** clicks first, then orders. Clicks are the leading signal.
- **Reddit profile:** karma on deal posts trending up = the community trusts the account.
- **Facebook/Instagram insights:** follower count and reach per post.
- **Google Search Console** (free — the site is pre-wired for it, ~3 min of your part):
  1. Go to https://search.google.com/search-console and sign in with your Google account.
  2. Click "Add property" → choose **URL prefix** (NOT Domain) → enter
     `https://boardgameblackmarket.com/`
  3. On the verification screen pick **HTML tag** and copy the long `content="..."` value
     from the meta tag it shows you.
  4. Paste that value to Claude (or into `GOOGLE_SITE_VERIFICATION` in
     `src/render_site.py`, then re-render and push). It goes into every page head.
  5. Back in Search Console click **Verify**, then open **Sitemaps** in the left menu,
     type `sitemap.xml`, and click Submit.

  Once verified, Search Console shows which ranked lists get search impressions.
  The lists usually start showing impressions within 4-8 weeks.
- **Bing/DuckDuckGo/Yandex** need nothing from you — the bot submits pages to them
  automatically via IndexNow after every run.

Realistic arc: weeks 1-4 near zero, then deal posts start driving spikes of 50-300 visits,
and search traffic to the ranked lists compounds from month 2-3 onward. The 3-sales/180-day
Associates requirement is the first milestone — deal posts on r/boardgamedeals are the
most direct path to it.
