# Press Monitor → vertebrate.ai — Design Spec (v1)

_Date: 2026-07-15 · Status: approved design, ready for planning_

## What this is

A daily press-monitoring agent for a PR/communications professional. It fetches
news for a configurable watchlist, uses the Claude API to judge relevance,
classify each item, extract entities, and write copy in a specific voice, then
**publishes the results as a retro-newspaper static website** at
**vertebrate.ai** — "the first AI-powered media." Once a week it also produces
a longer editorial edition, **The Weekly**, that explains why each mention
matters.

There is no server and no database. The monitor writes flat files (JSON data +
static HTML); the website is served by GitHub Pages straight from the repo.

## Owner context

Built by a communications strategist (MS in Computer Science, returning to
hands-on work through agentic tools). **Prioritize simple, readable code over
cleverness.** Explain any non-obvious choice in a comment — the owner will read
the code to learn from it. Small, single-purpose modules are preferred over
clever density.

---

## Core behavior

### Daily cycle — `python monitor.py`

1. **Load config.** Read `watchlist.yaml` (topics, each with a name + search
   keywords) and `.env` (`ANTHROPIC_API_KEY`). One clear error per failure mode
   (see Error Handling).
2. **Fetch.** For each topic, pull recent articles from Google News RSS
   (`https://news.google.com/rss/search?q=KEYWORDS`) using `feedparser` — no API
   key needed. Cap at **25 articles per topic** to bound cost. Normalize each to
   `{title, url, source, published, snippet}`; truncate `snippet` to ~500 chars.
3. **Deduplicate.** Skip any article URL already present in
   `data/mentions.json`.
4. **Classify (Claude Haiku 4.5).** For each new article, one API call using the
   official `anthropic` Python SDK with **structured outputs**
   (`client.messages.parse()` + a Pydantic model) → schema-valid JSON:
   - `relevant: bool` — is this genuinely about the topic, not keyword noise?
   - `category: "launch" | "funding" | "research" | "opinion" | "other"`
   - `one_line: str` — a single, sharp sentence in the house voice (below).
   - `companies: list[str]` — org names mentioned (e.g. `["Waymo", "Figure"]`).
   - `people: list[str]` — notable people (e.g. `["Elon Musk"]`).
   - `themes: list[str]` — thematic tags (e.g. `["driverless", "physical AI",
     "humanoid", "drone", "autonomous"]`).

   If a single item errors or returns off-schema, **skip it and log it** — never
   crash the run.
5. **Store.** Keep items where `relevant == true`; append a record to
   `data/mentions.json` (schema below). Dedup is derived from this file — a URL
   present here counts as "seen."
6. **Build the site.** Regenerate the full static site into `docs/` from
   `data/mentions.json` (+ `data/weeks.json`): homepage feed and the "Index" tag
   cloud. Site generation is deterministic — it always renders the complete site
   from stored data, so re-running is safe and idempotent.
7. **Report.** Print a plain-text run summary: `fetched / relevant / added`.

### Weekly cycle — `python monitor.py --weekly` (optionally `--week YYYY-Www`)

1. Select the target ISO week's relevant mentions (default: the current week).
2. **Editorial (Claude Sonnet 5).** Generate, in the house voice:
   - an **editor's-note lede** (2–3 sentences framing the week), and
   - for each mention, a **"Why it matters"** explainer of 2–3 sentences.
   Use structured outputs here too; skip-and-log any item that fails.
3. Save the lede into `data/weeks.json` (keyed by week) and each `why` back onto
   its mention record.
4. Rebuild the site — this produces/updates `docs/weekly/<week>.html`, the weekly
   archive index, and the homepage teaser.

### Two-tier model choice

- **Haiku 4.5** (`claude-haiku-4-5`) for high-volume daily triage — cheapest
  model that still supports guaranteed schema-valid JSON.
- **Sonnet 5** (`claude-sonnet-5`) for the once-a-week editorial — sharper prose
  where it is reader-facing, and it runs rarely, so cost stays in cents.

_Model IDs and the structured-outputs approach were verified against the current
Claude API reference. `claude-sonnet-4-6` (the model in the original brief) does
**not** support native structured outputs; Haiku 4.5 and Sonnet 5 do. Do not use
assistant-message prefills — they are rejected on these models._

---

## Writing voice (applies to every LLM-written string)

Sophisticated but easy to read — the register of a thoughtful **New Yorker**
reporter: observed, dry, with a point of view, never press-release hype. This
voice governs both the daily `one_line` and the weekly `why`/`lede`.

Reference examples (from the approved mockups):

- one_line: _"For six years the driverless car behaved like a tourist who
  refused the highway; this week, in Phoenix, it finally learned to merge."_
- why-it-matters: _"This is the first time a humanoid robot has taken real,
  repeated factory work at scale rather than posing for a launch video — the
  metric has shifted from 'can it walk' to 'can it pay for itself.'"_

Bake the voice into the prompts as an explicit style brief with 1–2 positive
examples. Keep the daily `one_line` to a single sentence; let the weekly `why`
run 2–3.

---

## The website (design — approved)

**Aesthetic:** retro newspaper on warm, aged-manila stock.

- Palette: paper `#ecdcb6`, ink `#241d12`, muted `#6a5b3e`, hairline rule
  `#b7a377`, oxblood/red stamp accent `#b1332a`.
- Fonts (Google Fonts, with fallbacks): **Archivo Black** (masthead), **Special
  Elite** (typewriter accents — datelines, labels, meta), **Source Serif 4**
  (headlines + body).
- Subtle paper texture (CSS speckle) and a rubber-stamp seal motif.

**Homepage — `docs/index.html`** (the fast daily read):
- Topbar: wire number · "The Autonomous Desk" · date.
- Masthead: `VERTEBRATE.ai` (Archivo Black, red `.ai`) + rubber-stamp seal
  ("EST. 2026 · AUTONOMOUS DESK") + tagline "the first ai-powered media."
- Nav strip: Today's Feed · The Weekly · The Index · Topics · About.
- **Weekly teaser** strip linking to the current edition.
- **Single-column wire feed:** each item = red category stamp + typewriter
  dateline meta + linked headline + source + `one_line`.
- **Right sidebar — "The Index" tag cloud:** aggregated tags sized by frequency,
  with type distinguished by style — **companies bold**, _people italic_,
  themes in typewriter mono. Each tag links to its own page (below).

**The Weekly — `docs/weekly/<week>.html`** (the deep read):
- "THE WEEKLY" kicker masthead + edition line (e.g. "No. 29 · Week of Jul
  13–19, 2026").
- Italic **editor's-note lede**.
- Mentions grouped by topic; each entry = category stamp + linked headline +
  source + a **"Why it matters."** 2–3 sentence explainer.
- Archive of past editions at `docs/weekly/index.html`.

**Tag pages — `docs/tag/<slug>.html`:** one page per tag, listing every mention
carrying it (feed style). This is what makes the Index cloud navigable.

**Reference mockups (approved):** `mocks/final-home.html`,
`mocks/final-weekly.html` — the canonical look the templates should reproduce.

Site generation uses **Jinja2** templates in `templates/`, writing:
`docs/index.html`, `docs/weekly/index.html`, `docs/weekly/<week>.html`,
`docs/tag/<slug>.html`, `docs/style.css`, and `docs/CNAME` (contains
`vertebrate.ai`).

---

## Publishing — GitHub Pages (the "simple architecture")

- Pages serves from the **`main` branch → `/docs` folder** (no CI, no gh-pages
  branch).
- `docs/` and `data/` are **tracked in git** — they are the published site and
  its content. Running the monitor changes files there; **`git commit && git
  push` is the deploy step** (manual for v1; automated scheduling is v2).
- README documents the one-time setup: Settings → Pages → `/docs`; the `CNAME`
  file; and the DNS records to point the vertebrate.ai apex domain at GitHub
  Pages. (Sanity-check the domain spelling before wiring DNS.)

---

## Data model (flat files, no database)

`data/mentions.json` — a list of records:

```json
{
  "url": "https://…",
  "title": "Figure Puts a Humanoid on BMW's Line…",
  "source": "The Verge",
  "published": "2026-07-15T07:12:00Z",
  "topic": "Physical AI",
  "category": "launch",
  "one_line": "The robot can carry a chassis part without complaint…",
  "companies": ["Figure", "BMW"],
  "people": ["Brett Adcock"],
  "themes": ["humanoid", "physical AI"],
  "first_seen": "2026-07-15T14:03:00Z",
  "week": "2026-W29",
  "why": null
}
```

- `week` is the ISO week of `first_seen` (`YYYY-Www`).
- `why` is `null` until the weekly run fills it.
- **Entity normalization (v1, light):** trim whitespace; collapse
  case-insensitive duplicates keeping the first-seen display form; support an
  optional small alias map the owner can extend later (e.g. "Waymo LLC" →
  "Waymo"). Naming inconsistency from the model is a known rough edge, acceptable
  for v1.

`data/weeks.json` — weekly ledes, keyed by ISO week:

```json
{ "2026-W29": { "lede": "This was the week the humanoid clocked in…",
                "generated_at": "2026-07-19T09:00:00Z" } }
```

`watchlist.yaml` — owner-edited topics:

```yaml
topics:
  - name: Physical AI
    keywords: '"physical AI" OR humanoid OR "embodied AI"'
  - name: Driverless
    keywords: 'Waymo OR robotaxi OR driverless'
```

`.env` — `ANTHROPIC_API_KEY` only.

---

## Module layout

Small, single-purpose files (each readable end to end):

| File | One job |
|------|---------|
| `config.py` | Load `.env`, `watchlist.yaml`, site settings; one clear error per failure. |
| `feeds.py` | Google News RSS via `feedparser` → normalized articles; per-topic cap; snippet truncation. |
| `store.py` | Load/save `data/mentions.json` + `data/weeks.json`; dedup by URL; append; query by week. |
| `classify.py` | Haiku 4.5, per-article structured output → relevance/category/one_line/companies/people/themes. Skip-on-error. |
| `weekly.py` | Sonnet 5, editor's-note lede + per-mention "why it matters"; write back. |
| `site.py` | Jinja2 templates → `docs/` (home, weekly editions + archive, tag pages, `style.css`, `CNAME`). |
| `monitor.py` | CLI orchestrator: default = daily ingest + rebuild; `--weekly [--week …]` = editorial + rebuild. |

Plus: `templates/` (Jinja2), `README.md`, `watchlist.yaml`, `.env.example`,
`requirements.txt`, `.gitignore`, `tests/`.

---

## Error handling (quality bar)

- **Bad API key** → `anthropic.AuthenticationError` → one clear line
  ("ANTHROPIC_API_KEY was rejected — check your key.").
- **No network** → connection error / feedparser failure → one clear line.
- **Malformed `watchlist.yaml`** → one clear line naming the file + parser detail.
- **Missing `ANTHROPIC_API_KEY`** → checked up front; fail fast before any work.
- **A single item returning malformed/off-schema JSON** → skipped and logged;
  the run and the site build never crash on one bad item.
- **Site build** skips a record with missing required fields rather than aborting
  the whole build.

## Cost (quality bar: cents, not dollars)

Haiku for daily triage, truncated snippets, small `max_tokens`, 25/topic cap →
fractions of a cent per daily run. Sonnet only weekly, over a handful of
mentions → still cents. No prompt caching (negligible benefit at once-daily
volume; skipped for simplicity).

## Testing (modest, to learn from)

Unit tests for the pure logic, with the Anthropic client **mocked** (no network,
no cost):

- `store` — dedup, append, query-by-week.
- `site` — renders expected structure, skips empty topics, tag-cloud frequency
  sizing.
- `classify` / `weekly` — parsing of structured output into records.

Network- and API-touching code stays thin so it needs no elaborate mocking.

---

## Run model & README

- **Manual first:** `python monitor.py` runs one daily cycle; `python
  monitor.py --weekly` produces the weekly edition. Publish with `git commit &&
  git push`.
- README covers: venv + `pip install`; how to add topics to `watchlist.yaml`;
  GitHub Pages + custom-domain (CNAME + DNS) setup; how to run daily and weekly;
  the cost note; and how to schedule later (cron or GitHub Actions).

## Out of scope for v1 (do not build)

Sentiment scoring, dashboards, email/Telegram delivery, multiple recipients,
X/Reddit or non-RSS sources, historical analytics beyond the weekly archive,
full-text search, comments, and **automated scheduling** (cron/GitHub Actions is
v2 — documented, not built). Keep v1 shippable.

## Open follow-ups (v2+, noted not built)

- Automated scheduling (GitHub Actions or cron) + optional auto-commit/push.
- Richer entity normalization / a curated alias map.
- Per-topic and per-source pages beyond the tag pages.
