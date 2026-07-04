"""Extracts the actual GAME NAME from an Amazon listing title.

Amazon titles are marketing soup ("Ravensburger That's Not A Hat - Fun
Bluffing & Memory Party Game for All Ages | ..."), and the deal cards must
show only the real game name ("That's Not a Hat"). Layers:

1. Primary: ask Claude (headless CLI, haiku model) to extract the game name.
   This is the only approach that reliably distinguishes publisher from game
   ("Spin Master Games, Jumanji Stampede, ..." -> "Jumanji Stampede") and it
   costs fractions of a cent per NEW listing. (BoardGameGeek's XML API would
   have been the alternative, but it now requires registered access.)
2. Fallback: publisher-stripping + separator-splitting heuristics, used when
   the CLI is unavailable (not installed / not logged in) or errors.

Results are cached in config/game_title_cache.json so each listing is
resolved once, ever. Heuristic-sourced entries are retried through Claude
after a few days (e.g. once `claude /login` has been run). All of this is
best-effort: title extraction can never break the pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess

from safewrite import atomic_write_text
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "config" / "game_title_cache.json"

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_TIMEOUT_SECONDS = 120
HEURISTIC_RETRY_DAYS = 3  # re-try Claude for heuristic-only cache entries

# Publishers/brands that appear as the first segment of Amazon listing titles.
# Used by the heuristic fallback only (Claude doesn't need the list). Matched
# exactly after normalization -- never as a suffix guess.
PUBLISHERS = {
    "hasbro", "hasbro gaming", "hasbro games", "mattel", "mattel games",
    "asmodee", "ravensburger", "thames & kosmos", "thames and kosmos",
    "z-man games", "zman games", "days of wonder", "stonemaier games",
    "rio grande games", "fantasy flight games", "wizards of the coast",
    "spin master", "spin master games", "avalon hill", "cmon", "iello",
    "czech games edition", "czech games", "repos production", "libellud",
    "plan b games", "next move games", "blue orange games", "gamewright",
    "pandasaurus games", "renegade game studios", "leder games",
    "cephalofair games", "greater than games", "indie boards and cards",
    "indie boards & cards", "bezier games", "grey fox games", "looney labs",
    "steve jackson games", "the op", "the op games", "usaopoly",
    "winning moves", "winning moves games", "university games", "pressman",
    "pressman toy", "buffalo games", "big potato", "big potato games",
    "skybound", "skybound games", "goliath", "goliath games",
    "north star games", "north star game studio", "arcane wonders",
    "atlas games", "catan studio", "cryptozoic", "cryptozoic entertainment",
    "eagle-gryphon games", "floodgate games", "gale force nine",
    "gamelyn games", "hachette boardgames", "kosmos", "lucky duck games",
    "matagot", "mindware", "osprey games", "peaceable kingdom",
    "portal games", "roxley", "roxley games", "stronghold games", "thinkfun",
    "van ryder games", "wizkids", "ares games", "capstone games",
    "chip theory games", "restoration games", "funko", "funko games",
    "ridley's", "ridleys", "professor puzzle", "melissa & doug",
    "melissa and doug", "orchard toys", "haba", "educational insights",
    "learning resources", "spinmaster", "late for the sky", "brass monkey",
    "hygge games", "relatable",
}

# Candidates that are pure marketing residue, never a game name.
JUNK_PHRASES = {
    "board game", "card game", "the game", "game", "games", "party game",
    "strategy game", "family game", "dice game", "board games", "the",
    "family board game", "strategy board game", "party board game",
}

_SEPARATOR_RE = re.compile(r"\s*(?:,|\||;|\s-\s|\s–\s|\s—\s)\s*")
_ORDINAL_EDITION_RE = re.compile(
    r"\b(\d+(?:st|nd|rd|th)|first|second|third|fourth|fifth)\s+edition\s*$", re.IGNORECASE
)
_TRAILING_JUNK_RE = re.compile(
    r"(\s+(board|card|tabletop|party|strategy|family|cooperative|dice|trivia)\s+games?"
    r"|\s+the\s+game"
    r"|\s+games?"
    r"|\s+\d{4,5}"
    r"|\s+(deluxe|standard|classic|premium)?\s*edition(\s+(game|set|pack))?"
    r"|\s+for\s+(kids|adults|families|teens)[\w\s&]*"
    r"|\s+ages?\s+\d+.*"
    r"|\s+\d{1,2}\s*(?:-|to|\+)\s*\d{0,2}\s*players?.*"
    r"|\s+\([^)]*\)"
    r"|\s*:\s*the"
    r")\s*$",
    re.IGNORECASE,
)


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_junk(s: str) -> str:
    for _ in range(4):
        if _ORDINAL_EDITION_RE.search(s):
            break  # "2nd Edition" is part of the name -- stop trimming
        cleaned = _TRAILING_JUNK_RE.sub("", s).strip(" ,;:-|")
        if cleaned == s:
            break
        s = cleaned
    return s


_JUNK_LEADS = ("board game", "card game", "party game", "strategy game",
               "family game", "dice game", "the game", "game ")


def _strip_brand(title: str, brand: str | None) -> str:
    t = title.strip()

    def cut(text: str, prefix_words: int) -> str | None:
        words = text.split()
        raw_remainder = " ".join(words[prefix_words:])
        remainder = raw_remainder.strip(" ,;:-|")
        first_seg = _SEPARATOR_RE.split(remainder)[0] if remainder else ""
        norm_seg = _normalize(first_seg)
        # refuse the cut if what's left is marketing residue, not a name
        if len(remainder) < 3 or norm_seg in JUNK_PHRASES or norm_seg.startswith(_JUNK_LEADS):
            return None
        return remainder

    if brand and len(brand) >= 3 and _normalize(t).startswith(_normalize(brand)):
        n = len(brand.split())
        words = t.split()
        prefix = " ".join(words[:n])
        after = " ".join(words[n:]).lstrip()
        # "Hunt A Killer: The Final Act" -- a series colon right after the brand
        # means the brand is part of the official title; keep it (known
        # publishers are still stripped by the list branch below)
        if not (after.startswith(":") or prefix.endswith(":")):
            r = cut(t, n)
            if r:
                t = r
    norm = _normalize(t)
    for pub in PUBLISHERS:
        if norm.startswith(pub + " "):
            r = cut(t, len(pub.split()))
            if r:
                t = r
            break
    return t


def heuristic_title(listing_title: str, brand: str | None = None) -> str:
    """Best-effort game name without any LLM -- the fallback path."""
    base = _strip_brand(re.sub(r"\s+", " ", listing_title).strip(), brand)
    segments = [s for s in _SEPARATOR_RE.split(base) if s]
    seg0 = segments[0] if segments else base

    # "Rio Grande Games: Beyond The Sun" -- publisher head before a colon
    if ":" in seg0:
        head, tail = seg0.split(":", 1)
        if _normalize(head) in PUBLISHERS and _normalize(tail.strip()) not in JUNK_PHRASES:
            seg0 = tail.strip()

    result = _strip_junk(seg0)
    # de-market mid-string leftovers: "Monopoly Board Game Boise" -> "Monopoly Boise"
    result = re.sub(r"\s+(board|card)\s+game\b", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s+", " ", result).strip(" ,;:-|")
    if _normalize(result) in JUNK_PHRASES or len(result) < 3:
        result = seg0.strip()
    return result or listing_title


# ── Claude CLI extraction ────────────────────────────────────────────────────

_EXTRACT_PROMPT = """Each numbered line below is an Amazon product listing title for a tabletop game.
For each, extract ONLY the actual name of the game as it would appear on the box:
- no publisher or brand name (unless the brand IS the game name, e.g. "Exploding Kittens")
- no marketing phrases, player counts, ages, "Board Game", "Party Game", etc.
- keep official subtitles and expansion names, formatted "Base Game: Expansion"
  (e.g. "Dominion: Prosperity"), and keep edition markers only when they are part
  of the official product identity (e.g. "Ticket to Ride: Europe" yes, random
  "Deluxe Edition" fluff no)
- accessories/non-games (dice sets, card sleeves): return the product's natural short name

Reply with STRICT JSON only -- an array of strings, one per input line, same order,
no commentary, no code fences.

{listings}"""


def _find_claude() -> str | None:
    for candidate in ("claude", str(Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd")):
        try:
            if subprocess.run([candidate, "--version"], capture_output=True, timeout=30).returncode == 0:
                return candidate
        except Exception:
            continue
    return None


def _llm_extract(listing_titles: list[str]) -> list[str] | None:
    """Asks Claude for the game names. Returns None on any failure."""
    claude = _find_claude()
    if not claude:
        return None
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(listing_titles, 1))
    try:
        result = subprocess.run(
            [claude, "-p", _EXTRACT_PROMPT.format(listings=numbered), "--model", CLAUDE_MODEL],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=CLAUDE_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL, cwd=ROOT,
        )
        out = (result.stdout or "").strip()
        if result.returncode != 0 or "Not logged in" in out or not out:
            logger.info("Claude CLI unavailable for title extraction (rc=%s)", result.returncode)
            return None
        start, end = out.find("["), out.rfind("]")
        if start == -1 or end == -1:
            return None
        names = json.loads(out[start:end + 1])
        if not isinstance(names, list) or len(names) != len(listing_titles):
            return None
        cleaned = [str(n).strip() for n in names]
        if any(not n or len(n) > 120 for n in cleaned):
            return None
        return cleaned
    except Exception:
        logger.warning("Claude title extraction failed", exc_info=True)
        return None


# ── cache + public API ───────────────────────────────────────────────────────

def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(CACHE_PATH, json.dumps(cache, indent=2, ensure_ascii=False))


def _cache_fresh(entry: dict) -> bool:
    if entry.get("source") == "llm":
        return True
    try:
        cached_at = datetime.fromisoformat(entry["ts"])
        return datetime.now(timezone.utc) - cached_at < timedelta(days=HEURISTIC_RETRY_DAYS)
    except (KeyError, ValueError):
        return False


def get_game_titles(listings: list[tuple[str, str | None]]) -> dict[str, str]:
    """Batch entry point: [(listing_title, brand), ...] -> {listing_title: game_name}.
    One Claude call for all uncached titles. Never raises."""
    cache = _load_cache()
    out: dict[str, str] = {}
    todo: list[tuple[str, str | None]] = []
    for title, brand in listings:
        if not title:
            continue
        entry = cache.get(title)
        if entry and _cache_fresh(entry):
            out[title] = entry["title"]
        else:
            todo.append((title, brand))

    if todo:
        names = _llm_extract([t for t, _ in todo])
        now = datetime.now(timezone.utc).isoformat()
        for i, (title, brand) in enumerate(todo):
            if names:
                out[title] = names[i]
                cache[title] = {"title": names[i], "source": "llm", "ts": now}
            else:
                out[title] = heuristic_title(title, brand)
                cache[title] = {"title": out[title], "source": "heuristic", "ts": now}
        try:
            _save_cache(cache)
        except OSError:
            logger.warning("could not write game title cache")
    return out


def get_game_title(listing_title: str, brand: str | None = None) -> str:
    """Single-title convenience wrapper. Never raises."""
    if not listing_title:
        return listing_title
    return get_game_titles([(listing_title, brand)]).get(listing_title, listing_title)
