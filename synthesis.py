from __future__ import annotations

import hashlib
import logging
import re
from typing import List, Literal

from pydantic import BaseModel

import store
from config import WEEKLY_MODEL
from dedup import _entity_groups, _keep_key
from weekly import VOICE

log = logging.getLogger("pressmonitor.synthesis")

ARTICLE_SYSTEM = (
    "You are a robotics-industry reporter writing a full news article for a serious outlet. You "
    "get a headline and the source items it combines. Write the article, about 350-500 words:\n"
    "1. Open with the news itself — what happened, WHEN, and WHERE — naming the company and the "
    "concrete specifics (numbers, cities, people, partners).\n"
    "2. Then explain why it matters: the impact on the robotics industry, and where relevant on "
    "the economy and on people's lives. Be concrete and grounded in the source items; never "
    "invent facts, figures, or quotes.\n"
    "Return clean HTML paragraphs (<p>...</p>) only — no headline, no markdown, no lists.\n"
    "Voice: " + VOICE
)


def _clean_html(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text.strip()).strip()
    if "<p" not in text.lower():   # model returned plain paragraphs — wrap them
        text = "".join(f"<p>{p.strip()}</p>" for p in re.split(r"\n\s*\n", text) if p.strip())
    return text


def _slug(title: str, url: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:60] or "story"
    return f"{base}-{hashlib.md5((url or '').encode()).hexdigest()[:6]}"


def write_article(client, title: str, summary: str, items: list, model: str = WEEKLY_MODEL) -> str:
    """Write the full HTML article body for a combined story from its source items."""
    src = "\n".join(f"- {it.get('title', '')} — {it.get('one_line', '')} ({it.get('source', '')})"
                    for it in items)
    try:
        resp = client.messages.create(
            model=model, max_tokens=1500, system=ARTICLE_SYSTEM,
            messages=[{"role": "user", "content":
                       f"Headline: {title}\nSummary: {summary}\n\nSource items:\n{src}\n\n"
                       "Write the article body (HTML paragraphs)."}],
        )
        return _clean_html("".join(getattr(b, "text", "") for b in resp.content))
    except Exception as e:  # noqa: BLE001
        log.warning("article generation failed: %s", e)
        return ""

SYNTH_SYSTEM = (
    "You are the editor of an AI-and-robotics news brief. You are given several news items "
    "from one day that all concern the same company. Group the items that belong to the SAME "
    "ongoing story or theme — e.g. one company's rollout across several cities, or several "
    "funding/order items — into ONE combined story. For each group of 2 OR MORE items, write:\n"
    "- 'title': an informative, non-clickbait headline that names the company and what happened "
    "(e.g. 'Waymo Expands Robotaxis to Denver, San Diego and Tampa').\n"
    "- 'summary': 2-4 sentences weaving the items together, naming the specifics (cities, "
    "numbers, people, partners).\n"
    "- 'category': the best fit (launch, funding, research, opinion, other).\n"
    "- 'ids': the indices of the items in this combined story.\n"
    "Return ONLY combined stories of 2+ items; items that stand on their own are omitted.\n"
    "Voice: " + VOICE
)


class SynthStory(BaseModel):
    ids: List[int]
    title: str
    summary: str
    category: Literal["launch", "funding", "research", "opinion", "other"]


class SynthResult(BaseModel):
    stories: List[SynthStory]


def _prompt(items: list) -> str:
    lines = [f"[{i}] {m.title} — {m.one_line} (source: {m.source})" for i, m in enumerate(items)]
    return "News items:\n" + "\n".join(lines) + "\n\nReturn the combined stories (2+ items each)."


def _synthesize_group(client, items: list, model: str) -> list:
    try:
        resp = client.messages.parse(
            model=model, max_tokens=2000, system=SYNTH_SYSTEM,
            messages=[{"role": "user", "content": _prompt(items)}],
            output_format=SynthResult,
        )
        return resp.parsed_output.stories
    except Exception as e:  # noqa: BLE001
        log.warning("synthesis failed: %s", e)
        return []


def synthesize_day(client, day_mentions: list, model: str = WEEKLY_MODEL) -> int:
    """Group a day's stories per company and synthesize each 2+ thread into one briefing.

    The representative mention becomes the synthesized story (informative title, combined
    summary, all sources); the other members are marked `folded` and hidden individually.
    Returns how many combined stories were written.
    """
    count = 0
    for group in _entity_groups(day_mentions):
        if len(group) < 2:
            continue
        sub = [day_mentions[i] for i in group]
        for story in _synthesize_group(client, sub, model):
            members = [sub[i] for i in story.ids if 0 <= i < len(sub)]
            members = [m for m in members if not m.folded]           # don't double-fold
            if len(members) < 2:
                continue
            members.sort(key=_keep_key)                              # earliest/best = representative
            rep, rest = members[0], members[1:]
            items = [{"title": m.title, "one_line": m.one_line, "source": m.source} for m in members]
            rep.slug = _slug(story.title, rep.url)
            rep.body = write_article(client, story.title, story.summary, items, model)
            rep.title = story.title.strip() or rep.title
            rep.one_line = story.summary.strip() or rep.one_line
            rep.category = story.category
            rep.sources = [{"url": m.url, "title": m.title, "source": m.source} for m in members]
            rep.companies = store.normalize_tags([c for m in members for c in m.companies])
            rep.people = store.normalize_tags([p for m in members for p in m.people])
            rep.themes = store.normalize_tags([t for m in members for t in m.themes])
            for m in rest:
                m.folded = True
            count += 1
    return count


def write_missing_articles(client, mentions: list, model: str = WEEKLY_MODEL) -> int:
    """Backfill full article bodies for combined stories that have sources but no body yet."""
    n = 0
    for m in mentions:
        if m.sources and not m.body:
            items = [{"title": s.get("title", ""), "one_line": "", "source": s.get("source", "")}
                     for s in m.sources]
            if not m.slug:
                m.slug = _slug(m.title, m.url)
            m.body = write_article(client, m.title, m.one_line, items, model)
            if m.body:
                n += 1
    return n
