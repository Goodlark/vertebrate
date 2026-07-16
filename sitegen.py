from __future__ import annotations

import os
import re
import shutil
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

import store
from config import DOMAIN, MAIN_FEED_LIMIT, SITE_TAGLINE, SITE_TITLE

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# tag kind -> CSS class used in templates
_KIND_CLASS = {"company": "co", "person": "pe", "theme": "th"}

# A rough "importance" order for the lead feed: hard news leads, briefs trail.
_CATEGORY_RANK = {"launch": 5, "funding": 4, "research": 3, "opinion": 2, "other": 1}


@dataclass
class TagCount:
    label: str
    kind: str  # "company" | "person" | "theme"
    count: int
    slug: str


# --- Pure helpers (unit-tested without touching the filesystem) ---------------

def slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.strip().lower()).strip("-")


def size_class(count: int, max_count: int) -> str:
    if max_count <= 0:
        return "s1"
    bucket = 1 + round(4 * (count - 1) / max(1, max_count - 1))
    bucket = max(1, min(5, bucket))
    return f"s{bucket}"


def build_tag_index(mentions: list) -> list:
    # Count each label within its kind; a label keeps its first-seen spelling.
    counts: "OrderedDict[str, TagCount]" = OrderedDict()
    for m in mentions:
        for kind, labels in (("company", m.companies), ("person", m.people), ("theme", m.themes)):
            for label in labels:
                key = f"{kind}:{label.lower()}"
                if key in counts:
                    counts[key].count += 1
                else:
                    counts[key] = TagCount(label=label, kind=kind, count=1, slug=slugify(label))
    return sorted(counts.values(), key=lambda t: (-t.count, t.label.lower()))


def group_by_topic(mentions: list) -> "OrderedDict[str, list]":
    grouped: "OrderedDict[str, list]" = OrderedDict()
    for m in mentions:
        grouped.setdefault(m.topic, []).append(m)
    return grouped


def rank_mentions(mentions: list) -> list:
    """Order mentions for the homepage: hard-news category first, then most recent."""
    return sorted(mentions,
                  key=lambda m: (_CATEGORY_RANK.get(m.category, 0), m.first_seen),
                  reverse=True)


# --- Site builder -------------------------------------------------------------

def _env(templates_dir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
    )


def _common(root: str) -> dict:
    return {"site_title": SITE_TITLE, "site_tagline": SITE_TAGLINE, "root": root,
            "today": datetime.now().strftime("%a · %d %b %Y").upper()}


def build_site(mentions: list, weeks: dict, out_dir: str = "docs",
               templates_dir: str = "templates") -> None:
    env = _env(templates_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Collapse the same story from different outlets (highest-ranked kept),
    # then split into lead stories vs. the "Also happened today" briefs.
    ranked = store.dedupe_stories(rank_mentions(mentions))
    feed = ranked[:MAIN_FEED_LIMIT]
    also = ranked[MAIN_FEED_LIMIT:]

    tags = build_tag_index(ranked)
    max_count = max((t.count for t in tags), default=1)
    view_tags = [
        {"label": t.label, "slug": t.slug, "kind_class": _KIND_CLASS[t.kind],
         "size": size_class(t.count, max_count)}
        for t in tags
    ]

    week_ids = sorted(weeks.keys(), reverse=True)
    latest_week = week_ids[0] if week_ids else None
    latest_lede = weeks.get(latest_week, {}).get("lede", "") if latest_week else ""

    # Homepage
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("index.html").render(
            mentions=feed, also=also, tags=view_tags, latest_week=latest_week,
            latest_lede=latest_lede, **_common("")))

    # Weekly editions + archive
    weekly_dir = os.path.join(out_dir, "weekly")
    os.makedirs(weekly_dir, exist_ok=True)
    for week_id in week_ids:
        wk_mentions = [m for m in ranked if m.week == week_id]
        with open(os.path.join(weekly_dir, f"{week_id}.html"), "w", encoding="utf-8") as f:
            f.write(env.get_template("weekly_edition.html").render(
                week=week_id, lede=weeks[week_id].get("lede", ""),
                groups=group_by_topic(wk_mentions), **_common("../")))
    with open(os.path.join(weekly_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("weekly_index.html").render(weeks=week_ids, **_common("../")))

    # Tag pages
    tag_dir = os.path.join(out_dir, "tag")
    os.makedirs(tag_dir, exist_ok=True)
    for t in tags:
        tagged = [m for m in ranked if t.label in (m.companies + m.people + m.themes)]
        with open(os.path.join(tag_dir, f"{t.slug}.html"), "w", encoding="utf-8") as f:
            f.write(env.get_template("tag.html").render(
                label=t.label, mentions=tagged, **_common("../")))

    # Static assets
    shutil.copyfile(os.path.join(templates_dir, "style.css"),
                    os.path.join(out_dir, "style.css"))
    with open(os.path.join(out_dir, "CNAME"), "w", encoding="utf-8") as f:
        f.write(DOMAIN + "\n")
