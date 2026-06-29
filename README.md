# boardgame-dealbot

Finds genuine Amazon price drops on board games and publishes them (with an
Amazon Associates tag) to a small static site. **Live and running** -- see
Status below.

Full design rationale lives in the project plan; this file is the practical
setup and operating guide.

## How it works

Every 4 hours, a Windows Scheduled Task on this PC (`BoardGameDealBot`) runs
`scripts/run_local.ps1`, which runs `src/main.py`: fetches current
board-game deals from the Keepa API, filters out anything that doesn't
clear the bar in `config/niche.yaml`, drops anything already posted before
(`posted_log.json`), builds tagged Amazon links, regenerates the static
site in `docs/` (served by GitHub Pages -- the folder is named `docs/`
only because that's one of the two paths Pages allows, not because it's
documentation), and commits + pushes the result.

It runs locally rather than on GitHub Actions' own schedule because **Keepa
rejects API requests from GitHub's datacenter IP ranges** (confirmed by
reproducing it twice) -- the same call succeeds from this PC's connection
every time. The GitHub Actions workflow still exists for manual runs
(`workflow_dispatch`) as a fallback in case that ever changes.

## Status -- fully live

- [x] Repo + Pages: https://github.com/SomeCarney/boardgame-dealbot ,
      https://somecarney.github.io/boardgame-dealbot/
- [x] Keepa API subscription active (21 tokens/min)
- [x] Amazon Associates approved, tag `carnivalgam06-20` wired in
- [x] Windows Scheduled Task `BoardGameDealBot` registered, running every 4h
- [ ] Optional, not set up: Telegram bot/channel (secondary push feed)

Real credentials live in a local `.env` file (gitignored, never committed)
for local runs, and as GitHub Actions secrets for the manual-fallback path:

| Secret/env name | Where it lives | From |
|---|---|---|
| `KEEPA_API_KEY` | `.env` + GH secret | Keepa account |
| `AMAZON_ASSOCIATE_TAG` | `.env` + GH secret | Amazon Associates |
| `TELEGRAM_BOT_TOKEN` | not set (optional) | @BotFather |
| `TELEGRAM_CHANNEL_ID` | not set (optional) | Your Telegram channel |

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

## Check-in checklist (this is the "passive" part)

**Weekly (a few minutes):**
- Skim the last few posts on the site -- do they look like real, sensible
  deals?
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
