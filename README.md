# boardgame-dealbot

Finds genuine Amazon price drops on board games and publishes them (with an
Amazon Associates tag) to a small static site. **Live and running** -- see
Status below.

Full design rationale lives in the project plan; this file is the practical
setup and operating guide.

## How it works

Every 4 hours, a Windows Scheduled Task on this PC (`BoardGameDealBot`) runs
`scripts/run_local.ps1`, which runs `src/main.py`:

1. Fetches current board-game deals from the Keepa API, filters out
   anything that doesn't clear the bar in `config/niche.yaml`, drops
   anything already posted before (`posted_log.json`).
2. For each new deal: extracts real facts (player count, playtime) from
   the actual Amazon listing text via regex (`src/describe.py`) -- never
   invented, omitted if not confidently found -- and writes a short
   description (template-based, or Claude-generated if `ANTHROPIC_API_KEY`
   is set, always grounded in the extracted facts so it can't state
   specifics that weren't actually found).
3. Composites a was/now price banner onto the product's real Amazon image
   (`src/image_compose.py`), saved into `docs/images/`.
4. Builds tagged Amazon links, regenerates the static site in `docs/`
   (served by GitHub Pages), and -- if Facebook or Instagram are
   configured -- pushes early so the composited images are publicly
   reachable before those platforms' APIs try to fetch them.
5. Posts to whichever of Telegram / Facebook / Instagram are configured
   (each no-ops cleanly if not set up), then commits + pushes everything.

It runs locally rather than on GitHub Actions' own schedule because **Keepa
rejects API requests from GitHub's datacenter IP ranges** (confirmed by
reproducing it twice) -- the same call succeeds from this PC's connection
every time. The GitHub Actions workflow still exists for manual runs
(`workflow_dispatch`) as a fallback in case that ever changes.

Product images come from Amazon's own listing images (via Keepa), not from
publisher/manufacturer websites -- those are someone else's copyrighted
marketing assets and reposting them would be infringement. Amazon's own
images are explicitly licensed for Associates to use in promotional content
on Facebook/Instagram, which is why this is the only image source used.

## Status

- [x] Repo + Pages: https://github.com/SomeCarney/boardgame-dealbot ,
      https://somecarney.github.io/boardgame-dealbot/
- [x] Keepa API subscription active (21 tokens/min)
- [x] Amazon Associates approved, tag `carnivalgam06-20` wired in
- [x] Windows Scheduled Task `BoardGameDealBot` registered, running every 4h
- [x] Fact extraction, description generation, and price-banner images live
- [ ] Telegram bot/channel -- optional, not set up
- [x] Facebook Page posting -- live and verified with real posts, capped at `facebook_max_posts_per_day` (3) best-ranked deals/day, see config/niche.yaml
- [x] Instagram posting -- live and verified with real posts, capped at `instagram_max_posts_per_day` (3) best-ranked deals/day. Working today via the developer app's own admin/tester access to this Instagram Business account, even without a completed Meta App Review (that review is only needed to post to *other* people's accounts at scale) -- see below
- [ ] Claude-generated descriptions -- optional upgrade, see below

Real credentials live in a local `.env` file (gitignored, never committed)
for local runs, and as GitHub Actions secrets for the manual-fallback path:

| Secret/env name | Where it lives | From |
|---|---|---|
| `KEEPA_API_KEY` | `.env` + GH secret | Keepa account |
| `AMAZON_ASSOCIATE_TAG` | `.env` + GH secret | Amazon Associates |
| `TELEGRAM_BOT_TOKEN` | not set (optional) | @BotFather |
| `TELEGRAM_CHANNEL_ID` | not set (optional) | Your Telegram channel |
| `FACEBOOK_PAGE_ID` | `.env` | Your Facebook Page |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | `.env` (non-expiring, derived Page token) | Meta for Developers app |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | `.env` | Linked IG Business account |
| `INSTAGRAM_ACCESS_TOKEN` | `.env` (long-lived user token) | Meta for Developers app |
| `ANTHROPIC_API_KEY` | not set (optional) | console.anthropic.com |

## Setting up Facebook and Instagram posting

**Facebook (achievable without a lengthy review process, since you're
posting to your own Page):**
1. Create a Facebook Page for the store, if you haven't already.
2. Go to [developers.facebook.com](https://developers.facebook.com), create
   a Meta app (type: Business).
3. Add the Page as an asset of the app. In Graph API Explorer (or via the
   app's settings), generate a Page access token with `pages_manage_posts`
   and `pages_read_engagement`. As the Page's admin using your own app in
   development mode, this typically works without full App Review.
4. Exchange it for a long-lived token (Meta's docs walk through this --
   "Page tokens never expire" when derived from a long-lived user token).
5. Send me the Page ID and that access token.

**Instagram (same app, but with a real catch):**
1. The Instagram account has to be a Business or Creator account, linked to
   the same Facebook Page. (Done -- `@boardgameblackmarket` is linked.)
2. In the same Meta app, request `instagram_basic` and
   `instagram_content_publish`. (Done -- granted to a long-lived user token
   in `.env` as `INSTAGRAM_ACCESS_TOKEN`, separate from the Facebook Page
   token.)
3. `instagram_content_publish` formally requires Meta App Review before an
   app can post to *other* people's Instagram accounts at scale -- but as
   the app's own developer/admin posting to your own linked account, it
   works today without waiting on that review (confirmed with real posts).
   Worth submitting for review eventually for long-term robustness, but not
   blocking current operation.

## Optional: better-written descriptions via Claude

Without `ANTHROPIC_API_KEY` set, descriptions are template-based (serviceable,
a bit formulaic). With it set, `src/describe.py` calls Claude (Haiku) to
write a genuinely original 2-3 sentence description instead, still grounded
in only the facts actually extracted from the real listing (it's explicitly
told not to invent specifics). Get a key at
[console.anthropic.com](https://console.anthropic.com), send it over, and
it'll be used automatically on the next run -- no code changes needed.

## Repo and Pages (already done -- reference only)

This repo was already created, pushed, and pointed at GitHub Pages using the
commands below. Nothing here needs to be re-run; it's documented in case the
repo ever needs to be recreated from scratch.

```
gh repo create boardgame-dealbot --public --source=. --remote=origin --push
gh api -X POST /repos/<owner>/boardgame-dealbot/pages -f "source[branch]=main" -f "source[path]=/docs"
```

Pages must be public on GitHub's free tier (private-repo Pages needs a paid
GitHub plan) -- the deals site is public-facing by design anyway, and the
secrets above are encrypted regardless of repo visibility.

## Running locally

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt          # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

set DRY_RUN=1                                           # Windows (cmd)
$env:DRY_RUN = "1"                                       # Windows (PowerShell)
export DRY_RUN=1                                          # macOS/Linux
.venv\Scripts\python.exe src\main.py
```

`DRY_RUN=1` uses fixture deals and a placeholder affiliate tag, rebuilds
`docs/` so you can open it locally, and skips the dedupe log -- safe to run
anytime, costs nothing, needs no credentials.

To run the real pipeline by hand (outside the schedule): `scripts\run_local.ps1`
runs it for real and pushes the result, same as the scheduled task does.

## Managing the scheduled task

```powershell
Get-ScheduledTaskInfo -TaskName "BoardGameDealBot"   # last/next run time, last result
Start-ScheduledTask -TaskName "BoardGameDealBot"      # force a run right now
Disable-ScheduledTask -TaskName "BoardGameDealBot"    # pause it
```

Run history (including errors) is in `logs\run_local.log` -- check there
first if a weekly glance at the site looks stale.

## Growing the audience

See `marketing/GROWTH_PLAYBOOK.md` for the full strategy (~30 min/week).
The short version: after every run the bot rewrites `social_drafts.md`
(local-only, gitignored) with copy-paste-ready posts for r/boardgamedeals,
the BGG Bargains forum, Facebook groups, and X -- with clean non-affiliate
links where community rules require them. SEO (sitemap, structured data,
share cards), an RSS feed (`docs/deals.xml`), and social hashtags are all
automatic.

## Check-in checklist (this is the "passive" part)

**Weekly (a few minutes):**
- Skim the last few posts on the site -- do they look like real, sensible
  deals?
- Open `social_drafts.md` and post the best deal to r/boardgamedeals
  (see the growth playbook for the rules that keep the account safe).
- Check the Amazon Associates dashboard for clicks/sales.
- If the site looks stale, check `logs\run_local.log` and that this PC has
  been on/connected -- the schedule only runs while it is.

**Monthly:**
- Check Keepa token usage isn't maxed out or wildly under-used.
- For the first 6 months: track progress toward 3 qualifying sales --
  Amazon can close an Associates account that doesn't get there within 180
  days of approval. Some manual sharing in board-game communities early on
  is genuinely what gets you those first few sales; the bot finds and posts
  deals, it doesn't build an audience by itself.

## Changing the niche later

Everything niche-specific lives in `config/niche.yaml`
(`category_search_term` and the filter thresholds). Pet supplies, baby gear,
and home goods all carry the same ~3% Amazon commission rate, so swapping is
a config edit, not a rebuild. Delete `config/category_cache.json` after
changing `category_search_term` so it re-resolves the new category.

## Honest expectations

This is a slow-compounding asset, not a guaranteed income source. Realistic
early outcome is $0 for the first several weeks/months until there's an
audience. No fake engagement, bought followers, or spam -- those risk
account bans and would undermine the whole thing.
