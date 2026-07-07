"""Generates per-deal post copy: a players/playtime/best-for summary block,
then a separated detailed description of what playing the game looks like.

Facts (player count, playtime, age) are extracted from the real Amazon
listing text already on the deal (title/description/features, from Keepa)
-- never invented. Anything not confidently found is simply omitted rather
than guessed. The detailed description uses Claude for a better-written
version, grounded in the same extracted facts so it can't state specifics
that weren't found: the logged-in Claude CLI is preferred (covered by
`claude /login`, no per-call billing), an ANTHROPIC_API_KEY is used if the
CLI isn't available, and a plain template is the final fallback.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
_DESC_MODEL = "claude-haiku-4-5-20251001"
_DESC_TIMEOUT_SECONDS = 90

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_WORD_TO_DIGIT_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)

_TITLE_SPLIT_RE = re.compile(r"\s*[,–—]\s*")
_BRAND_PREFIX_RE = re.compile(
    r"^(hasbro\s+(gaming\s+)?|mattel(?:\s+games?)?\s+|asmodee\s+|ravensburger\s+|"
    r"thames\s+(?:&|and)\s+kosmos\s+|z-man\s+games?\s+|days?\s+of\s+wonder\s+|"
    r"stonemaier\s+games?\s+|rio\s+grande\s+games?\s+|"
    r"fantasy\s+flight\s+games?\s+|wizards\s+of\s+the\s+coast\s+)",
    re.IGNORECASE,
)
_TRAILING_JUNK_RE = re.compile(
    r"(\s+(board|card|tabletop|party|strategy|family|cooperative)\s+game"
    r"|\s+the\s+game|\s+game"
    r"|\s+edition(\s+(game|set|pack))?"
    r"|\s+for\s+\d[\w\s]*?players?"
    r"|\s+\([^)]*\))"
    r"\s*$",
    re.IGNORECASE,
)

_PLAYERS_RANGE_RE = re.compile(r"(\d{1,2})\s*(?:to|-|–|—)\s*(\d{1,2})\+?\s*players?", re.IGNORECASE)
_PLAYERS_PLUS_RE = re.compile(r"(\d{1,2})\+\s*players?", re.IGNORECASE)
_PLAYERS_SINGLE_RE = re.compile(r"\bfor\s+(\d{1,2})\s*players?", re.IGNORECASE)

_PLAYTIME_RANGE_RE = re.compile(r"(\d{1,3})\s*(?:to|-|–|—)\s*(\d{1,3})\s*min", re.IGNORECASE)
_PLAYTIME_SINGLE_RE = re.compile(r"\b(\d{1,3})\s*min(?:ute)?s?\b", re.IGNORECASE)

_AGE_RE = re.compile(r"ages?\s*(\d{1,2})\s*\+", re.IGNORECASE)

_THEME_KEYWORDS = {
    "cooperative": ["cooperative", "co-op", "coop", "work together"],
    "strategy": ["strategy", "strategic", "tactical"],
    "party": ["party game", "hilarious", "laugh-out-loud"],
    "family": ["family", "kid-friendly", "all ages"],
    "deckbuilding": ["deck-building", "deck building", "deckbuilder"],
    "miniatures": ["miniatures", "minis"],
    "worker_placement": ["worker placement"],
    "card_game": ["card game"],
    "two_player": ["two-player", "2-player", "duel"],
}

_BEST_FOR_BY_THEME = {
    "cooperative": "players who'd rather team up against the game than against each other",
    "strategy": "players who enjoy planning a few moves ahead",
    "party": "bigger groups who want something loud and easy to pick up",
    "family": "mixed-age groups, including first-timers",
    "deckbuilding": "players who like optimizing a growing deck/engine",
    "miniatures": "collectors and players who enjoy tactile, detailed components",
    "worker_placement": "players who enjoy resource and turn-order puzzles",
    "card_game": "players who want something quick and portable",
    "two_player": "couples or duos looking for a dedicated two-player game",
}

_DETAIL_TEMPLATES = {
    "cooperative": "Players work together against the game itself, rather than competing with each other.",
    "strategy": "Expect meaningful decisions each turn that reward planning ahead.",
    "party": "Sessions are fast, social, and easy to jump into without much setup.",
    "family": "Rules are simple enough to teach in a few minutes to mixed-age groups.",
    "deckbuilding": "You'll build up a deck or engine over the course of the game that gets stronger each turn.",
    "miniatures": "Detailed physical components are a big part of the experience here.",
    "worker_placement": "Turns revolve around claiming limited spots before opponents do.",
    "card_game": "It's a card-driven game, easy to bring along and quick to set up.",
    "two_player": "It's built specifically around a head-to-head two-player experience.",
}


def _words_to_digits(text: str) -> str:
    return _WORD_TO_DIGIT_RE.sub(lambda m: str(_NUMBER_WORDS[m.group(0).lower()]), text)


def extract_facts(deal: dict[str, Any]) -> dict[str, Any]:
    raw_text = " ".join([deal.get("title", ""), deal.get("description", ""), " ".join(deal.get("features", []))])
    text = _words_to_digits(raw_text)
    facts: dict[str, Any] = {}

    m = _PLAYERS_RANGE_RE.search(text)
    if m:
        facts["min_players"], facts["max_players"] = int(m.group(1)), int(m.group(2))
    else:
        m = _PLAYERS_PLUS_RE.search(text)
        if m:
            facts["min_players"] = int(m.group(1))
        else:
            m = _PLAYERS_SINGLE_RE.search(text)
            if m:
                facts["min_players"] = facts["max_players"] = int(m.group(1))

    m = _PLAYTIME_RANGE_RE.search(text)
    if m:
        facts["min_minutes"], facts["max_minutes"] = int(m.group(1)), int(m.group(2))
    else:
        m = _PLAYTIME_SINGLE_RE.search(text)
        if m:
            facts["min_minutes"] = facts["max_minutes"] = int(m.group(1))

    m = _AGE_RE.search(text)
    if m:
        facts["min_age"] = int(m.group(1))

    lower_text = raw_text.lower()
    facts["themes"] = [theme for theme, keywords in _THEME_KEYWORDS.items() if any(k in lower_text for k in keywords)]

    return facts


def _players_line(facts: dict[str, Any]) -> str | None:
    lo, hi = facts.get("min_players"), facts.get("max_players")
    if lo is None and hi is None:
        return None
    if hi is None:
        return f"Players: {lo}+"  # "4+ players" listings set min only
    if lo is None:
        return f"Players: up to {hi}"
    if lo == hi:
        return f"Players: {lo}"
    return f"Players: {lo}-{hi}"


def _playtime_line(facts: dict[str, Any]) -> str | None:
    lo, hi = facts.get("min_minutes"), facts.get("max_minutes")
    if lo is None and hi is None:
        return None
    if hi is None:
        return f"Playtime: ~{lo}+ min"
    if lo is None:
        return f"Playtime: up to {hi} min"
    if lo == hi:
        return f"Playtime: ~{lo} min"
    return f"Playtime: ~{lo}-{hi} min"


def _best_for_line(facts: dict[str, Any]) -> str:
    for theme in facts.get("themes") or []:
        if theme in _BEST_FOR_BY_THEME:
            return f"Best for: {_BEST_FOR_BY_THEME[theme]}"
    if facts.get("min_players") == 2 and facts.get("max_players") == 2:
        return "Best for: two players looking for a dedicated head-to-head game"
    if facts.get("max_players", 0) >= 6:
        return "Best for: larger groups and game nights"
    return "Best for: general tabletop game fans"


def extract_short_title(full_title: str, brand: str | None = None) -> str:
    """The actual game name, not the Amazon listing title. Delegates to
    game_title.get_game_title, which verifies candidates against the
    BoardGameGeek database and falls back to heuristics. Never raises."""
    try:
        from game_title import get_game_title
        return get_game_title(full_title, brand)
    except Exception:
        # last-resort legacy heuristic -- a bad short title must never kill a run
        part = _TITLE_SPLIT_RE.split(full_title)[0].strip()
        part = _BRAND_PREFIX_RE.sub("", part).strip()
        for _ in range(3):
            cleaned = _TRAILING_JUNK_RE.sub("", part).strip()
            if cleaned == part:
                break
            part = cleaned
        return part or full_title.split(",")[0].strip()


def generate_description(deal: dict[str, Any]) -> dict[str, Any]:
    """Returns {"summary_lines": [...], "detailed": "...", "short_title": "...", "facts": {...}}."""
    facts = extract_facts(deal)
    summary_lines = []
    if deal.get("is_best_seller"):
        # a verified fact from Keepa's best-sellers list, not a marketing
        # flourish -- only ever set when the ASIN is actually on it
        summary_lines.append("\U0001f3c6 Category Best Seller")
    summary_lines.extend(line for line in (_players_line(facts), _playtime_line(facts)) if line)
    summary_lines.append(_best_for_line(facts))
    return {
        "summary_lines": summary_lines,
        "detailed": _generate_detailed(deal, facts),
        "short_title": extract_short_title(deal.get("title", ""), deal.get("brand")),
        "facts": facts,
    }


def _generate_detailed(deal: dict[str, Any], facts: dict[str, Any]) -> str:
    # Prefer the logged-in Claude CLI (no per-call API billing); fall back to
    # the API if a key is set, then to a plain template. Each generator returns
    # None when its backend isn't available, so the next one is tried.
    for gen in (_generate_detailed_cli, _generate_detailed_api):
        try:
            text = gen(deal, facts)
        except Exception:
            logger.exception("%s failed, trying next description backend", gen.__name__)
            text = None
        if text:
            return text
    return _generate_detailed_template(facts)


_REFUSAL_MARKERS = (
    "i don't have enough", "i do not have enough", "not enough information",
    "insufficient information", "there isn't enough", "there is not enough",
    "i cannot", "i can't ", "i'm unable", "i am unable", "as an ai",
    "known facts", "the listing text", "based on the information provided",
)


def _usable_description(text: str | None) -> str | None:
    """Reject model refusals / prompt-echoing / stubs so they fall through to
    the template instead of shipping to the site or a social post."""
    if not text:
        return None
    t = text.strip()
    low = t.lower()
    if len(t) < 40 or any(m in low for m in _REFUSAL_MARKERS):
        return None
    return t


def _description_prompt(deal: dict[str, Any], facts: dict[str, Any]) -> str:
    fact_lines = "\n".join(f"- {k}: {v}" for k, v in facts.items() if v) or "(none confidently extracted)"
    return (
        "Write a 2-3 sentence description of what playing this board game looks and feels like, "
        "for a social media post about a price deal. Be engaging but accurate -- do not invent "
        "specific facts (player counts, playtime, awards, etc.) beyond what's listed below. "
        "Reply with only the description text, no preamble.\n\n"
        f"Game title: {deal.get('title')}\n"
        f"Known facts:\n{fact_lines}\n\n"
        "Real product listing text, for context only (do not copy it verbatim):\n"
        f"{(deal.get('description') or '')[:800]}"
    )


def _generate_detailed_template(facts: dict[str, Any]) -> str:
    sentences = [_DETAIL_TEMPLATES[t] for t in (facts.get("themes") or []) if t in _DETAIL_TEMPLATES]
    if not sentences:
        sentences.append("A tabletop game with its own rules and pacing -- check the listing for full details.")
    return " ".join(sentences)


def _generate_detailed_cli(deal: dict[str, Any], facts: dict[str, Any]) -> str | None:
    """Headless Claude CLI (haiku). Returns None if the CLI isn't installed or
    isn't logged in, so the caller falls through to the API/template."""
    from game_title import _find_claude
    claude = _find_claude()
    if not claude:
        return None
    # Prompt on STDIN, not as a -p arg: the Windows `claude.cmd` shim truncates
    # a multi-line argument at the first newline (see game_title._llm_extract).
    result = subprocess.run(
        [claude, "-p", "--model", _DESC_MODEL],
        input=_description_prompt(deal, facts),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=_DESC_TIMEOUT_SECONDS, cwd=ROOT,
    )
    out = (result.stdout or "").strip()
    if result.returncode != 0 or "Not logged in" in out:
        return None
    return _usable_description(out)


def _generate_detailed_api(deal: dict[str, Any], facts: dict[str, Any]) -> str | None:
    """Anthropic API path -- only if ANTHROPIC_API_KEY is set (bills per call)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=_DESC_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": _description_prompt(deal, facts)}],
    )
    return _usable_description(response.content[0].text)
