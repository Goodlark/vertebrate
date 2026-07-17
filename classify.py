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
    "and write a single sharp sentence.\n"
    "The sentence MUST lead with the fact and MUST name the primary company. If the story "
    "turns on something a specific person said or did (a founder, executive, official, or "
    "spokesperson), name that person too. These are facts — never drop the company or a "
    "named person for the sake of style.\n"
    "Also extract: 'companies' (real, specific organizations actually named — NOT the news "
    "outlet/publication that ran the story, NOT vague descriptors like 'a startup'), 'people' "
    "(ONLY proper names of specific individuals, e.g. 'Elon Musk' — NEVER job titles or roles "
    "like 'CEO' or 'a former engineer'), and short thematic tags "
    "(e.g. 'driverless', 'humanoid', 'physical AI', 'drone').\n\n"
    "one_line voice: " + VOICE
)

# In-place cleanup for stories collected before the fact-first rule existed. It never
# re-fetches the article, so it can only surface names already present in the data.
ENRICH_SYSTEM = (
    "You are a copy editor cleaning up one-sentence news summaries and their tags. For each "
    "item you get an id, a headline, a draft summary, and the currently-tagged companies. "
    "Return, per id:\n"
    "- 'one_line': the summary rewritten to LEAD WITH THE FACT and explicitly name the primary "
    "company and any person named in the headline or draft. One sentence, ~25-40 words, "
    "sophisticated but facts-first. If the draft already does this, return it unchanged. Do NOT "
    "invent facts, numbers, or names that are not in the headline or draft.\n"
    "- 'companies': only real, specific organizations actually named (keep the good ones from "
    "the given list). DROP news outlets/publications (e.g. TechCrunch, Yahoo, WSJ, Bloomberg, "
    "Interesting Engineering) and vague descriptors (e.g. 'a startup', 'humanoid robotics "
    "company'). [] if none.\n"
    "- 'people': ONLY proper names of specific individuals (e.g. 'Elon Musk', 'Oren Etzioni'). "
    "NEVER job titles, roles, or descriptions such as 'CEO', 'a spokesperson', or 'a former "
    "Tesla engineer'. [] if no real name is given."
)


class Assessment(BaseModel):
    relevant: bool
    category: Literal["launch", "funding", "research", "opinion", "other"]
    one_line: str
    companies: List[str]
    people: List[str]
    themes: List[str]


class EnrichItem(BaseModel):
    id: int
    one_line: str
    companies: List[str]
    people: List[str]


class EnrichBatch(BaseModel):
    items: List[EnrichItem]


def build_enrich_prompt(items: list) -> str:
    lines = []
    for i, m in enumerate(items):
        co = ", ".join(m.companies) or "—"
        lines.append(f"[{i}] headline: {m.title}\n    draft: {m.one_line}\n    companies: {co}")
    return "Items:\n" + "\n".join(lines) + "\n\nReturn one item per id."


def enrich_batch(client, items: list, model: str = CLASSIFY_MODEL) -> dict:
    """Return {batch_index: EnrichItem} of tightened summaries; {} on failure."""
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=2500,
            system=ENRICH_SYSTEM,
            messages=[{"role": "user", "content": build_enrich_prompt(items)}],
            output_format=EnrichBatch,
        )
        return {it.id: it for it in resp.parsed_output.items}
    except Exception as e:  # noqa: BLE001
        log.warning("enrich batch failed: %s", e)
        return {}


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
