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

# Shared spec for the copy-paste LinkedIn caption, reused by the weekly rollup and
# by the standalone backfill helper so both write it the same way.
LINKEDIN_SPEC = (
    "a ready-to-post LinkedIn caption, about 120-180 words, in a professional-but-lively "
    "register. Open with a one-line hook. Then 3-4 short lines, each beginning with '→ ' "
    "and naming a company and the concrete development. Close with one line pointing readers "
    "to the full edition (e.g. 'The full edition is on vertebrate.ai.'). End with a final "
    "line of 5-6 relevant hashtags (e.g. #Robotics #Humanoids #PhysicalAI #Driverless #AI). "
    "Plain text only: real line breaks between thoughts, no markdown, no raw URLs, at most "
    "one tasteful emoji."
)

WEEKLY_SYSTEM = (
    "You write the weekly edition of an AI-and-robotics newspaper. You are given the "
    "week's stories, each with the companies and people involved. Produce four things:\n"
    "1. 'summary': ONE sentence naming the 2-3 most important developments of the week, "
    "with the company names in it. " + IMPORTANCE + "\n"
    "2. 'lede': 2-3 sentences framing the week.\n"
    "3. 'entries': for EACH story, a 'why it matters' explainer of 2-3 sentences — what "
    "changed, who it pressures, what to watch — keyed by its exact url.\n"
    "4. 'linkedin': " + LINKEDIN_SPEC + "\n\n"
    "Voice: " + VOICE
)

LINKEDIN_SYSTEM = (
    "You write the LinkedIn caption that promotes the weekly edition of an AI-and-robotics "
    "newspaper. Given the week's summary, lede, and stories, produce " + LINKEDIN_SPEC +
    "\nVoice: " + VOICE
)


class WhyEntry(BaseModel):
    url: str
    why: str


class WeeklyRollup(BaseModel):
    summary: str
    lede: str
    linkedin: str
    entries: List[WhyEntry]


class LinkedInCaption(BaseModel):
    linkedin: str


def build_weekly_prompt(mentions: list) -> str:
    lines = ["This week's stories:\n"]
    for m in mentions:
        who = ", ".join(list(m.companies) + list(m.people)) or "—"
        lines.append(
            f"- url: {m.url}\n  headline: {m.title}\n  fact: {m.one_line}\n"
            f"  players: {who}\n  source: {m.source}\n  category: {m.category}"
        )
    lines.append("\nWrite the summary, the lede, the LinkedIn caption, and one "
                 "why-it-matters per url above.")
    return "\n".join(lines)


def build_linkedin_prompt(week_label: str, summary: str, lede: str, mentions: list) -> str:
    lines = [f"Week: {week_label}", f"Summary: {summary}", f"Lede: {lede}", "", "Stories:"]
    for m in mentions:
        who = ", ".join(list(m.companies) + list(m.people)) or "—"
        lines.append(f"- {m.title} — {m.one_line} (players: {who})")
    lines.append("\nWrite the LinkedIn caption.")
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


def write_linkedin(client, week_label: str, summary: str, lede: str, mentions: list,
                   model: str = WEEKLY_MODEL) -> Optional[str]:
    """Generate just the LinkedIn caption for a week that already has an editorial.

    Used to backfill weeks written before the caption existed; a live weekly run gets
    the caption in the same call as the rest of the rollup.
    """
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=1000,
            system=LINKEDIN_SYSTEM,
            messages=[{"role": "user",
                       "content": build_linkedin_prompt(week_label, summary, lede, mentions)}],
            output_format=LinkedInCaption,
        )
        return resp.parsed_output.linkedin
    except Exception as e:  # noqa: BLE001
        log.warning("linkedin caption failed: %s", e)
        return None


def apply_rollup(mentions: list, rollup: WeeklyRollup) -> None:
    why_by_url = {e.url: e.why for e in rollup.entries}
    for m in mentions:
        if m.url in why_by_url:
            m.why = why_by_url[m.url]
