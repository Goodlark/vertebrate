from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import List

from pydantic import BaseModel

import store
from config import CLASSIFY_MODEL

log = logging.getLogger("pressmonitor.dedup")

# Words that don't identify a specific organization, so they must not group two
# unrelated entities into one big blob. Excludes corporate suffixes AND common
# geographic / institutional words (e.g. "Korea Advanced Institute of Science and
# Technology" should link on a distinctive token or a person's name, not on "korea").
GENERIC_ENTITY_TOKENS = {
    # corporate / descriptive
    "robotics", "robotic", "ventures", "venture", "technologies", "technology", "inc",
    "corp", "corporation", "llc", "ltd", "systems", "system", "labs", "lab", "company",
    "group", "holdings", "motors", "motor", "aviation", "dynamics", "intelligence", "ai",
    "the", "global", "industries", "industry", "international", "aerospace", "capital",
    "partners", "automation", "mobility", "auto", "tech", "co", "and", "solutions",
    # geographic / institutional / governmental
    "korea", "korean", "china", "chinese", "japan", "japanese", "usa", "american",
    "america", "european", "europe", "national", "state", "federal", "navy", "army",
    "air", "force", "marine", "defense", "defence", "military", "university", "college",
    "institute", "science", "sciences", "school", "department", "agency", "administration",
    "development", "republic", "ministry", "city", "county", "new", "york", "first",
    "world", "us", "uk", "german", "germany", "french", "france",
}

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


def _entity_tokens(m) -> set:
    """Specific (non-generic) name tokens of a story's companies + people."""
    toks = set()
    for e in list(m.companies) + list(m.people):
        for w in re.findall(r"[a-z0-9]+", str(e).lower()):
            if len(w) > 2 and w not in GENERIC_ENTITY_TOKENS:
                toks.add(w)
    return toks


def _entity_groups(mentions: list) -> list:
    """Connected components of stories that share a specific company/person token.
    Same-event coverage almost always shares the subject, so this narrows the event
    clustering to small, same-subject groups — reliable no matter how big the week."""
    parent = list(range(len(mentions)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    token_first = {}
    for i, m in enumerate(mentions):
        for t in _entity_tokens(m):
            if t in token_first:
                parent[find(i)] = find(token_first[t])
            else:
                token_first[t] = i

    groups = {}
    for i in range(len(mentions)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


_CAT_RANK = {"launch": 5, "funding": 4, "research": 3, "opinion": 2, "other": 1}


def _keep_key(m):
    """Sort key that keeps the EARLIEST day (so old news never resurfaces later), and
    within a day the most important / most complete story as the representative."""
    return ((m.first_seen or "")[:10], -_CAT_RANK.get(m.category, 0), -len(m.one_line or ""))


def _recent_cutoff(mentions: list, days: int) -> str:
    dates = [(m.first_seen or "")[:10] for m in mentions if m.first_seen]
    if not dates:
        return ""
    try:
        y, mo, d = map(int, max(dates).split("-"))
        return (date(y, mo, d) - timedelta(days=days)).isoformat()
    except ValueError:
        return ""


def mark_duplicates(client, mentions: list, model: str = CLASSIFY_MODEL,
                    llm_window_days: int = 10) -> int:
    """Flag same-event duplicates across ALL stored stories, keeping the earliest of
    each event so the same news never reappears on a later day. Two passes:
    (1) a conservative textual pass over everything, then (2) a semantic LLM pass that
    clusters recent stories sharing a distinctive company/person. Fresh each call."""
    for m in mentions:
        m.duplicate = False
    if len(mentions) < 2:
        return 0
    dropped = 0

    # (1) Textual pass, earliest-first: a later story that clearly repeats an earlier
    # one (same event, similar headline) is flagged; the earlier one is kept.
    kept = []
    for m in sorted(mentions, key=_keep_key):
        if any(store._is_duplicate(m, k) for k in kept):
            m.duplicate = True
            dropped += 1
        else:
            kept.append(m)

    # (2) Semantic pass over recent, still-kept stories: group by a distinctive shared
    # entity (small groups → reliable), then let the model merge same-event stories.
    cutoff = _recent_cutoff(mentions, llm_window_days)
    survivors = [m for m in mentions if not m.duplicate and (m.first_seen or "")[:10] >= cutoff]
    for group in _entity_groups(survivors):
        if len(group) < 2:
            continue
        sub = [survivors[i] for i in group]
        for cluster in cluster_events(client, sub, model=model):
            if len(cluster) < 2:
                continue
            members = sorted((sub[i] for i in cluster), key=_keep_key)   # keep earliest
            for m in members[1:]:
                if not m.duplicate:
                    m.duplicate = True
                    dropped += 1
    return dropped
