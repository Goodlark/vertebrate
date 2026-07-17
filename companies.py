from __future__ import annotations

import logging
import re
from typing import List
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from pydantic import BaseModel

from config import CLASSIFY_MODEL
from feeds import Article

log = logging.getLogger("pressmonitor.companies")

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


class PostLink(BaseModel):
    title: str
    url: str


class PostLinks(BaseModel):
    posts: List[PostLink]


EXTRACT_SYSTEM = (
    "You are given the link text and URLs found on a company's newsroom / blog index page. "
    "Return ONLY the links that are individual news articles or blog posts published BY THIS "
    "company — each an actual story with its own page. Exclude navigation, categories, tags, "
    "pagination, 'read more', social, legal, careers, and external links. Clean each title "
    "(no dates or 'Blog' labels). Keep the URL exactly as given."
)


def _anchors(html: str, base: str) -> list:
    """(title, absolute_url) for on-site links, de-duplicated, nav-ish junk dropped."""
    out, seen = [], set()
    host = urlparse(base).netloc
    for href, inner in re.findall(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        url = urljoin(base, href.strip())
        if urlparse(url).netloc != host:
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        key = url.split("#")[0]
        if len(title) < 6 or key in seen:
            continue
        seen.add(key)
        out.append((title, url))
    return out[:80]


def _extract_posts(client, company: dict, cands: list, model: str) -> list:
    listing = "\n".join(f"- {t} | {u}" for t, u in cands)
    try:
        resp = client.messages.parse(
            model=model, max_tokens=1500, system=EXTRACT_SYSTEM,
            messages=[{"role": "user",
                       "content": f"Company: {company['name']}\nNewsroom: {company['url']}\n\n"
                                  f"Links found:\n{listing}"}],
            output_format=PostLinks,
        )
        return [(p.title, p.url) for p in resp.parsed_output.posts]
    except Exception as e:  # noqa: BLE001
        log.warning("post extraction failed for %s: %s", company["name"], e)
        return []


def list_posts(company: dict, client, model: str = CLASSIFY_MODEL, limit: int = 8) -> List[Article]:
    """Recent posts from a company newsroom as Article candidates (snippet filled later).

    RSS feed when the company has one; otherwise fetch the index page and let the
    model pick the real articles out of the links.
    """
    name = company["name"]
    if company.get("rss"):
        d = feedparser.parse(company["rss"])
        items = [(e.get("title", "").strip(), e.get("link", "").strip())
                 for e in d.entries[:limit]]
    else:
        try:
            html = requests.get(company["url"], headers=UA, timeout=20).text
        except Exception as e:  # noqa: BLE001
            log.warning("newsroom fetch failed for %s: %s", name, e)
            return []
        items = _extract_posts(client, company, _anchors(html, company["url"]), model)[:limit]

    return [Article(title=t, url=u, source=name, published="", snippet="")
            for t, u in items if t and u]
