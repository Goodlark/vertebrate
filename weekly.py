from __future__ import annotations

import logging
from typing import List, Optional

from pydantic import BaseModel

from config import WEEKLY_MAX_TOKENS, WEEKLY_MODEL

log = logging.getLogger("pressmonitor.weekly")

VOICE = (
    "Write in the register of a thoughtful New Yorker reporter: sophisticated but "
    "easy to read, observed, dry, with a point of view. Never press-release hype or "
    "hedging. Prefer one vivid, concrete image over three adjectives."
)

IMPORTANCE = (
    "Judge importance by substance, not press-release loudness: (a) a genuine "
    "technological leap (e.g. a 25-degrees-of-freedom robot hand), (b) a large amount "
    "of money (funding round, valuation, acquisition), (c) a large order or deployment "
    "of robots, or (d) a notable person changing jobs."
)

WEEKLY_SYSTEM = (
    "You write the weekly edition of an AI-and-robotics newspaper. You are given the "
    "week's stories, each with the companies and people involved. Produce three things:\n"
    "1. 'summary': ONE sentence naming the 2-3 most important developments of the week, "
    "with the company names in it. " + IMPORTANCE + "\n"
    "2. 'lede': 2-3 sentences framing the week.\n"
    "3. 'entries': for EACH story, a 'why it matters' explainer of 2-3 sentences — what "
    "changed, who it pressures, what to watch — keyed by its exact url.\n\n"
    "Voice: " + VOICE
)


class WhyEntry(BaseModel):
    url: str
    why: str


class WeeklyRollup(BaseModel):
    summary: str
    lede: str
    entries: List[WhyEntry]


def build_weekly_prompt(mentions: list) -> str:
    lines = ["This week's stories:\n"]
    for m in mentions:
        who = ", ".join(list(m.companies) + list(m.people)) or "—"
        lines.append(
            f"- url: {m.url}\n  headline: {m.title}\n  fact: {m.one_line}\n"
            f"  players: {who}\n  source: {m.source}\n  category: {m.category}"
        )
    lines.append("\nWrite the summary, the lede, and one why-it-matters per url above.")
    return "\n".join(lines)


def write_weekly(client, mentions: list, model: str = WEEKLY_MODEL) -> Optional[WeeklyRollup]:
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=WEEKLY_MAX_TOKENS,
            system=WEEKLY_SYSTEM,
            messages=[{"role": "user", "content": build_weekly_prompt(mentions)}],
            output_format=WeeklyRollup,
        )
        return resp.parsed_output
    except Exception as e:  # noqa: BLE001
        log.warning("weekly rollup failed: %s", e)
        return None


def apply_rollup(mentions: list, rollup: WeeklyRollup) -> None:
    why_by_url = {e.url: e.why for e in rollup.entries}
    for m in mentions:
        if m.url in why_by_url:
            m.why = why_by_url[m.url]
