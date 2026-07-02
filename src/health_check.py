"""Post-run health check: verifies the run actually delivered, fixes what it
can automatically, and escalates to Devon only when it can't.

Runs at the end of every scheduled run (see scripts/run_local.ps1). Three jobs:

1. RETRY failed social posts.  The posting modules record permanent failures
   to logs/social_failures.json; by the time this runs, CDN propagation has
   settled, so one more attempt (with a cache-buster) usually lands. Entries
   that keep failing trigger a notification instead of silent loss.

2. VERIFY the live site actually shows the newest deal (GitHub Pages deploys
   can fail silently). If a push happened this run, poll the live homepage
   for the newest ASIN; if it never appears, re-render + push once, then
   alert if still stale.

3. AUTO-FIX pipeline crashes.  If the run exited non-zero, invoke Claude Code
   headless to diagnose the traceback, implement a minimal fix, commit, and
   push -- then re-run the pipeline once. A state file guards against
   re-attempting the same failure signature in a loop; repeat failures
   escalate to Devon via notification.

Usage (from run_local.ps1):
    python src/health_check.py --exit-code 0 --pushed 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s health_check: %(message)s")
logger = logging.getLogger("health_check")

BASE_URL = "https://somecarney.github.io/boardgame-dealbot"
LOG_PATH = ROOT / "logs" / "run_local.log"
FAILURES_PATH = ROOT / "logs" / "social_failures.json"
AUTOFIX_STATE_PATH = ROOT / "logs" / "autofix_state.json"
POSTED_LOG = ROOT / "posted_log.json"
NOTIFY_PS1 = ROOT / "scripts" / "notify.ps1"

MAX_HC_RETRIES = 2          # health-check retries per failed post before alerting
SITE_POLL_ATTEMPTS = 8      # x 30s = up to 4 min for GitHub Pages to deploy
AUTOFIX_COOLDOWN_HOURS = 24 # never re-attempt the same failure signature sooner
CLAUDE_TIMEOUT_SECONDS = 1500


def notify(title: str, message: str, priority: str = "high") -> None:
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(NOTIFY_PS1),
             "-Title", title, "-Message", message, "-Priority", priority],
            timeout=60, capture_output=True,
        )
    except Exception:
        logger.exception("notification failed")


# ── 1. retry failed social posts ────────────────────────────────────────────

def retry_social_failures() -> None:
    if not FAILURES_PATH.exists():
        return
    entries = json.loads(FAILURES_PATH.read_text(encoding="utf-8"))
    if not entries:
        return

    posted = {d["asin"]: d for d in json.loads(POSTED_LOG.read_text(encoding="utf-8"))}
    import facebook_post
    import instagram_post

    remaining, gave_up = [], []
    for entry in entries:
        deal = posted.get(entry["asin"])
        if not deal:
            continue  # unknown asin -- drop
        # cache-buster distinct from the in-module ones
        attempt_deal = dict(deal)
        attempt_deal["image_url"] = f"{deal['image_url']}?hc={int(time.time())}"
        try:
            if entry["platform"] == "facebook":
                facebook_post._post_one(attempt_deal, os.environ.get("FACEBOOK_PAGE_ID"),
                                        os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN"))
            else:
                instagram_post._post_one(attempt_deal, os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
                                         os.environ.get("INSTAGRAM_ACCESS_TOKEN"))
            logger.info("recovered %s post for %s", entry["platform"], entry["asin"])
        except Exception as exc:
            entry["hc_retries"] = entry.get("hc_retries", 0) + 1
            entry["error"] = str(exc)[:300]
            if entry["hc_retries"] >= MAX_HC_RETRIES:
                gave_up.append(entry)
            else:
                remaining.append(entry)

    FAILURES_PATH.write_text(json.dumps(remaining, indent=2), encoding="utf-8")
    if gave_up:
        lines = ", ".join(f"{e['asin']} ({e['platform']})" for e in gave_up)
        notify("Deal bot: social posts need attention",
               f"Could not post after multiple retries: {lines}. "
               f"Last error: {gave_up[0]['error'][:120]}. If this mentions an "
               "expired/invalid token, the Meta access token needs renewing.")


# ── 2. verify the live site updated ─────────────────────────────────────────

def verify_site_fresh(pushed: bool) -> None:
    if not pushed:
        return
    posted = json.loads(POSTED_LOG.read_text(encoding="utf-8"))
    if not posted:
        return
    newest = max(posted, key=lambda d: d.get("posted_at") or "")
    asin = newest["asin"]

    for attempt in range(SITE_POLL_ATTEMPTS):
        try:
            body = requests.get(f"{BASE_URL}/?hc={int(time.time())}", timeout=20).text
            if asin in body:
                logger.info("live site shows newest deal %s", asin)
                return
        except requests.RequestException:
            pass
        time.sleep(30)

    logger.warning("live site does not show %s -- attempting re-push", asin)
    try:
        subprocess.run(["git", "push"], cwd=ROOT, timeout=120, capture_output=True)
        time.sleep(90)
        body = requests.get(f"{BASE_URL}/?hc2={int(time.time())}", timeout=20).text
        if asin in body:
            logger.info("site recovered after re-push")
            return
    except Exception:
        pass
    notify("Deal bot: site may be stale",
           f"The live site is not showing the newest deal ({asin}) several minutes "
           "after the push. GitHub Pages may be having deploy trouble -- check "
           "https://github.com/SomeCarney/boardgame-dealbot/actions and the site.")


# ── 3. auto-fix pipeline crashes via headless Claude ────────────────────────

def _last_traceback_signature() -> tuple[str, str]:
    """Returns (signature_hash, traceback_text) for the newest traceback in the log."""
    if not LOG_PATH.exists():
        return "", ""
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace")[-20000:]
    blocks = re.findall(r"Traceback \(most recent call last\):.*?(?:\n\S[^\n]*Error[^\n]*)", text, re.DOTALL)
    if not blocks:
        return hashlib.sha256(text[-2000:].encode()).hexdigest()[:16], text[-2000:]
    tb = blocks[-1]
    # signature = exception line + raising location, stable across timestamps
    sig_material = "\n".join(line for line in tb.splitlines() if line.startswith('  File') or "Error" in line)
    return hashlib.sha256(sig_material.encode()).hexdigest()[:16], tb


def _find_claude() -> str | None:
    for candidate in ("claude", str(Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd")):
        try:
            result = subprocess.run([candidate, "--version"], capture_output=True, timeout=30)
            if result.returncode == 0:
                return candidate
        except Exception:
            continue
    return None


AUTOFIX_PROMPT = """The boardgame-dealbot scheduled pipeline (src/main.py) is failing. You are running
unattended -- fix it so the next scheduled run succeeds.

The most recent failure traceback:

{traceback}

Steps:
1. Read the relevant source files and find the root cause.
2. Implement the smallest correct fix. Prefer making code defensive over changing behavior.
3. Verify: run `.venv\\Scripts\\python.exe src\\main.py` with environment variable DRY_RUN=1
   and confirm it exits 0.
4. Commit ONLY the specific files you changed (never `git add -A`, never touch or commit
   `.env` or anything containing secrets) using:
   git -c user.name="boardgame-dealbot" -c user.email="actions@users.noreply.github.com" commit
   with a message explaining the root cause. Then `git push`.
5. If you cannot find a safe fix, make NO changes and end your reply with the line
   AUTOFIX_FAILED: <one-line reason>

Rules: stay inside this repository. Do not modify scheduled tasks, credentials, or
config/niche.yaml thresholds. Do not post to social media yourself -- the caller
re-runs the pipeline after you finish."""


def autofix(exit_code: int) -> None:
    sig, tb = _last_traceback_signature()
    state = {}
    if AUTOFIX_STATE_PATH.exists():
        state = json.loads(AUTOFIX_STATE_PATH.read_text(encoding="utf-8"))

    if state.get("signature") == sig:
        attempted = datetime.fromisoformat(state["attempted_at"])
        if datetime.now(timezone.utc) - attempted < timedelta(hours=AUTOFIX_COOLDOWN_HOURS):
            if not state.get("alerted"):
                notify("Deal bot: still failing after auto-fix",
                       "The pipeline is failing with the same error the auto-fixer already "
                       "attempted to solve. Manual attention needed -- open Claude Code in "
                       "C:\\Claude\\boardgame-dealbot and say 'the bot is failing, fix it'.",
                       priority="urgent")
                state["alerted"] = True
                AUTOFIX_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
            return

    claude = _find_claude()
    if not claude:
        notify("Deal bot: run failed (exit {})".format(exit_code),
               "The pipeline crashed and the Claude CLI is not available for auto-fix. "
               "Open Claude Code in C:\\Claude\\boardgame-dealbot and say 'the bot is failing, fix it'.",
               priority="urgent")
        return

    AUTOFIX_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTOFIX_STATE_PATH.write_text(json.dumps({
        "signature": sig,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "alerted": False,
    }, indent=2), encoding="utf-8")

    logger.info("invoking Claude Code headless for auto-fix (signature %s)", sig)
    try:
        result = subprocess.run(
            [claude, "-p", AUTOFIX_PROMPT.format(traceback=tb[-4000:]),
             "--dangerously-skip-permissions"],
            cwd=ROOT, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
        output = (result.stdout or "") + (result.stderr or "")
        logger.info("claude auto-fix finished (rc=%s), output tail: %s", result.returncode, output[-500:])
        if "Not logged in" in output or "/login" in output:
            notify("Deal bot: auto-fix needs one-time setup",
                   "The pipeline crashed and the auto-fixer can't run because the Claude "
                   "CLI isn't logged in. One-time fix: open a terminal, run 'claude /login', "
                   "sign in, done. Then the bot can repair itself. For now, open Claude Code "
                   "in C:\\Claude\\boardgame-dealbot and say 'the bot is failing, fix it'.",
                   priority="urgent")
            return
        if "AUTOFIX_FAILED" in output:
            notify("Deal bot: auto-fix could not solve it",
                   "Claude examined the failure but declined to change code: "
                   + output.split("AUTOFIX_FAILED:", 1)[-1].strip()[:200],
                   priority="urgent")
            return
    except subprocess.TimeoutExpired:
        notify("Deal bot: auto-fix timed out",
               "The automatic fix attempt ran too long and was stopped. Manual attention needed.",
               priority="urgent")
        return
    except Exception as exc:
        notify("Deal bot: auto-fix errored", f"Auto-fix could not run: {str(exc)[:200]}", priority="urgent")
        return

    # Re-run the pipeline once to recover this run's deals
    logger.info("re-running pipeline after auto-fix")
    rerun = subprocess.run(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), "src/main.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=1800,
    )
    if rerun.returncode == 0:
        notify("Deal bot: self-healed", "The pipeline crashed, was automatically diagnosed and "
               "fixed, and the recovery run succeeded. Details in the git log and logs/run_local.log.",
               priority="default")
        # push whatever the recovery run produced
        subprocess.run(["git", "add", "docs/", "posted_log.json", "config/category_cache.json"], cwd=ROOT, capture_output=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
        if diff.returncode != 0:
            subprocess.run(["git", "-c", "user.name=boardgame-dealbot",
                            "-c", "user.email=actions@users.noreply.github.com",
                            "commit", "-q", "-m", "Recovery run after auto-fix"], cwd=ROOT, capture_output=True)
            subprocess.run(["git", "push"], cwd=ROOT, capture_output=True)
    else:
        notify("Deal bot: auto-fix did not stick",
               "A fix was attempted but the recovery run still failed. Open Claude Code in "
               "C:\\Claude\\boardgame-dealbot and say 'the bot is failing, fix it'.",
               priority="urgent")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--pushed", type=int, default=0)
    args = parser.parse_args()

    try:
        retry_social_failures()
    except Exception:
        logger.exception("social retry step failed")

    try:
        verify_site_fresh(bool(args.pushed))
    except Exception:
        logger.exception("site freshness step failed")

    if args.exit_code != 0:
        try:
            autofix(args.exit_code)
        except Exception:
            logger.exception("autofix step failed")
            notify("Deal bot: run failed", "The pipeline crashed and the auto-fixer also hit an "
                   "error. Manual attention needed.", priority="urgent")

    logger.info("health check complete")


if __name__ == "__main__":
    main()
