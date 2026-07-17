from __future__ import annotations

import logging
from typing import List

from pydantic import BaseModel

from config import CLASSIFY_MODEL
from sitegen import rank_mentions

log = logging.getLogger("pressmonitor.dedup")

# Same-event de-duplication. Title-word overlap can't tell that "Waymo comes to
# Tampa" and "Waymo to start rides in 4 more markets" are one event told from two
# angles — so we ask the model to cluster stories by the underlying event.
DEDUP_SYSTEM = (
    "You are a news-desk editor collapsing a wire. You get a numbered list of articles "
    "(id, headline, fact, companies). Group together every article that reports the SAME "
    "underlying news event — even if the outlet, the angle, or which city/detail it "
    "emphasizes differs. Two articles are the same event if a reader would say 'that's the "
    "same story.'\n"
    "Also merge multiple stories in which the SAME company makes the SAME KIND of "
    "announcement in this period — e.g. several stories about one company rolling out its "
    "robotaxi service to various cities (Denver, San Diego, Tampa, '4 new markets') are ONE "
    "expansion story; several stories about a single funding round are one story. Keep the "
    "broadest / most complete one as the representative.\n"
    "But do NOT merge DIFFERENT KINDS of events about the same company: an expansion, a car "
    "being vandalized, a lawsuit, a safety complaint, and a pricing quirk are five different "
    "stories. Return the groups so that every id appears in exactly one group; a story with "
    "no duplicate is a group of one."
)


class Group(BaseModel):
    ids: List[int]


class Clusters(BaseModel):
    groups: List[Group]


def build_dedup_prompt(items: list) -> str:
    lines = []
    for i, m in enumerate(items):
        co = ", ".join(m.companies) or "—"
        lines.append(f"[{i}] {m.title} | {m.one_line} | {co}")
    return "Articles:\n" + "\n".join(lines) + "\n\nReturn the same-event groups."


def cluster_events(client, mentions: list, model: str = CLASSIFY_MODEL) -> list:
    """Return a list of index-groups; identity clustering (all singletons) on failure."""
    n = len(mentions)
    if n < 2:
        return [[i] for i in range(n)]
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=2000,
            system=DEDUP_SYSTEM,
            messages=[{"role": "user", "content": build_dedup_prompt(mentions)}],
            output_format=Clusters,
        )
        raw = [g.ids for g in resp.parsed_output.groups]
    except Exception as e:  # noqa: BLE001
        log.warning("event clustering failed: %s", e)
        return [[i] for i in range(n)]

    # Defensive: keep each valid id once; any id the model dropped becomes a singleton.
    seen: set = set()
    clean = []
    for group in raw:
        g = [i for i in group if isinstance(i, int) and 0 <= i < n and i not in seen]
        seen.update(g)
        if g:
            clean.append(g)
    for i in range(n):
        if i not in seen:
            clean.append([i])
    return clean


def mark_duplicates(client, week_mentions: list, model: str = CLASSIFY_MODEL) -> int:
    """Cluster a week's stories by event; keep the best per cluster, mark the rest
    as duplicates. Returns how many were marked. Recomputed fresh each call."""
    for m in week_mentions:
        m.duplicate = False
    if len(week_mentions) < 2:
        return 0
    dropped = 0
    for group in cluster_events(client, week_mentions, model=model):
        if len(group) < 2:
            continue
        members = rank_mentions([week_mentions[i] for i in group])   # best first
        for m in members[1:]:
            m.duplicate = True
            dropped += 1
    return dropped
