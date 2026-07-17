from __future__ import annotations

import html
import os
import re
import shutil
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

import store
from config import (DOMAIN, MAIN_FEED_LIMIT, SITE_DESC, SITE_TAGLINE, SITE_TITLE,
                    WEEKLY_STORY_LIMIT)

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# tag kind -> CSS class used in templates
_KIND_CLASS = {"company": "co", "person": "pe", "theme": "th"}

# A rough "importance" order for the lead feed: hard news leads, briefs trail.
_CATEGORY_RANK = {"launch": 5, "funding": 4, "research": 3, "opinion": 2, "other": 1}

# Tiny inline-style favicon: a red "V" on the aged-manila paper colour.
_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" fill="#ecdcb6"/>'
    '<text x="16" y="24" text-anchor="middle" font-family="Georgia,serif" '
    'font-weight="bold" font-size="24" fill="#b1332a">V</text></svg>'
)


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


def _rfc822(d) -> str:
    """RFC-822 date (RSS pubDate) at noon UTC on the given date."""
    return format_datetime(datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc))


def build_feed(weeks: dict, mentions: list, week_ids: list) -> str:
    """An RSS 2.0 feed of the weekly editions — one item per edition, newest first,
    carrying the full write-up so Substack (and any reader) can import it whole."""
    base = "https://%s" % DOMAIN
    items = []
    for wid in week_ids:                                  # week_ids is newest-first
        meta = weeks.get(wid, {})
        _monday, sunday = store.iso_week_bounds(wid)
        link = "%s/weekly/%s.html" % (base, wid)
        title = "The Weekly — %s" % wid

        wk = store.dedupe_stories(
            rank_mentions([m for m in mentions if m.week == wid]))[:WEEKLY_STORY_LIMIT]
        parts = []
        if meta.get("summary"):
            parts.append("<p><strong>%s</strong></p>" % html.escape(meta["summary"]))
        if meta.get("lede"):
            parts.append("<p><em>%s</em></p>" % html.escape(meta["lede"]))
        for m in wk:
            who = ", ".join(list(m.companies) + list(m.people))
            parts.append('<h3><a href="%s">%s</a></h3>'
                         % (html.escape(m.url), html.escape(m.title)))
            if who:
                parts.append("<p><strong>%s</strong></p>" % html.escape(who))
            parts.append("<p>%s</p>" % html.escape(m.one_line))
            if m.why:
                parts.append("<p><em>Why it matters.</em> %s</p>" % html.escape(m.why))
            parts.append('<p><a href="%s">Read at %s &rarr;</a></p>'
                         % (html.escape(m.url), html.escape(m.source)))
        body = "\n".join(parts).replace("]]>", "]]&gt;")   # keep CDATA well-formed
        desc = meta.get("summary") or meta.get("lede") or title

        items.append(
            "  <item>\n"
            "    <title>%s</title>\n"
            "    <link>%s</link>\n"
            '    <guid isPermaLink="true">%s</guid>\n'
            "    <pubDate>%s</pubDate>\n"
            "    <description>%s</description>\n"
            "    <content:encoded><![CDATA[%s]]></content:encoded>\n"
            "  </item>" % (xml_escape(title), link, link, _rfc822(sunday),
                           xml_escape(desc), body)
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
        'xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "<channel>\n"
        "  <title>%s — The Weekly</title>\n"
        "  <link>%s/</link>\n"
        '  <atom:link href="%s/feed.xml" rel="self" type="application/rss+xml"/>\n'
        "  <description>%s</description>\n"
        "  <language>en-us</language>\n"
        "%s\n"
        "</channel>\n</rss>\n"
        % (xml_escape(SITE_TITLE), base, base, xml_escape(SITE_DESC), "\n".join(items))
    )


# --- Site builder -------------------------------------------------------------

def _env(templates_dir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
    )


def _common(root: str, page_path: str = "") -> dict:
    return {"site_title": SITE_TITLE, "site_tagline": SITE_TAGLINE, "site_desc": SITE_DESC,
            "domain": DOMAIN, "root": root, "page_path": page_path,
            "today": datetime.now().strftime("%a · %d %b %Y").upper()}


def build_site(mentions: list, weeks: dict, out_dir: str = "docs",
               templates_dir: str = "templates") -> None:
    env = _env(templates_dir)
    # Rebuild from scratch so stale pages (tags/weeks no longer present) don't linger.
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Same-event duplicates are marked (not deleted) upstream; hide them from every view.
    mentions = [m for m in mentions if not getattr(m, "duplicate", False)]

    # Importance-ranked, not yet deduped — dedup happens per rendered view so
    # the same ongoing story can still appear in each week it was news.
    ranked = rank_mentions(mentions)

    # The homepage shows only the most recent ISO week; earlier weeks live on
    # their own weekly pages. This keeps "Also Happened Today" honest and stops
    # the front page from growing without bound as the archive fills up.
    weeks_present = sorted({m.week for m in mentions if m.week}, reverse=True)
    current_week = weeks_present[0] if weeks_present else None
    home_src = [m for m in ranked if m.week == current_week] if current_week else ranked
    home = store.dedupe_stories(home_src)
    feed = home[:MAIN_FEED_LIMIT]
    also = home[MAIN_FEED_LIMIT:]

    # The Index (sidebar): companies + main topics only. People are dropped — they
    # cluttered it — and one-off themes are trimmed so only recurring topics remain.
    all_tags = build_tag_index(home)
    company_tags = [t for t in all_tags if t.kind == "company"][:40]
    topic_tags = [t for t in all_tags if t.kind == "theme"]
    topic_tags = ([t for t in topic_tags if t.count >= 2] or topic_tags)[:24]
    tags = company_tags + topic_tags   # what the Index links to (also tag pages + sitemap)

    def _view(group: list) -> list:
        mx = max((t.count for t in group), default=1)
        return [{"label": t.label, "slug": t.slug, "size": size_class(t.count, mx)} for t in group]
    view_companies = _view(company_tags)
    view_topics = _view(topic_tags)

    week_ids = sorted(weeks.keys(), reverse=True)
    latest_week = week_ids[0] if week_ids else None
    latest_meta = weeks.get(latest_week, {}) if latest_week else {}
    latest_dek = latest_meta.get("summary") or latest_meta.get("lede", "")

    # Homepage
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("index.html").render(
            mentions=feed, also=also, companies=view_companies, topics=view_topics,
            latest_week=latest_week, latest_dek=latest_dek, **_common("", "")))

    # Weekly editions + archive
    weekly_dir = os.path.join(out_dir, "weekly")
    os.makedirs(weekly_dir, exist_ok=True)
    for week_id in week_ids:
        wk_mentions = store.dedupe_stories(
            [m for m in ranked if m.week == week_id])[:WEEKLY_STORY_LIMIT]
        monday, _sun = store.iso_week_bounds(week_id)
        with open(os.path.join(weekly_dir, f"{week_id}.html"), "w", encoding="utf-8") as f:
            f.write(env.get_template("weekly_edition.html").render(
                week=week_id, lede=weeks[week_id].get("lede", ""),
                summary=weeks[week_id].get("summary", ""),
                linkedin=weeks[week_id].get("linkedin", ""), week_date=monday.isoformat(),
                groups=group_by_topic(wk_mentions),
                **_common("../", "weekly/" + week_id + ".html")))
    week_views = [{"id": w, "summary": weeks.get(w, {}).get("summary", "")} for w in week_ids]
    with open(os.path.join(weekly_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("weekly_index.html").render(
            weeks=week_views, **_common("../", "weekly/index.html")))

    # Tag pages
    tag_dir = os.path.join(out_dir, "tag")
    os.makedirs(tag_dir, exist_ok=True)
    for t in tags:
        tagged = store.dedupe_stories(
            [m for m in ranked if t.label in (m.companies + m.people + m.themes)])
        with open(os.path.join(tag_dir, f"{t.slug}.html"), "w", encoding="utf-8") as f:
            f.write(env.get_template("tag.html").render(
                label=t.label, mentions=tagged, **_common("../", "tag/" + t.slug + ".html")))

    # Static assets
    shutil.copyfile(os.path.join(templates_dir, "style.css"),
                    os.path.join(out_dir, "style.css"))
    og_src = os.path.join(templates_dir, "og.png")
    if os.path.exists(og_src):                       # social share card
        shutil.copyfile(og_src, os.path.join(out_dir, "og.png"))
    with open(os.path.join(out_dir, "CNAME"), "w", encoding="utf-8") as f:
        f.write(DOMAIN + "\n")

    # SEO: favicon, robots.txt, and a sitemap of every page.
    with open(os.path.join(out_dir, "favicon.svg"), "w", encoding="utf-8") as f:
        f.write(_FAVICON_SVG)
    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: https://%s/sitemap.xml\n" % DOMAIN)
    paths = [""] + ["weekly/index.html"] + [f"weekly/{w}.html" for w in week_ids] \
        + [f"tag/{t.slug}.html" for t in tags]
    urls = "".join('  <url><loc>https://%s/%s</loc></url>\n' % (DOMAIN, p) for p in paths)
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + urls + "</urlset>\n")

    # Syndication: an RSS feed of the weekly editions (readers + Substack import).
    with open(os.path.join(out_dir, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(build_feed(weeks, mentions, week_ids))
