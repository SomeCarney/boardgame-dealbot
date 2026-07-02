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

The ranked lists ("Hottest X Board Games") are the SEO engine: they target long-tail
searches like "best social deduction board games" and refresh monthly, which Google likes.
Give them 2-3 months to index and climb.

---

## The weekly 30-minute routine

**Mon / Wed / Fri (5 min each):** open `social_drafts.md`, pick the best deal, post it to
r/boardgamedeals (link post, clean URL). If it's a genuinely great deal (40%+ off a well-known
game), also drop it in the BGG Bargains forum.

**Any one day (10 min):** answer 2-3 questions in r/boardgames "Daily Discussion" or the
weekly recommendation thread. Answer genuinely first; link one of our guides or ranked lists
ONLY when it directly answers the question (e.g. someone asks "best games for 2 players?" →
answer with 3 titles in text, then "I keep a fuller ranked list here if useful: [link]").

**Any one day (5 min):** open Instagram, reply to every comment, follow 10-15 accounts that
posted under #boardgamedeals or #boardgamenight recently. A meaningful share of them follow back.

That's it. Consistency beats volume — one clean post 3x/week outperforms a burst of ten.

---

## Platform-by-platform

### Reddit (highest-intent audience, strictest rules)

- **r/boardgamedeals** — the core target. Deal posts are the entire point of the sub.
  - NO affiliate links. Ever. Post the clean Amazon URL (drafts file already strips the tag).
  - Title format: `[Amazon] Game Name - $XX.XX (XX% off)`.
  - After posting, add the comment from the drafts file (the "real price history" angle is
    our differentiator — no other poster verifies against 90-day history).
  - Put the site URL in your Reddit **profile bio**, not in posts. People who like your
    deal posts click through on their own.
- **r/boardgames** — huge (millions of members), strict 10:1 self-promotion rule.
  - Participate in discussion threads as a hobbyist. Guides/lists only as answers to
    direct questions, at most 1 link per week.
- **r/soloboardgaming** — our "Hottest Solo Board Games" list is a genuinely good answer
  to their most-asked question. Same value-first rules.
- **Account hygiene:** use a personal-feeling account, build a little comment karma in the
  first two weeks before the first link. New accounts posting links on day one get filtered.

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
- **Google Search Console** (worth setting up — free, 10 min, needs the GitHub Pages site
  verified): shows which ranked lists are getting search impressions. The lists usually
  start showing impressions within 4-8 weeks.

Realistic arc: weeks 1-4 near zero, then deal posts start driving spikes of 50-300 visits,
and search traffic to the ranked lists compounds from month 2-3 onward. The 3-sales/180-day
Associates requirement is the first milestone — deal posts on r/boardgamedeals are the
most direct path to it.
