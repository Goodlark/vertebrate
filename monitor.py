from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

import anthropic

import classify
import config
import feeds
import sitegen
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

    # Collapse same-story duplicates from different outlets before saving.
    mentions = store.dedupe_stories(mentions)
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

    wk = store.mentions_for_week(mentions, week)
    if not wk:
        log.info("No mentions for %s — nothing to write.", week)
        return {"week": week, "mentions": 0}

    rollup = weekly.write_weekly(client, wk)
    if rollup is not None:
        weekly.apply_rollup(mentions, rollup)
        weeks[week] = {"lede": rollup.lede, "generated_at": now.isoformat(timespec="seconds")}
        store.save_mentions(mentions, mentions_path)
        store.save_weeks(weeks, weeks_path)

    sitegen.build_site(mentions, weeks, out_dir=out_dir)
    log.info("Weekly run — %s / %d mentions", week, len(wk))
    return {"week": week, "mentions": len(wk)}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="Press Monitor for vertebrate.ai")
    parser.add_argument("--weekly", action="store_true", help="Generate the weekly edition.")
    parser.add_argument("--week", default=None, help="ISO week (YYYY-Www); defaults to now.")
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
    if args.weekly:
        run_weekly(now, args.week or store.iso_week(now), client)
    else:
        run_daily(now, topics, client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
