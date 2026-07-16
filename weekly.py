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

WEEKLY_SYSTEM = (
    "You write the weekly edition of an AI-and-robotics newspaper. You are given the "
    "week's mentions. Produce (1) an editor's-note 'lede' of 2-3 sentences framing the "
    "week, and (2) for each mention, a 'why it matters' explainer of 2-3 sentences — what "
    "changed, who it pressures, what to watch. Return one entry per mention, keyed by its "
    "exact url.\n\n"
    "Voice: " + VOICE
)


class WhyEntry(BaseModel):
    url: str
    why: str


class WeeklyRollup(BaseModel):
    lede: str
    entries: List[WhyEntry]


def build_weekly_prompt(mentions: list) -> str:
    lines = ["This week's mentions:\n"]
    for m in mentions:
        lines.append(
            f"- url: {m.url}\n  headline: {m.title}\n  source: {m.source}\n"
            f"  topic: {m.topic}\n  category: {m.category}\n  note: {m.one_line}"
        )
    lines.append("\nWrite the lede and one why-it-matters per url above.")
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
