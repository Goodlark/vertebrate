from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus

import feedparser

from config import PER_TOPIC_LIMIT, SNIPPET_MAX_CHARS, Topic


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published: str
    snippet: str


def google_news_rss_url(keywords: str) -> str:
    # hl/gl/ceid keep results in English/US; quote_plus encodes quotes and spaces.
    q = quote_plus(keywords)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


_TAG_RE = re.compile(r"<[^>]+>")


def _clean_snippet(raw: str, max_chars: int) -> str:
    text = _TAG_RE.sub("", raw or "").strip()
    return text[:max_chars]


def _title_and_source(entry) -> tuple:
    title = (getattr(entry, "title", "") or "").strip()
    # Google News exposes the outlet on entry.source.title; fall back to the
    # " - Outlet" suffix Google appends to titles.
    src = ""
    source_obj = getattr(entry, "source", None)
    if source_obj is not None:
        src = (getattr(source_obj, "title", "") or "").strip()
    if not src and " - " in title:
        title, src = title.rsplit(" - ", 1)
        title, src = title.strip(), src.strip()
    return title, src


def parse_entries(parsed, limit: int, snippet_max: int) -> list:
    articles = []
    for entry in parsed.entries[:limit]:
        title, source = _title_and_source(entry)
        articles.append(Article(
            title=title,
            url=(getattr(entry, "link", "") or "").strip(),
            source=source,
            published=(getattr(entry, "published", "") or "").strip(),
            snippet=_clean_snippet(getattr(entry, "summary", ""), snippet_max),
        ))
    return articles


def fetch_topic(topic: Topic, limit: int = PER_TOPIC_LIMIT,
                snippet_max: int = SNIPPET_MAX_CHARS) -> list:
    """Fetch one topic's feed. Returns [] on failure (caller logs); never raises."""
    parsed = feedparser.parse(google_news_rss_url(topic.keywords))
    return parse_entries(parsed, limit, snippet_max)
