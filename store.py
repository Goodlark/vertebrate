from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Optional

from feeds import Article  # noqa: F401 (documents the Article -> Mention relationship)


@dataclass
class Mention:
    url: str
    title: str
    source: str
    published: str
    topic: str
    category: str
    one_line: str
    companies: list = field(default_factory=list)
    people: list = field(default_factory=list)
    themes: list = field(default_factory=list)
    first_seen: str = ""
    week: str = ""
    why: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Mention":
        return Mention(**d)


def iso_week(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def iso_week_bounds(week_str: str) -> tuple:
    """'2026-W28' -> (date(2026, 7, 6), date(2026, 7, 12)) — the Monday and Sunday."""
    year_s, wk_s = week_str.split("-W")
    year, wk = int(year_s), int(wk_s)
    return date.fromisocalendar(year, wk, 1), date.fromisocalendar(year, wk, 7)


def normalize_tags(tags: list) -> list:
    """Trim, drop blanks, and dedupe case-insensitively keeping the first spelling."""
    seen = {}
    for t in tags or []:
        label = str(t).strip()
        if label and label.lower() not in seen:
            seen[label.lower()] = label
    return list(seen.values())


def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_mentions(path: str = "data/mentions.json") -> list:
    return [Mention.from_dict(d) for d in _read_json(path, [])]


def save_mentions(mentions: list, path: str = "data/mentions.json") -> None:
    _write_json(path, [m.to_dict() for m in mentions])


def known_urls(mentions: list) -> set:
    return {m.url for m in mentions}


def filter_new(articles: list, known: set) -> list:
    return [a for a in articles if a.url and a.url not in known]


def mentions_for_week(mentions: list, week: str) -> list:
    return [m for m in mentions if m.week == week]


def load_weeks(path: str = "data/weeks.json") -> dict:
    return _read_json(path, {})


def save_weeks(weeks: dict, path: str = "data/weeks.json") -> None:
    _write_json(path, weeks)


# --- Near-duplicate detection -------------------------------------------------
# The same event is often filed by several outlets under slightly different
# headlines. We collapse them by comparing the "significant words" of each title:
# if two titles share most of their meaningful words, they're the same story.

DUP_THRESHOLD = 0.6          # title-word overlap required when two stories share NO named entity
DUP_THRESHOLD_ENTITY = 0.4   # lower bar when they share a company/person (same subject)

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "after", "before",
    "over", "its", "has", "have", "had", "are", "was", "were", "will", "would",
    "can", "could", "not", "new", "say", "says", "said", "amid", "who", "how",
    "why", "what", "when", "been", "being", "their", "they", "them", "out", "off",
    "per", "via", "but", "all", "one", "get", "gets", "now", "you", "your",
}


def _stem(w: str) -> str:
    """Crude singular-ise so 'drones'/'drone' and 'deliveries'/'delivery' match."""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"          # deliveries -> delivery
    if len(w) > 3 and w.endswith("s"):
        return w[:-1]                # drones -> drone, services -> service
    return w


def _title_key(m) -> set:
    """The set of significant, stemmed words in a title (outlet suffix removed)."""
    t = m.title.lower()
    src = (m.source or "").lower()
    if src and t.endswith(" - " + src):
        t = t[: -(len(src) + 3)]
    elif " - " in t:                      # Google News appends "- Outlet"
        t = t.rsplit(" - ", 1)[0]
    words = re.findall(r"[a-z0-9]+", t)
    return {_stem(w) for w in words if len(w) > 2 and w not in STOPWORDS}


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _entities(m) -> set:
    return {e.strip().lower() for e in (list(m.companies) + list(m.people)) if e.strip()}


def _is_duplicate(a, b) -> bool:
    """Same story if titles overlap a lot, or overlap moderately AND share a subject."""
    ov = _overlap(_title_key(a), _title_key(b))
    if _entities(a) & _entities(b):
        return ov >= DUP_THRESHOLD_ENTITY
    return ov >= DUP_THRESHOLD


def dedupe_stories(mentions: list) -> list:
    """Drop near-duplicate stories, keeping the first occurrence of each.

    Callers pass mentions in priority order (best first) so the representative
    kept is the one they'd most want to show.
    """
    seen = []   # every mention processed — enables transitive (single-link) matching
    out = []
    for m in mentions:
        if any(_is_duplicate(m, s) for s in seen):
            seen.append(m)               # record even dropped ones, for chaining
            continue
        seen.append(m)
        out.append(m)
    return out
