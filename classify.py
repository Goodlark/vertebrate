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
    "Set 'is_news' true ONLY if the item reports a concrete development — a product/robot "
    "launch, a funding round, a hire or departure, a deployment or order, real results/data, "
    "or a partnership. Set it false for opinion, analysis, company culture, how-to, hiring "
    "drives, or pure marketing. (This matters most for company blog posts, which mix "
    "announcements with essays.)\n"
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
    "- 'drop_companies': ONLY the entries in the given company list that are NOT real companies — "
    "i.e. news outlets/publications (e.g. TechCrunch, Yahoo, WSJ, Bloomberg, Reuters, Axios, "
    "Interesting Engineering, DroneDJ) or vague descriptors (e.g. 'a startup', 'humanoid robotics "
    "company'). Keep every real company; when unsure, do NOT drop it. [] if the list is clean.\n"
    "- 'people': ONLY proper names of specific individuals (e.g. 'Elon Musk', 'Oren Etzioni'). "
    "NEVER job titles, roles, or descriptions such as 'CEO', 'a spokesperson', or 'a former "
    "Tesla engineer'. [] if no real name is given."
)


class Assessment(BaseModel):
    relevant: bool
    is_news: bool = True     # false = opinion/culture/how-to; enforced for company blog posts
    category: Literal["launch", "funding", "research", "opinion", "other"]
    one_line: str
    companies: List[str]
    people: List[str]
    themes: List[str]


class EnrichItem(BaseModel):
    id: int
    one_line: str
    drop_companies: List[str]
    people: List[str]


class EnrichBatch(BaseModel):
    items: List[EnrichItem]


SOURCE_SYSTEM = (
    "You are the desk editor. You are given a news article's headline and body text. "
    "Extract the facts:\n"
    "- 'companies': the real, specific organizations that are the SUBJECT of the story (the "
    "robot maker, the funded startup, the buyer, the deploying agency, etc.), using proper "
    "names as written. Do NOT include the news outlet/publication that ran the story. [] if "
    "truly none.\n"
    "- 'people': proper names of specific individuals central to the story (founders, "
    "executives, officials). NEVER job titles or roles like 'CEO'. [] if none.\n"
    "- 'one_line': one sharp sentence, ~25-40 words, that LEADS WITH THE FACT and names the "
    "primary company (and the key person, if any).\n\n"
    "one_line voice: " + VOICE
)


class SourceExtract(BaseModel):
    companies: List[str]
    people: List[str]
    one_line: str


def extract_from_source(client, title: str, text: str,
                        model: str = CLASSIFY_MODEL) -> Optional["SourceExtract"]:
    """Extract grounded companies/people/fact from an article's real body text."""
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=400,
            system=SOURCE_SYSTEM,
            messages=[{"role": "user", "content": f"Headline: {title}\n\nArticle:\n{text}"}],
            output_format=SourceExtract,
        )
        return resp.parsed_output
    except Exception as e:  # noqa: BLE001
        log.warning("source extract failed: %s", e)
        return None


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
