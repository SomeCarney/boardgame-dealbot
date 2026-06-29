"""Generates per-deal post copy: a players/playtime/best-for summary block,
then a separated detailed description of what playing the game looks like.

Facts (player count, playtime, age) are extracted from the real Amazon
listing text already on the deal (title/description/features, from Keepa)
-- never invented. Anything not confidently found is simply omitted rather
than guessed. The detailed description is template-based by default; set
ANTHROPIC_API_KEY to use Claude for a better-written version, grounded in
the same extracted facts so it can't state specifics that weren't found.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_WORD_TO_DIGIT_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)

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
    if "min_players" not in facts:
        return None
    if facts["min_players"] == facts.get("max_players"):
        return f"Players: {facts['min_players']}"
    return f"Players: {facts['min_players']}-{facts['max_players']}"


def _playtime_line(facts: dict[str, Any]) -> str | None:
    if "min_minutes" not in facts:
        return None
    if facts["min_minutes"] == facts.get("max_minutes"):
        return f"Playtime: ~{facts['min_minutes']} min"
    return f"Playtime: ~{facts['min_minutes']}-{facts['max_minutes']} min"


def _best_for_line(facts: dict[str, Any]) -> str:
    for theme in facts.get("themes") or []:
        if theme in _BEST_FOR_BY_THEME:
            return f"Best for: {_BEST_FOR_BY_THEME[theme]}"
    if facts.get("min_players") == 2 and facts.get("max_players") == 2:
        return "Best for: two players looking for a dedicated head-to-head game"
    if facts.get("max_players", 0) >= 6:
        return "Best for: larger groups and game nights"
    return "Best for: general tabletop game fans"


def generate_description(deal: dict[str, Any]) -> dict[str, Any]:
    """Returns {"summary_lines": [...], "detailed": "...", "facts": {...}}."""
    facts = extract_facts(deal)
    summary_lines = [line for line in (_players_line(facts), _playtime_line(facts)) if line]
    summary_lines.append(_best_for_line(facts))
    return {
        "summary_lines": summary_lines,
        "detailed": _generate_detailed(deal, facts),
        "facts": facts,
    }


def _generate_detailed(deal: dict[str, Any], facts: dict[str, Any]) -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _generate_detailed_claude(deal, facts)
        except Exception:
            logger.exception("Claude description generation failed, falling back to template")
    return _generate_detailed_template(facts)


def _generate_detailed_template(facts: dict[str, Any]) -> str:
    sentences = [_DETAIL_TEMPLATES[t] for t in (facts.get("themes") or []) if t in _DETAIL_TEMPLATES]
    if not sentences:
        sentences.append("A tabletop game with its own rules and pacing -- check the listing for full details.")
    return " ".join(sentences)


def _generate_detailed_claude(deal: dict[str, Any], facts: dict[str, Any]) -> str:
    import anthropic

    client = anthropic.Anthropic()
    fact_lines = "\n".join(f"- {k}: {v}" for k, v in facts.items() if v) or "(none confidently extracted)"
    prompt = (
        "Write a 2-3 sentence description of what playing this board game looks and feels like, "
        "for a social media post about a price deal. Be engaging but accurate -- do not invent "
        "specific facts (player counts, playtime, awards, etc.) beyond what's listed below.\n\n"
        f"Game title: {deal.get('title')}\n"
        f"Known facts:\n{fact_lines}\n\n"
        "Real product listing text, for context only (do not copy it verbatim):\n"
        f"{(deal.get('description') or '')[:800]}"
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
