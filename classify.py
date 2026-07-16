from __future__ import annotations

import logging
from typing import List, Literal, Optional

from pydantic import BaseModel

from config import CLASSIFY_MAX_TOKENS, CLASSIFY_MODEL
from feeds import Article

log = logging.getLogger("pressmonitor.classify")

VOICE = (
    "Write in the register of a thoughtful New Yorker reporter: sophisticated but "
    "easy to read, observed, dry, with a point of view. Never press-release hype or "
    "hedging. Prefer one vivid, concrete image over three adjectives."
)

CLASSIFY_SYSTEM = (
    "You are the desk editor for an AI-and-robotics news monitor. For one article, "
    "decide if it is genuinely about the given topic (not keyword noise), classify it, "
    "and write a single sharp sentence. Also extract named companies, named people, and "
    "short thematic tags (e.g. 'driverless', 'humanoid', 'physical AI', 'drone').\n\n"
    "one_line voice: " + VOICE
)


class Assessment(BaseModel):
    relevant: bool
    category: Literal["launch", "funding", "research", "opinion", "other"]
    one_line: str
    companies: List[str]
    people: List[str]
    themes: List[str]


def build_user_prompt(article: Article, topic_name: str) -> str:
    return (
        f"Topic: {topic_name}\n"
        f"Headline: {article.title}\n"
        f"Source: {article.source}\n"
        f"Snippet: {article.snippet}\n\n"
        "Assess this article for the topic above."
    )


def assess(client, article: Article, topic_name: str,
           model: str = CLASSIFY_MODEL) -> Optional[Assessment]:
    """Return an Assessment, or None if the call/parse fails (skip-and-log)."""
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=CLASSIFY_MAX_TOKENS,
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": build_user_prompt(article, topic_name)}],
            output_format=Assessment,
        )
        return resp.parsed_output
    except Exception as e:  # noqa: BLE001 — one bad article must never crash the run
        log.warning("classify failed for %s: %s", article.url, e)
        return None
