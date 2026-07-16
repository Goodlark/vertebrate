from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
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
