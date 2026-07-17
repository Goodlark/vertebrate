from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

import anthropic

import classify
import config
import dedup
import feeds
import sitegen
import sources
import store
import weekly

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("pressmonitor")


def _paths(data_dir: str):
    return os.path.join(data_dir, "mentions.json"), os.path.join(data_dir, "weeks.json")


def run_daily(now: datetime, topics: list, client, out_dir: str = "docs",
              data_dir: str = "data") -> dict:
    mentions_path, weeks_path = _paths(data_dir)
    mentions = store.load_mentions(mentions_path)
    weeks = store.load_weeks(weeks_path)
    known = store.known_urls(mentions)

    fetched = relevant = added = 0
    for topic in topics:
        articles = feeds.fetch_topic(topic)
        fresh = store.filter_new(articles, known)
        fetched += len(fresh)
        for art in fresh:
            known.add(art.url)  # avoid re-adding a duplicate url within one run
            assessment = classify.assess(client, art, topic.name)
            if assessment is None or not assessment.relevant:
                continue
            relevant += 1
            mentions.append(store.Mention(
                url=art.url, title=art.title, source=art.source, published=art.published,
                topic=topic.name, category=assessment.category, one_line=assessment.one_line,
                companies=store.normalize_tags(assessment.companies),
                people=store.normalize_tags(assessment.people),
                themes=store.normalize_tags(assessment.themes),
                first_seen=now.isoformat(timespec="seconds"), week=store.iso_week(now)))
            added += 1

    # Collapse same-story duplicates within this week (other weeks left intact):
    # first the cheap title-overlap pass, then the semantic same-event pass.
    cur = store.iso_week(now)
    this_week = store.dedupe_stories(sitegen.rank_mentions([m for m in mentions if m.week == cur]))
    dedup.mark_duplicates(client, this_week)
    # Fill in the company/people/fact from the real article for anything the
    # headline+snippet didn't name (the reader needs the players up front).
    _fill_from_sources(client, [m for m in this_week if not m.duplicate], only_missing=True)
    mentions = [m for m in mentions if m.week != cur] + this_week
    store.save_mentions(mentions, mentions_path)
    sitegen.build_site(mentions, weeks, out_dir=out_dir)
    summary = {"fetched": fetched, "relevant": relevant, "added": added, "stored": len(mentions)}
    log.info("Daily run — fetched %(fetched)d new / relevant %(relevant)d / added %(added)d "
             "/ stored %(stored)d", summary)
    return summary


def run_weekly(now: datetime, week: str, client, out_dir: str = "docs",
               data_dir: str = "data") -> dict:
    mentions_path, weeks_path = _paths(data_dir)
    mentions = store.load_mentions(mentions_path)
    weeks = store.load_weeks(weeks_path)

    # Editorialize only the week's top stories (same-event duplicates hidden,
    # then dedup + importance-ranked), so Sonnet stays in budget and it reads clean.
    live = [m for m in store.mentions_for_week(mentions, week) if not m.duplicate]
    wk = store.dedupe_stories(sitegen.rank_mentions(live))
    wk = wk[:config.WEEKLY_STORY_LIMIT]
    if not wk:
        log.info("No mentions for %s — nothing to write.", week)
        return {"week": week, "mentions": 0}

    rollup = weekly.write_weekly(client, wk)
    if rollup is not None:
        weekly.apply_rollup(mentions, rollup)
        weeks[week] = {"summary": rollup.summary, "lede": rollup.lede,
                       "linkedin": rollup.linkedin,
                       "generated_at": now.isoformat(timespec="seconds")}
        store.save_mentions(mentions, mentions_path)
        store.save_weeks(weeks, weeks_path)

    sitegen.build_site(mentions, weeks, out_dir=out_dir)
    log.info("Weekly run — %s / %d mentions", week, len(wk))
    return {"week": week, "mentions": len(wk)}


def _fill_from_sources(client, mentions: list, only_missing: bool = True) -> tuple:
    """Read each story's real article (resolving Google News links) and fill in the
    company / people / fact from the actual text. Best-effort: a fetch that fails
    (paywall, block, dead link) simply leaves that story as-is."""
    filled = failed = 0
    for m in mentions:
        if only_missing and m.companies:
            continue
        text = sources.article_text(m.url)
        if not text:
            failed += 1
            continue
        ext = classify.extract_from_source(client, m.title, text)
        if ext is None:
            failed += 1
            continue
        if ext.companies:
            m.companies = store.normalize_tags(ext.companies)
        if ext.people:
            m.people = store.normalize_tags(ext.people)
        if ext.one_line.strip():
            m.one_line = ext.one_line.strip()
        filled += 1
    return filled, failed


def run_sources(now: datetime, client, out_dir: str = "docs", data_dir: str = "data",
                only_missing: bool = True) -> dict:
    """Fill company/people/fact from the real source articles, then rebuild. By
    default only touches stories that currently have no company tag."""
    mentions_path, weeks_path = _paths(data_dir)
    mentions = store.load_mentions(mentions_path)
    weeks = store.load_weeks(weeks_path)
    filled, failed = _fill_from_sources(
        client, [m for m in mentions if not m.duplicate], only_missing=only_missing)
    store.save_mentions(mentions, mentions_path)
    sitegen.build_site(mentions, weeks, out_dir=out_dir)
    log.info("Sources — filled %d story(ies) from the article, %d could not be fetched",
             filled, failed)
    return {"filled": filled, "failed": failed}


def run_clean(now: datetime, client, out_dir: str = "docs", data_dir: str = "data",
              enrich: bool = True) -> dict:
    """Re-clean stored data in place: (1) mark same-event duplicates per week,
    (2) tighten each visible summary to lead with the fact and name the company /
    speaker. No re-fetch, so no new stories are pulled. Then rebuild the site."""
    mentions_path, weeks_path = _paths(data_dir)
    mentions = store.load_mentions(mentions_path)
    weeks = store.load_weeks(weeks_path)

    dropped = 0
    for wk in sorted({m.week for m in mentions if m.week}):
        dropped += dedup.mark_duplicates(client, [m for m in mentions if m.week == wk])

    enriched = 0
    if enrich:
        live = [m for m in mentions if not m.duplicate]
        for i in range(0, len(live), 15):
            batch = live[i:i + 15]
            for idx, it in classify.enrich_batch(client, batch).items():
                if 0 <= idx < len(batch):
                    m = batch[idx]
                    if it.one_line.strip():
                        m.one_line = it.one_line.strip()
                    # Keep every real company; remove only flagged junk + the outlet itself.
                    drop = {d.strip().lower() for d in it.drop_companies}
                    drop.add((m.source or "").strip().lower())
                    m.companies = store.normalize_tags(
                        [c for c in m.companies if c.strip().lower() not in drop])
                    m.people = store.normalize_tags(it.people)         # proper names only
                    enriched += 1

    store.save_mentions(mentions, mentions_path)
    sitegen.build_site(mentions, weeks, out_dir=out_dir)
    log.info("Clean — marked %d duplicate(s), enriched %d summar(y/ies)", dropped, enriched)
    return {"dropped": dropped, "enriched": enriched}


def run_captions(now: datetime, client, out_dir: str = "docs",
                 data_dir: str = "data") -> dict:
    """Backfill LinkedIn captions for any weekly edition written before captions
    existed, then rebuild the site. Live weekly runs already include the caption."""
    mentions_path, weeks_path = _paths(data_dir)
    mentions = store.load_mentions(mentions_path)
    weeks = store.load_weeks(weeks_path)

    done = 0
    for week, meta in weeks.items():
        if meta.get("linkedin"):
            continue
        wk = store.dedupe_stories(
            sitegen.rank_mentions(store.mentions_for_week(mentions, week)))[:config.WEEKLY_STORY_LIMIT]
        caption = weekly.write_linkedin(
            client, week, meta.get("summary", ""), meta.get("lede", ""), wk)
        if caption:
            meta["linkedin"] = caption
            done += 1
    store.save_weeks(weeks, weeks_path)
    sitegen.build_site(mentions, weeks, out_dir=out_dir)
    log.info("Captions — backfilled %d week(s)", done)
    return {"captions": done}


def run_backfill(now: datetime, week: str, topics: list, client, out_dir: str = "docs",
                 data_dir: str = "data") -> dict:
    """Fetch a past ISO week's news (by publication date), store it tagged to that
    week, then write that week's editorial. Reusable for any prior week."""
    mentions_path, _ = _paths(data_dir)
    mentions = store.load_mentions(mentions_path)
    known = store.known_urls(mentions)

    monday, sunday = store.iso_week_bounds(week)
    # Google News date operators are day-granular; widen by a day on each side.
    after = (monday - timedelta(days=1)).isoformat()
    before = (sunday + timedelta(days=1)).isoformat()
    seen_stamp = datetime.combine(monday, datetime.min.time()).isoformat(timespec="seconds")

    added = 0
    for topic in topics:
        dated = config.Topic(topic.name, f"{topic.keywords} after:{after} before:{before}")
        for art in store.filter_new(feeds.fetch_topic(dated), known):
            known.add(art.url)
            assessment = classify.assess(client, art, topic.name)
            if assessment is None or not assessment.relevant:
                continue
            mentions.append(store.Mention(
                url=art.url, title=art.title, source=art.source, published=art.published,
                topic=topic.name, category=assessment.category, one_line=assessment.one_line,
                companies=store.normalize_tags(assessment.companies),
                people=store.normalize_tags(assessment.people),
                themes=store.normalize_tags(assessment.themes),
                first_seen=seen_stamp, week=week))
            added += 1

    # Collapse duplicates within the backfilled week only (title pass + same-event pass).
    this_week = store.dedupe_stories(sitegen.rank_mentions([m for m in mentions if m.week == week]))
    dedup.mark_duplicates(client, this_week)
    mentions = [m for m in mentions if m.week != week] + this_week
    store.save_mentions(mentions, mentions_path)
    log.info("Backfill %s — added %d stories", week, added)
    return run_weekly(now, week, client, out_dir=out_dir, data_dir=data_dir)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="Press Monitor for vertebrate.ai")
    parser.add_argument("--weekly", action="store_true", help="Generate the weekly edition.")
    parser.add_argument("--week", default=None, help="ISO week (YYYY-Www); defaults to now.")
    parser.add_argument("--backfill", default=None, metavar="YYYY-Www",
                        help="Fetch a past ISO week's news by publication date and write its weekly.")
    parser.add_argument("--captions", action="store_true",
                        help="Backfill LinkedIn captions for editions that lack one, then rebuild.")
    parser.add_argument("--clean", action="store_true",
                        help="Re-clean stored data in place: mark same-event duplicates and "
                             "tighten summaries (company/speaker facts), then rebuild.")
    parser.add_argument("--no-enrich", action="store_true",
                        help="With --clean, only de-duplicate; skip the summary-tightening pass.")
    parser.add_argument("--sources", action="store_true",
                        help="Fill company/people/fact from the real source articles "
                             "(resolves Google News links), then rebuild.")
    parser.add_argument("--all", action="store_true",
                        help="With --sources, re-read every story, not just those missing a company.")
    args = parser.parse_args(argv)

    try:
        config.load_env()
        config.require_api_key()
        topics = config.load_watchlist()
    except config.ConfigError as e:
        log.error("Config error: %s", e)
        return 1

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    now = datetime.now()
    if args.backfill:
        run_backfill(now, args.backfill, topics, client)
    elif args.sources:
        run_sources(now, client, only_missing=not args.all)
    elif args.clean:
        run_clean(now, client, enrich=not args.no_enrich)
    elif args.captions:
        run_captions(now, client)
    elif args.weekly:
        run_weekly(now, args.week or store.iso_week(now), client)
    else:
        run_daily(now, topics, client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
