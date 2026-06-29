# boardgame-dealbot

Finds genuine Amazon price drops on board games and publishes them (with an
Amazon Associates tag) to a small static site, and optionally to a Telegram
channel. Runs on a GitHub Actions schedule -- no server to maintain.

Full design rationale lives in the project plan; this file is the practical
setup and operating guide.

## How it works

Every few hours, a GitHub Actions workflow runs `src/main.py`, which:
fetches current board-game deals from the Keepa API, filters out anything
that doesn't clear the bar in `config/niche.yaml`, drops anything already
posted before (`posted_log.json`), builds tagged Amazon links, regenerates
the static site in `docs/` (served by GitHub Pages -- the folder is named
`docs/` only because that's one of the two paths Pages allows, not because
it's documentation), optionally posts to Telegram, and commits the result
back to the repo.

## One-time setup (your part)

Do these in order -- each step unlocks the next:

1. **Push this repo to GitHub and enable Pages** (if not already done --
   see "Repo and Pages" below). You need a live site URL before step 3.
2. **Keepa**: sign up at [keepa.com](https://keepa.com) and subscribe to the
   lowest API tier (~$53/mo as of when this was built). Get your API key
   from the Keepa API settings page.
3. **Amazon Associates**: apply at
   [affiliate-program.amazon.com](https://affiliate-program.amazon.com),
   using this site's GitHub Pages URL as your "Site." Amazon requires the
   site to already have original content when you apply -- the 10 evergreen
   pages in `content/` are there for exactly this reason. After approval,
   grab your tracking tag (looks like `yourname-20`).
4. **Optional -- Telegram**: message [@BotFather](https://t.me/BotFather) to
   create a bot and get a token, then create a Telegram channel and add the
   bot as an admin. Get the channel's `@username` or numeric chat id.
5. **Optional -- custom domain**: point a domain at GitHub Pages if you want
   one; not required to start.

Send the values you collect (Keepa key, Amazon tag, Telegram token/channel
id) to whoever's wiring up the repo -- they go into **Settings > Secrets and
variables > Actions** on the GitHub repo, never into a committed file:

| Secret name | Required | From |
|---|---|---|
| `KEEPA_API_KEY` | yes | Keepa account |
| `AMAZON_ASSOCIATE_TAG` | yes | Amazon Associates, after approval |
| `TELEGRAM_BOT_TOKEN` | optional | @BotFather |
| `TELEGRAM_CHANNEL_ID` | optional | Your Telegram channel |

## Repo and Pages

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
`docs/` so you can open it locally, and skips Telegram and the dedupe log --
safe to run anytime, costs nothing, needs no credentials.

Once `KEEPA_API_KEY` and `AMAZON_ASSOCIATE_TAG` are set as real secrets, do
one manual run first: GitHub repo -> Actions -> "Find and post board game
deals" -> Run workflow. Check the result before trusting the schedule.

## Check-in checklist (this is the "passive" part)

**Weekly (a few minutes):**
- Skim the last few posts on the site/channel -- do they look like real,
  sensible deals?
- Check the Amazon Associates dashboard for clicks/sales.

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
