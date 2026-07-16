# Press Monitor → verterbrate.ai — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python static-site press monitor that fetches Google News RSS for a watchlist, uses Claude to judge relevance / classify / extract tags / write copy, stores results in flat JSON, and publishes a retro-newspaper website (plus a weekly editorial) to GitHub Pages.

**Architecture:** A small set of single-purpose modules at the repo root wired together by a `monitor.py` CLI. Data lives in flat JSON files (`data/mentions.json`, `data/weeks.json`); the site is rendered by Jinja2 into `docs/` and served by GitHub Pages. Two Claude tiers: Haiku 4.5 for per-article triage, Sonnet 5 for the weekly editorial. No server, no database.

**Tech Stack:** Python 3.9+, `anthropic` (SDK, structured outputs via `messages.parse`), `pydantic` v2, `feedparser`, `PyYAML`, `python-dotenv`, `Jinja2`; `pytest` for tests.

**Design spec:** `superpowers/specs/2026-07-15-press-monitor-verterbrate-design.md`
**Locked look (reference):** `mocks/final-home.html`, `mocks/final-weekly.html`

## Global Constraints

Every task's requirements implicitly include these:

- **Python 3.9+ compatible.** No `match`/`case` (3.10+). Use `from __future__ import annotations` at the top of each module for clean type hints.
- **Model IDs (exact strings):** classify = `claude-haiku-4-5`; weekly = `claude-sonnet-5`.
- **Strict JSON via structured outputs:** use `client.messages.parse(..., output_format=<PydanticModel>)` → `response.parsed_output`. **No assistant-message prefills** (rejected on these models).
- **Secrets:** never hardcode the key. Construct the client with bare `anthropic.Anthropic()` — it reads `ANTHROPIC_API_KEY` from the environment. `config.load_env()` loads `.env` first.
- **Voice (verbatim brief, reused in prompts):** "Write in the register of a thoughtful New Yorker reporter: sophisticated but easy to read, observed, dry, with a point of view. Never press-release hype or hedging. Prefer one vivid, concrete image over three adjectives."
- **Flat files only:** `data/mentions.json`, `data/weeks.json`. No database.
- **Site output → `docs/`** (GitHub Pages serves `/docs`). Always write `docs/CNAME` containing `verterbrate.ai`.
- **Cost guards:** per-topic cap = 25 articles; snippet truncation = 500 chars; classify `max_tokens=400`.
- **Resilience:** one clear error message per whole-run failure mode (missing key, malformed YAML); a single article/mention that errors is **skipped and logged**, never crashing the run or the site build.
- **Readability:** simple, commented code — the owner reads it to learn. One responsibility per module.
- **Aesthetic:** reproduce the warm-manila newspaper look from the committed mocks exactly (palette `#ecdcb6` paper, `#241d12` ink, `#6a5b3e` muted, `#b7a377` rule, `#b1332a` stamp; fonts Archivo Black / Special Elite / Source Serif 4).

## File Structure

| Path | Responsibility |
|------|----------------|
| `config.py` | Load `.env` + `watchlist.yaml`; constants; `ConfigError`; API-key check. |
| `feeds.py` | Build Google News RSS URLs; fetch + normalize articles (`feedparser`). |
| `store.py` | Load/save `data/*.json`; dedup; tag normalization; ISO-week helpers; `Mention` record. |
| `classify.py` | Haiku 4.5 per-article assessment → `Assessment` (strict JSON). |
| `weekly.py` | Sonnet 5 weekly rollup → lede + per-mention "why it matters". |
| `site.py` | Jinja2 render → `docs/` (home, weekly editions + archive, tag pages, CSS, CNAME). |
| `monitor.py` | CLI orchestrator: daily ingest (default) and `--weekly`. |
| `templates/` | Jinja2 templates + `style.css`. |
| `tests/` | Unit tests (Anthropic client mocked). |
| `watchlist.yaml`, `requirements.txt`, `README.md`, `.env.example` | Config, deps, docs. |

---

### Task 1: Scaffold — dependencies, watchlist, test harness

**Files:**
- Create: `requirements.txt`
- Create: `watchlist.yaml`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Produces: a working `pytest` run and installable deps. Nothing importable yet.

- [ ] **Step 1: Write `requirements.txt`**

```text
anthropic>=0.40
pydantic>=2.6
feedparser>=6.0
PyYAML>=6.0
python-dotenv>=1.0
Jinja2>=3.1
pytest>=8.0
```

- [ ] **Step 2: Write `watchlist.yaml` (sample the owner edits by hand)**

```yaml
# Each topic becomes a Google News RSS search. `keywords` is passed verbatim as
# the query, so you can use quotes and OR exactly like Google News search.
topics:
  - name: Physical AI
    keywords: '"physical AI" OR "embodied AI" OR humanoid robot'
  - name: Driverless
    keywords: 'Waymo OR robotaxi OR driverless OR "self-driving"'
  - name: Drones
    keywords: 'autonomous drone OR Skydio OR "drone delivery"'
```

- [ ] **Step 3: Write `tests/conftest.py` (put repo root on the import path)**

```python
import os
import sys

# Modules live at the repo root; make them importable from tests/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

- [ ] **Step 4: Write `tests/test_smoke.py`**

```python
def test_harness_runs():
    assert True
```

- [ ] **Step 5: Install deps and run tests**

Run:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```
Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt watchlist.yaml tests/conftest.py tests/test_smoke.py
git commit -m "chore: scaffold deps, sample watchlist, test harness"
```

---

### Task 2: `config.py` — env, watchlist, constants

**Files:**
- Create: `config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - Constants: `SNIPPET_MAX_CHARS=500`, `PER_TOPIC_LIMIT=25`, `CLASSIFY_MODEL="claude-haiku-4-5"`, `WEEKLY_MODEL="claude-sonnet-5"`, `SITE_TITLE="VERTERBRATE.ai"`, `SITE_TAGLINE="the first ai-powered media"`, `DOMAIN="verterbrate.ai"`, `CLASSIFY_MAX_TOKENS=400`, `WEEKLY_MAX_TOKENS=8000`.
  - `class ConfigError(Exception)`
  - `@dataclass(frozen=True) Topic(name: str, keywords: str)`
  - `load_env(path: str = ".env") -> None`
  - `require_api_key() -> str`
  - `load_watchlist(path: str = "watchlist.yaml") -> list[Topic]`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
import pytest
import config


def test_load_watchlist_parses_topics(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("topics:\n  - name: A\n    keywords: 'x OR y'\n")
    topics = config.load_watchlist(str(p))
    assert len(topics) == 1
    assert topics[0].name == "A"
    assert topics[0].keywords == "x OR y"


def test_load_watchlist_bad_yaml_raises_configerror(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("topics: [unterminated\n")
    with pytest.raises(config.ConfigError):
        config.load_watchlist(str(p))


def test_load_watchlist_missing_fields_raises(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("topics:\n  - name: A\n")  # no keywords
    with pytest.raises(config.ConfigError):
        config.load_watchlist(str(p))


def test_require_api_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(config.ConfigError):
        config.require_api_key()


def test_require_api_key_returns_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert config.require_api_key() == "sk-ant-test"
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'config'`).

- [ ] **Step 3: Write `config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml
from dotenv import load_dotenv

# --- Tunables (kept here so the owner can find and change them in one place) ---
SNIPPET_MAX_CHARS = 500
PER_TOPIC_LIMIT = 25
CLASSIFY_MODEL = "claude-haiku-4-5"      # cheap, high-volume daily triage
WEEKLY_MODEL = "claude-sonnet-5"         # sharper prose for the weekly editorial
CLASSIFY_MAX_TOKENS = 400
WEEKLY_MAX_TOKENS = 8000
SITE_TITLE = "VERTERBRATE.ai"
SITE_TAGLINE = "the first ai-powered media"
DOMAIN = "verterbrate.ai"


class ConfigError(Exception):
    """Raised for any user-fixable configuration problem, with a clear message."""


@dataclass(frozen=True)
class Topic:
    name: str
    keywords: str


def load_env(path: str = ".env") -> None:
    """Load ANTHROPIC_API_KEY (and anything else) from a local .env file."""
    load_dotenv(path)


def require_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return key


def load_watchlist(path: str = "watchlist.yaml") -> list[Topic]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"Watchlist not found at {path}.")
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} is not valid YAML: {e}")

    if not isinstance(data, dict) or "topics" not in data:
        raise ConfigError(f"{path} must have a top-level 'topics:' list.")

    topics = []
    for i, raw in enumerate(data["topics"] or []):
        if not isinstance(raw, dict) or "name" not in raw or "keywords" not in raw:
            raise ConfigError(
                f"{path} topic #{i + 1} must have both 'name' and 'keywords'."
            )
        topics.append(Topic(name=str(raw["name"]), keywords=str(raw["keywords"])))
    if not topics:
        raise ConfigError(f"{path} has no topics — add at least one.")
    return topics
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_config.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config loader (env, watchlist, constants)"
```

---

### Task 3: `feeds.py` — Google News RSS → articles

**Files:**
- Create: `feeds.py`
- Test: `tests/test_feeds.py`

**Interfaces:**
- Consumes: `config.Topic`, `config.PER_TOPIC_LIMIT`, `config.SNIPPET_MAX_CHARS`.
- Produces:
  - `@dataclass(frozen=True) Article(title: str, url: str, source: str, published: str, snippet: str)`
  - `google_news_rss_url(keywords: str) -> str`
  - `parse_entries(parsed, limit: int, snippet_max: int) -> list[Article]` (pure; `parsed` is a feedparser result-like object with `.entries`)
  - `fetch_topic(topic: Topic, limit: int = PER_TOPIC_LIMIT, snippet_max: int = SNIPPET_MAX_CHARS) -> list[Article]`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_feeds.py
from types import SimpleNamespace

import feeds


def _entry(title, link, summary="", source_title=None, published=""):
    e = SimpleNamespace(title=title, link=link, summary=summary, published=published)
    if source_title is not None:
        e.source = SimpleNamespace(title=source_title)
    return e


def test_url_encodes_keywords():
    url = feeds.google_news_rss_url('"physical AI" OR humanoid')
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "physical" in url and "%22" in url  # quotes percent-encoded


def test_parse_entries_limits_and_truncates():
    parsed = SimpleNamespace(entries=[
        _entry("A", "http://a", summary="<b>" + "x" * 999 + "</b>", source_title="The Verge"),
        _entry("B", "http://b", summary="short", source_title="Bloomberg"),
        _entry("C", "http://c", summary="", source_title="Wired"),
    ])
    out = feeds.parse_entries(parsed, limit=2, snippet_max=500)
    assert len(out) == 2
    assert out[0].title == "A"
    assert out[0].url == "http://a"
    assert out[0].source == "The Verge"
    assert len(out[0].snippet) <= 500       # truncated
    assert "<b>" not in out[0].snippet       # HTML stripped


def test_parse_entries_source_fallback_from_title_suffix():
    parsed = SimpleNamespace(entries=[_entry("Headline - Reuters", "http://r")])
    out = feeds.parse_entries(parsed, limit=10, snippet_max=500)
    assert out[0].source == "Reuters"
    assert out[0].title == "Headline"
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_feeds.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'feeds'`).

- [ ] **Step 3: Write `feeds.py`**

```python
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


def _title_and_source(entry) -> tuple[str, str]:
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


def parse_entries(parsed, limit: int, snippet_max: int) -> list[Article]:
    articles: list[Article] = []
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
                snippet_max: int = SNIPPET_MAX_CHARS) -> list[Article]:
    """Fetch one topic's feed. Returns [] on failure (caller logs); never raises."""
    parsed = feedparser.parse(google_news_rss_url(topic.keywords))
    return parse_entries(parsed, limit, snippet_max)
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_feeds.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add feeds.py tests/test_feeds.py
git commit -m "feat: Google News RSS fetch and article normalization"
```

---

### Task 4: `store.py` — records, dedup, JSON, ISO weeks

**Files:**
- Create: `store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `feeds.Article`.
- Produces:
  - `@dataclass Mention(url, title, source, published, topic, category, one_line, companies: list, people: list, themes: list, first_seen, week, why: Optional[str] = None)` with `.to_dict()` and `staticmethod from_dict(d)`.
  - `iso_week(dt: datetime) -> str` → `"YYYY-Www"`
  - `normalize_tags(tags: list[str]) -> list[str]`
  - `load_mentions(path="data/mentions.json") -> list[Mention]`
  - `save_mentions(mentions, path="data/mentions.json") -> None`
  - `known_urls(mentions) -> set[str]`
  - `filter_new(articles, known: set[str]) -> list[Article]`
  - `mentions_for_week(mentions, week: str) -> list[Mention]`
  - `load_weeks(path="data/weeks.json") -> dict`
  - `save_weeks(weeks, path="data/weeks.json") -> None`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_store.py
from datetime import datetime

import store
from feeds import Article


def _mention(url, week="2026-W29", why=None):
    return store.Mention(
        url=url, title="T", source="S", published="", topic="Physical AI",
        category="launch", one_line="one", companies=["Figure"], people=["Musk"],
        themes=["humanoid"], first_seen="2026-07-15T00:00:00", week=week, why=why,
    )


def test_iso_week_format():
    assert store.iso_week(datetime(2026, 7, 15)) == "2026-W29"


def test_normalize_tags_dedupes_case_insensitively_keeping_first():
    assert store.normalize_tags([" Figure ", "figure", "Waymo"]) == ["Figure", "Waymo"]


def test_filter_new_drops_known_urls():
    arts = [Article("A", "http://a", "S", "", ""), Article("B", "http://b", "S", "", "")]
    assert [a.url for a in store.filter_new(arts, {"http://a"})] == ["http://b"]


def test_mentions_roundtrip_json(tmp_path):
    p = tmp_path / "m.json"
    store.save_mentions([_mention("http://a")], str(p))
    loaded = store.load_mentions(str(p))
    assert len(loaded) == 1
    assert loaded[0].url == "http://a"
    assert loaded[0].companies == ["Figure"]


def test_load_mentions_missing_file_returns_empty(tmp_path):
    assert store.load_mentions(str(tmp_path / "nope.json")) == []


def test_mentions_for_week_filters():
    ms = [_mention("http://a", week="2026-W29"), _mention("http://b", week="2026-W28")]
    got = store.mentions_for_week(ms, "2026-W29")
    assert [m.url for m in got] == ["http://a"]


def test_weeks_roundtrip(tmp_path):
    p = tmp_path / "w.json"
    store.save_weeks({"2026-W29": {"lede": "hi"}}, str(p))
    assert store.load_weeks(str(p))["2026-W29"]["lede"] == "hi"
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_store.py -q`
Expected: FAIL (`No module named 'store'`).

- [ ] **Step 3: Write `store.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

from feeds import Article


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
    seen: dict[str, str] = {}
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
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_store.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat: flat-file store, dedup, tag normalization, ISO weeks"
```

---

### Task 5: `classify.py` — Haiku 4.5 per-article assessment

**Files:**
- Create: `classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: `feeds.Article`, `config.CLASSIFY_MODEL`, `config.CLASSIFY_MAX_TOKENS`.
- Produces:
  - `class Assessment(BaseModel)` with fields `relevant: bool`, `category: Literal["launch","funding","research","opinion","other"]`, `one_line: str`, `companies: list[str]`, `people: list[str]`, `themes: list[str]`.
  - `build_user_prompt(article: Article, topic_name: str) -> str`
  - `assess(client, article: Article, topic_name: str, model: str = CLASSIFY_MODEL) -> Optional[Assessment]`

- [ ] **Step 1: Write failing tests** (client is mocked — no network, no cost)

```python
# tests/test_classify.py
from types import SimpleNamespace
from unittest.mock import MagicMock

import classify
from feeds import Article

ART = Article("Figure hits BMW line", "http://x", "The Verge", "", "snippet")


def _mock_client(assessment):
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=assessment)
    return client


def test_assess_returns_parsed_output():
    a = classify.Assessment(relevant=True, category="launch", one_line="hi",
                            companies=["Figure"], people=[], themes=["humanoid"])
    client = _mock_client(a)
    out = classify.assess(client, ART, "Physical AI")
    assert out is a
    # It called the cheap model with our structured-output type.
    _, kwargs = client.messages.parse.call_args
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["output_format"] is classify.Assessment


def test_assess_returns_none_on_error():
    client = MagicMock()
    client.messages.parse.side_effect = RuntimeError("boom")
    assert classify.assess(client, ART, "Physical AI") is None


def test_build_user_prompt_includes_topic_and_title():
    p = classify.build_user_prompt(ART, "Physical AI")
    assert "Physical AI" in p and "Figure hits BMW line" in p
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_classify.py -q`
Expected: FAIL (`No module named 'classify'`).

- [ ] **Step 3: Write `classify.py`**

```python
from __future__ import annotations

import logging
from typing import List, Literal, Optional

from pydantic import BaseModel

from config import CLASSIFY_MAX_TOKENS, CLASSIFY_MODEL
from feeds import Article

log = logging.getLogger("pressmonitor.classify")

VOICE = (
    "Write in the register of a thoughtful New Yorker reporter: sophisticated but "
    "easy to read, observed, dry, with a point of view. Never press-release hype or "
    "hedging. Prefer one vivid, concrete image over three adjectives."
)

CLASSIFY_SYSTEM = (
    "You are the desk editor for an AI-and-robotics news monitor. For one article, "
    "decide if it is genuinely about the given topic (not keyword noise), classify it, "
    "and write a single sharp sentence. Also extract named companies, named people, and "
    "short thematic tags (e.g. 'driverless', 'humanoid', 'physical AI', 'drone').\n\n"
    f"one_line voice: {VOICE}"
)


class Assessment(BaseModel):
    relevant: bool
    category: Literal["launch", "funding", "research", "opinion", "other"]
    one_line: str
    companies: List[str]
    people: List[str]
    themes: List[str]


def build_user_prompt(article: Article, topic_name: str) -> str:
    return (
        f"Topic: {topic_name}\n"
        f"Headline: {article.title}\n"
        f"Source: {article.source}\n"
        f"Snippet: {article.snippet}\n\n"
        "Assess this article for the topic above."
    )


def assess(client, article: Article, topic_name: str,
           model: str = CLASSIFY_MODEL) -> Optional[Assessment]:
    """Return an Assessment, or None if the call/parse fails (skip-and-log)."""
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=CLASSIFY_MAX_TOKENS,
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": build_user_prompt(article, topic_name)}],
            output_format=Assessment,
        )
        return resp.parsed_output
    except Exception as e:  # noqa: BLE001 — one bad article must never crash the run
        log.warning("classify failed for %s: %s", article.url, e)
        return None
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_classify.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add classify.py tests/test_classify.py
git commit -m "feat: Haiku 4.5 article classifier with strict JSON output"
```

---

### Task 6: `weekly.py` — Sonnet 5 weekly rollup

**Files:**
- Create: `weekly.py`
- Test: `tests/test_weekly.py`

**Interfaces:**
- Consumes: `store.Mention`, `config.WEEKLY_MODEL`, `config.WEEKLY_MAX_TOKENS`.
- Produces:
  - `class WhyEntry(BaseModel)`: `url: str`, `why: str`
  - `class WeeklyRollup(BaseModel)`: `lede: str`, `entries: list[WhyEntry]`
  - `build_weekly_prompt(mentions: list) -> str`
  - `write_weekly(client, mentions: list, model: str = WEEKLY_MODEL) -> Optional[WeeklyRollup]`
  - `apply_rollup(mentions: list, rollup: WeeklyRollup) -> None` (sets `.why` in place by URL match)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_weekly.py
from types import SimpleNamespace
from unittest.mock import MagicMock

import weekly
import store


def _m(url):
    return store.Mention(url=url, title="T", source="S", published="", topic="Physical AI",
                         category="launch", one_line="one", first_seen="", week="2026-W29")


def test_write_weekly_uses_sonnet_and_returns_rollup():
    roll = weekly.WeeklyRollup(lede="The week...", entries=[weekly.WhyEntry(url="http://a", why="because")])
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=roll)
    out = weekly.write_weekly(client, [_m("http://a")])
    assert out.lede.startswith("The week")
    _, kwargs = client.messages.parse.call_args
    assert kwargs["model"] == "claude-sonnet-5"


def test_write_weekly_returns_none_on_error():
    client = MagicMock()
    client.messages.parse.side_effect = RuntimeError("boom")
    assert weekly.write_weekly(client, [_m("http://a")]) is None


def test_apply_rollup_sets_why_by_url():
    ms = [_m("http://a"), _m("http://b")]
    roll = weekly.WeeklyRollup(lede="x", entries=[weekly.WhyEntry(url="http://a", why="deep")])
    weekly.apply_rollup(ms, roll)
    assert ms[0].why == "deep"
    assert ms[1].why is None
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_weekly.py -q`
Expected: FAIL (`No module named 'weekly'`).

- [ ] **Step 3: Write `weekly.py`**

```python
from __future__ import annotations

import logging
from typing import List, Optional

from pydantic import BaseModel

from config import WEEKLY_MAX_TOKENS, WEEKLY_MODEL

log = logging.getLogger("pressmonitor.weekly")

VOICE = (
    "Write in the register of a thoughtful New Yorker reporter: sophisticated but "
    "easy to read, observed, dry, with a point of view. Never press-release hype or "
    "hedging. Prefer one vivid, concrete image over three adjectives."
)

WEEKLY_SYSTEM = (
    "You write the weekly edition of an AI-and-robotics newspaper. You are given the "
    "week's mentions. Produce (1) an editor's-note 'lede' of 2-3 sentences framing the "
    "week, and (2) for each mention, a 'why it matters' explainer of 2-3 sentences — what "
    "changed, who it pressures, what to watch. Return one entry per mention, keyed by its "
    "exact url.\n\n"
    f"Voice: {VOICE}"
)


class WhyEntry(BaseModel):
    url: str
    why: str


class WeeklyRollup(BaseModel):
    lede: str
    entries: List[WhyEntry]


def build_weekly_prompt(mentions: list) -> str:
    lines = ["This week's mentions:\n"]
    for m in mentions:
        lines.append(
            f"- url: {m.url}\n  headline: {m.title}\n  source: {m.source}\n"
            f"  topic: {m.topic}\n  category: {m.category}\n  note: {m.one_line}"
        )
    lines.append("\nWrite the lede and one why-it-matters per url above.")
    return "\n".join(lines)


def write_weekly(client, mentions: list, model: str = WEEKLY_MODEL) -> Optional[WeeklyRollup]:
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=WEEKLY_MAX_TOKENS,
            system=WEEKLY_SYSTEM,
            messages=[{"role": "user", "content": build_weekly_prompt(mentions)}],
            output_format=WeeklyRollup,
        )
        return resp.parsed_output
    except Exception as e:  # noqa: BLE001
        log.warning("weekly rollup failed: %s", e)
        return None


def apply_rollup(mentions: list, rollup: WeeklyRollup) -> None:
    why_by_url = {e.url: e.why for e in rollup.entries}
    for m in mentions:
        if m.url in why_by_url:
            m.why = why_by_url[m.url]
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_weekly.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add weekly.py tests/test_weekly.py
git commit -m "feat: Sonnet 5 weekly rollup (lede + why-it-matters)"
```

---

### Task 7: `site.py` — pure rendering helpers

**Files:**
- Create: `site.py` (helpers only in this task; `build_site` added in Task 8)
- Test: `tests/test_site_helpers.py`

**Interfaces:**
- Consumes: `store.Mention`.
- Produces:
  - `@dataclass TagCount(label: str, kind: str, count: int, slug: str)` (`kind` ∈ `"company" | "person" | "theme"`)
  - `slugify(text: str) -> str`
  - `size_class(count: int, max_count: int) -> str` → one of `"s1".."s5"`
  - `build_tag_index(mentions: list) -> list[TagCount]` (sorted by count desc, then label)
  - `group_by_topic(mentions: list) -> "collections.OrderedDict[str, list]"`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_site_helpers.py
import site as sitemod
import store


def _m(url, topic="Physical AI", companies=None, people=None, themes=None):
    return store.Mention(url=url, title="T", source="S", published="", topic=topic,
                         category="launch", one_line="one", companies=companies or [],
                         people=people or [], themes=themes or [], first_seen="", week="2026-W29")


def test_slugify():
    assert sitemod.slugify("Physical AI") == "physical-ai"
    assert sitemod.slugify("  Fei-Fei Li ") == "fei-fei-li"


def test_size_class_scales():
    assert sitemod.size_class(1, 10) == "s1"
    assert sitemod.size_class(10, 10) == "s5"


def test_build_tag_index_counts_and_kinds():
    ms = [_m("a", companies=["Figure"], themes=["humanoid"]),
          _m("b", companies=["Figure"], people=["Musk"])]
    idx = {t.label: t for t in sitemod.build_tag_index(ms)}
    assert idx["Figure"].count == 2 and idx["Figure"].kind == "company"
    assert idx["Musk"].kind == "person"
    assert idx["humanoid"].kind == "theme"
    # highest count sorts first
    assert sitemod.build_tag_index(ms)[0].label == "Figure"


def test_group_by_topic_preserves_first_seen_order():
    ms = [_m("a", topic="Driverless"), _m("b", topic="Physical AI"), _m("c", topic="Driverless")]
    grouped = sitemod.group_by_topic(ms)
    assert list(grouped.keys()) == ["Driverless", "Physical AI"]
    assert [m.url for m in grouped["Driverless"]] == ["a", "c"]
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_site_helpers.py -q`
Expected: FAIL (`No module named 'site'` — note: our local `site.py` shadows the stdlib `site` inside this project, which is fine because tests run with the repo root first on `sys.path`).

- [ ] **Step 3: Write `site.py` (helpers)**

```python
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class TagCount:
    label: str
    kind: str  # "company" | "person" | "theme"
    count: int
    slug: str


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
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_site_helpers.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add site.py tests/test_site_helpers.py
git commit -m "feat: site rendering helpers (slug, tag index, grouping)"
```

---

### Task 8: Templates + `build_site`

**Files:**
- Create: `templates/style.css`
- Create: `templates/base.html`, `templates/index.html`, `templates/weekly_edition.html`, `templates/weekly_index.html`, `templates/tag.html`
- Modify: `site.py` (add `build_site`)
- Test: `tests/test_build_site.py`

**Interfaces:**
- Consumes: `store.Mention`, the Task 7 helpers, `config.SITE_TITLE/SITE_TAGLINE/DOMAIN`.
- Produces: `build_site(mentions: list, weeks: dict, out_dir: str = "docs", templates_dir: str = "templates") -> None`

**Look source:** `templates/style.css` is the consolidated `<style>` blocks from the two committed mocks. Copy the CSS rules from `mocks/final-home.html` (masthead, topbar, nav.sections, teaser, feed, item, aside/index-box, cloud + `.co/.pe/.th/.s1..s5`, foot, paper background + speckle) and add the weekly-only rules from `mocks/final-weekly.html` (`.masthead .kicker`, `.editionline`, `.lede`, `.sec`, `.entry`, `.why`, `.why .lead-in`). Keep the palette/fonts identical. The templates below use the same class names as the mocks so the lifted CSS applies unchanged.

- [ ] **Step 1: Write failing test**

```python
# tests/test_build_site.py
import site as sitemod
import store


def _m(url, topic="Physical AI", why=None):
    return store.Mention(url=url, title="Figure hits the line", source="The Verge",
                         published="", topic=topic, category="launch",
                         one_line="A sharp sentence.", companies=["Figure"], people=["Musk"],
                         themes=["humanoid"], first_seen="2026-07-15T00:00:00",
                         week="2026-W29", why=why)


def test_build_site_writes_expected_files(tmp_path):
    out = tmp_path / "docs"
    mentions = [_m("http://a", why="Because it matters.")]
    weeks = {"2026-W29": {"lede": "The week the humanoid clocked in."}}
    sitemod.build_site(mentions, weeks, out_dir=str(out), templates_dir="templates")

    index = (out / "index.html").read_text(encoding="utf-8")
    assert "VERTERBRATE" in index
    assert "Figure hits the line" in index      # feed item
    assert "Figure" in index                     # tag index

    assert (out / "CNAME").read_text().strip() == "verterbrate.ai"
    assert (out / "style.css").exists()

    weekly = (out / "weekly" / "2026-W29.html").read_text(encoding="utf-8")
    assert "The week the humanoid clocked in." in weekly
    assert "Because it matters." in weekly       # why-it-matters

    assert (out / "weekly" / "index.html").exists()
    assert (out / "tag" / "figure.html").exists()  # slug of "Figure"
```

- [ ] **Step 2: Run test — expect failure**

Run: `pytest tests/test_build_site.py -q`
Expected: FAIL (`AttributeError: module 'site' has no attribute 'build_site'`).

- [ ] **Step 3: Create `templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}{{ site_title }}{% endblock %}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Special+Elite&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{{ root }}style.css">
</head>
<body>
<div class="wrap">
{% block body %}{% endblock %}
</div>
</body>
</html>
```

Note: `root` is a relative prefix (`""` for pages in `docs/`, `"../"` for pages one level down like `weekly/` and `tag/`) so the single stylesheet resolves from every page.

- [ ] **Step 4: Create `templates/index.html`**

```html
{% extends "base.html" %}
{% block body %}
  <div class="topbar"><span>WIRE</span><span>THE AUTONOMOUS DESK</span><span>{{ today }}</span></div>
  <header class="masthead">
    <div class="stamp"><div class="big">EST.</div><div class="yr">2026</div><div class="sm">AUTONOMOUS · DESK</div></div>
    <h1>VERTERBRATE<span class="ai">.ai</span></h1>
    <div class="tag">{{ site_tagline }}</div>
  </header>
  <nav class="sections">
    <a class="on" href="{{ root }}index.html">Today’s Feed</a>
    <a href="{{ root }}weekly/index.html">The Weekly</a>
  </nav>
  {% if latest_week %}
  <div class="teaser">
    <div class="flag">THE WEEKLY<br><small>{{ latest_week }}</small></div>
    <div class="dek">{{ latest_lede }}</div>
    <a class="read" href="{{ root }}weekly/{{ latest_week }}.html">Read the edition →</a>
  </div>
  {% endif %}
  <div class="stripline">· Today’s Dispatches · read by machine, written to be read ·</div>
  <div class="body">
    <div class="feed">
      {% for m in mentions %}
      <article class="item">
        <div class="meta"><span class="cat{% if m.category == 'opinion' %} q{% endif %}">{{ m.category|capitalize }}</span></div>
        <div>
          <h2><a href="{{ m.url }}">{{ m.title }}</a></h2>
          <div class="src">// {{ m.source }}</div>
          <p class="oneline">{{ m.one_line }}</p>
        </div>
      </article>
      {% endfor %}
    </div>
    <aside>
      <div class="index-box">
        <div class="hd">The Index</div>
        <div class="cloud">
          {% for t in tags %}<a class="{{ t.kind_class }} {{ t.size }}" href="{{ root }}tag/{{ t.slug }}.html">{{ t.label }}</a> {% endfor %}
        </div>
        <div class="legend"><b>Bold</b> companies · <i>Italic</i> people · <span style="font-family:'Special Elite',monospace">mono</span> themes</div>
      </div>
    </aside>
  </div>
  <div class="foot">COMPILED BY MACHINE · EDITED FOR THE CURIOUS · VERTERBRATE.AI</div>
{% endblock %}
```

- [ ] **Step 5: Create `templates/weekly_edition.html`**

```html
{% extends "base.html" %}
{% block title %}The Weekly {{ week }} — {{ site_title }}{% endblock %}
{% block body %}
  <div class="topbar"><span><a href="{{ root }}index.html">← Today’s Feed</a></span><span>THE AUTONOMOUS DESK</span><span>{{ week }}</span></div>
  <header class="masthead">
    <div class="kicker">THE WEEKLY</div>
    <h1>VERTERBRATE<span class="ai">.ai</span></h1>
    <div class="editionline">{{ week }}</div>
  </header>
  <p class="lede">{{ lede }}</p>
  {% for topic, items in groups.items() %}
  <div class="sec">{{ topic }}</div>
    {% for m in items %}
    <div class="entry">
      <span class="cat{% if m.category == 'opinion' %} q{% endif %}">{{ m.category|capitalize }}</span>
      <h3><a href="{{ m.url }}">{{ m.title }}</a></h3>
      <div class="src">// {{ m.source }}</div>
      {% if m.why %}<p class="why"><span class="lead-in">Why it matters. </span>{{ m.why }}</p>{% endif %}
    </div>
    {% endfor %}
  {% endfor %}
  <div class="foot">COMPILED BY MACHINE · EDITED FOR THE CURIOUS · VERTERBRATE.AI</div>
{% endblock %}
```

- [ ] **Step 6: Create `templates/weekly_index.html`**

```html
{% extends "base.html" %}
{% block title %}The Weekly — Archive — {{ site_title }}{% endblock %}
{% block body %}
  <div class="topbar"><span><a href="{{ root }}index.html">← Today’s Feed</a></span><span>THE WEEKLY · ARCHIVE</span><span></span></div>
  <header class="masthead"><div class="kicker">THE WEEKLY</div><h1>VERTERBRATE<span class="ai">.ai</span></h1></header>
  <div class="sec">Editions</div>
  {% for w in weeks %}
  <div class="entry"><h3><a href="{{ root }}weekly/{{ w }}.html">{{ w }}</a></h3></div>
  {% endfor %}
  <div class="foot">VERTERBRATE.AI</div>
{% endblock %}
```

- [ ] **Step 7: Create `templates/tag.html`**

```html
{% extends "base.html" %}
{% block title %}{{ label }} — {{ site_title }}{% endblock %}
{% block body %}
  <div class="topbar"><span><a href="{{ root }}index.html">← Today’s Feed</a></span><span>THE INDEX</span><span></span></div>
  <header class="masthead"><h1>VERTERBRATE<span class="ai">.ai</span></h1></header>
  <div class="sec">Tagged: {{ label }}</div>
  <div class="feed">
    {% for m in mentions %}
    <article class="item"><div class="meta"><span class="cat">{{ m.category|capitalize }}</span></div>
      <div><h2><a href="{{ m.url }}">{{ m.title }}</a></h2><div class="src">// {{ m.source }}</div>
      <p class="oneline">{{ m.one_line }}</p></div></article>
    {% endfor %}
  </div>
  <div class="foot">VERTERBRATE.AI</div>
{% endblock %}
```

- [ ] **Step 8: Create `templates/style.css`**

Consolidate the CSS as described in "Look source" above: copy the `<style>` rules from `mocks/final-home.html` into this file, then append the weekly-only rules from `mocks/final-weekly.html`. Do **not** invent new class names — the templates already use the mock class names (`wrap`, `topbar`, `masthead`, `stamp`, `sections`, `teaser`, `stripline`, `body`, `feed`, `item`, `meta`, `cat`, `oneline`, `aside`, `index-box`, `cloud`, `co`/`pe`/`th`, `s1`–`s5`, `legend`, `foot`, `kicker`, `editionline`, `lede`, `sec`, `entry`, `why`, `lead-in`). Verify by opening the generated `docs/index.html` in a browser (Task 9 Step 6) — it should match `mocks/final-home.html`.

- [ ] **Step 9: Add `build_site` to `site.py`**

```python
# Append to site.py

import os
import shutil
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import DOMAIN, SITE_TAGLINE, SITE_TITLE

# class -> template CSS class for the three tag kinds
_KIND_CLASS = {"company": "co", "person": "pe", "theme": "th"}


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

    # Newest first for the feed.
    feed = sorted(mentions, key=lambda m: m.first_seen, reverse=True)

    tags = build_tag_index(mentions)
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
            mentions=feed, tags=view_tags, latest_week=latest_week,
            latest_lede=latest_lede, **_common("")))

    # Weekly editions + archive
    weekly_dir = os.path.join(out_dir, "weekly")
    os.makedirs(weekly_dir, exist_ok=True)
    for week_id in week_ids:
        wk_mentions = [m for m in mentions if m.week == week_id]
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
        tagged = [m for m in feed
                  if t.label in (m.companies + m.people + m.themes)]
        with open(os.path.join(tag_dir, f"{t.slug}.html"), "w", encoding="utf-8") as f:
            f.write(env.get_template("tag.html").render(
                label=t.label, mentions=tagged, **_common("../")))

    # Static assets
    shutil.copyfile(os.path.join(templates_dir, "style.css"),
                    os.path.join(out_dir, "style.css"))
    with open(os.path.join(out_dir, "CNAME"), "w", encoding="utf-8") as f:
        f.write(DOMAIN + "\n")
```

- [ ] **Step 10: Run test — expect pass**

Run: `pytest tests/test_build_site.py -q`
Expected: PASS (1 passed).

- [ ] **Step 11: Commit**

```bash
git add site.py templates/ tests/test_build_site.py
git commit -m "feat: Jinja2 templates and static-site builder"
```

---

### Task 9: `monitor.py` — CLI orchestrator

**Files:**
- Create: `monitor.py`
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `run_daily(now: datetime, config_topics: list, client, out_dir="docs", data_dir="data") -> dict`
  - `run_weekly(now: datetime, week: str, client, out_dir="docs", data_dir="data") -> dict`
  - `main(argv=None) -> int`

- [ ] **Step 1: Write failing test** (feeds + Anthropic client both mocked)

```python
# tests/test_monitor.py
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import monitor
import classify
from config import Topic
from feeds import Article


def test_run_daily_writes_data_and_site(tmp_path):
    topics = [Topic("Physical AI", "humanoid")]
    art = Article("Figure hits the line", "http://a", "The Verge", "", "snippet")

    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=classify.Assessment(
        relevant=True, category="launch", one_line="A sharp sentence.",
        companies=["Figure"], people=["Musk"], themes=["humanoid"]))

    data_dir = tmp_path / "data"
    out_dir = tmp_path / "docs"
    with patch("monitor.feeds.fetch_topic", return_value=[art]):
        summary = monitor.run_daily(datetime(2026, 7, 15), topics, client,
                                    out_dir=str(out_dir), data_dir=str(data_dir))

    assert summary["fetched"] == 1 and summary["relevant"] == 1 and summary["added"] == 1
    assert os.path.exists(data_dir / "mentions.json")
    index = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "Figure hits the line" in index


def test_run_daily_skips_irrelevant_and_dedupes(tmp_path):
    topics = [Topic("Physical AI", "humanoid")]
    art = Article("Noise", "http://a", "S", "", "snippet")
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=classify.Assessment(
        relevant=False, category="other", one_line="", companies=[], people=[], themes=[]))
    with patch("monitor.feeds.fetch_topic", return_value=[art]):
        summary = monitor.run_daily(datetime(2026, 7, 15), topics, client,
                                    out_dir=str(tmp_path / "docs"), data_dir=str(tmp_path / "data"))
    assert summary["relevant"] == 0 and summary["added"] == 0
```

- [ ] **Step 2: Run test — expect failure**

Run: `pytest tests/test_monitor.py -q`
Expected: FAIL (`No module named 'monitor'`).

- [ ] **Step 3: Write `monitor.py`**

```python
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
import site
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
            if assessment is None:
                continue
            if not assessment.relevant:
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

    store.save_mentions(mentions, mentions_path)
    site.build_site(mentions, weeks, out_dir=out_dir)
    summary = {"fetched": fetched, "relevant": relevant, "added": added}
    log.info("Daily run — fetched %(fetched)d new / relevant %(relevant)d / added %(added)d", summary)
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

    site.build_site(mentions, weeks, out_dir=out_dir)
    log.info("Weekly run — %s / %d mentions", week, len(wk))
    return {"week": week, "mentions": len(wk)}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="Press Monitor for verterbrate.ai")
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
```

- [ ] **Step 4: Run test — expect pass**

Run: `pytest tests/test_monitor.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 6: Visual smoke-check the real look** (optional but recommended)

Generate a site from the test fixtures once and open it, comparing against `mocks/final-home.html`:
```bash
python -c "from datetime import datetime; import store, site; \
m=[store.Mention(url='http://a',title='Figure hits the line',source='The Verge',published='',topic='Physical AI',category='launch',one_line='A sharp sentence.',companies=['Figure'],people=['Musk'],themes=['humanoid'],first_seen='2026-07-15T00:00:00',week='2026-W29',why='Because it matters.')]; \
site.build_site(m, {'2026-W29':{'lede':'The week the humanoid clocked in.'}}, out_dir='docs')"
open docs/index.html
```
Expected: warm-manila newspaper matching the mock. Fix `templates/style.css` if anything drifted, then delete this throwaway `docs/` output before committing real data (or keep it — it's the site).

- [ ] **Step 7: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "feat: monitor CLI (daily ingest + weekly edition)"
```

---

### Task 10: README + first real run

**Files:**
- Create: `README.md`

**Interfaces:** none (documentation + operational).

- [ ] **Step 1: Write `README.md`**

````markdown
# Press Monitor → verterbrate.ai

A daily press monitor that fetches Google News for your watchlist, uses Claude to
judge relevance / classify / tag / write copy, and publishes a retro-newspaper
website (plus a weekly editorial) to GitHub Pages.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your Anthropic API key into .env
```

Get a key at https://platform.claude.com → API keys. `.env` is gitignored.

## Configure topics

Edit `watchlist.yaml`. Each topic is a Google News search; `keywords` is passed
verbatim, so quotes and `OR` work exactly like the Google News search box.

## Run

```bash
python monitor.py            # daily: fetch, classify, rebuild the site
python monitor.py --weekly   # weekly: write the "why it matters" edition
```

Both commands write files under `docs/` and `data/`. **Publish by committing:**

```bash
git add docs data && git commit -m "update: $(date +%F)" && git push
```

## Publish on verterbrate.ai (one time)

1. Push this repo to GitHub.
2. Settings → Pages → Build and deployment → Source: **Deploy from a branch**,
   Branch: **main** / **/docs**.
3. The build writes `docs/CNAME` (`verterbrate.ai`) for you. In your DNS, point
   the apex domain at GitHub Pages with these `A` records:
   `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   (and an `AAAA`/`www CNAME` per GitHub's current docs).
4. Settings → Pages → Custom domain: `verterbrate.ai`; enable HTTPS.

## Cost

Daily triage runs on Haiku 4.5 with truncated snippets and a 25-article/topic
cap — cents per run. The weekly editorial runs on Sonnet 5 once a week. See the
spec for details.

## Scheduling (later / v2)

Not built in v1 — run the two commands by hand. To automate later, a `cron` job
or a GitHub Actions workflow can run them on a schedule and commit the result.

## Tests

```bash
pytest -q
```
Tests mock the Anthropic client — no network, no cost.
````

- [ ] **Step 2: Commit the docs**

```bash
git add README.md
git commit -m "docs: setup, run, and GitHub Pages deploy guide"
```

- [ ] **Step 3: First real run** (needs a funded key in `.env`)

Run:
```bash
python monitor.py
```
Expected: a run summary line, `data/mentions.json` populated, `docs/` rebuilt.
Open `docs/index.html` to confirm real headlines flow into the newspaper look.
Then optionally `python monitor.py --weekly` and open `docs/weekly/<week>.html`.

- [ ] **Step 4: Commit the first published site**

```bash
git add docs data
git commit -m "content: first published edition"
```

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- Daily pipeline (fetch/dedup/classify/store/build/report) → Tasks 3–5, 8, 9.
- Weekly editorial (lede + why-it-matters) → Task 6, 9.
- Two-tier models (Haiku/Sonnet, exact IDs) → Tasks 5, 6 + Global Constraints.
- Structured outputs / no prefill → Tasks 5, 6.
- Tag extraction (companies/people/themes) + Index cloud + tag pages → Tasks 5, 7, 8.
- Data model (`mentions.json` + `weeks.json`, ISO week, normalization) → Task 4.
- Site look (warm newspaper, masthead, feed, Index, Weekly page) → Task 8 (CSS lifted from committed mocks).
- GitHub Pages publish (docs/, CNAME, DNS) → Task 8 (CNAME), Task 10 (README).
- Error handling (missing key, bad YAML, skip-and-log) → Tasks 2, 5, 6, 9.
- Cost guards (cap, truncation, max_tokens) → Tasks 2, 3, 5.
- Testing (mocked client) → every task's tests.
- Voice → Tasks 5, 6 (verbatim brief in Global Constraints).

**2. Placeholder scan** — the only "lift from an existing file" instruction is the
CSS in Task 8, which points at concrete committed mocks (`mocks/final-*.html`),
not a vague placeholder. All code steps contain runnable code.

**3. Type consistency** — checked across tasks: `Article`, `Mention`,
`Assessment`, `WhyEntry`/`WeeklyRollup`, `TagCount`, and the `build_site` /
`assess` / `write_weekly` / `run_daily` signatures match everywhere they are
consumed.
