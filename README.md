# Press Monitor → vertebrate.ai

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
python monitor.py --captions # backfill LinkedIn captions for older editions
```

Both commands write files under `docs/` and `data/`. **Publish by committing:**

```bash
git add docs data && git commit -m "update: $(date +%F)" && git push
```

## Publish on vertebrate.ai (one time)

1. Push this repo to GitHub.
2. Settings → Pages → Build and deployment → Source: **Deploy from a branch**,
   Branch: **main** / **/docs**.
3. The build writes `docs/CNAME` (`vertebrate.ai`) for you. In your DNS, point
   the apex domain at GitHub Pages with these `A` records:
   `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   (and an `AAAA`/`www` `CNAME` per GitHub's current Pages docs).
4. Settings → Pages → Custom domain: `vertebrate.ai`; enable HTTPS.

## Cost

Daily triage runs on Haiku 4.5 with truncated snippets and a 25-article/topic
cap — cents per run. The weekly editorial runs on Sonnet 5 once a week. See the
spec for details.

## Distribution

Each weekly edition ships three ways to repurpose it:

- **Share buttons** (X, LinkedIn, Facebook, email, copy-link) — they pull the
  branded `og.png` card automatically.
- **A copy-ready LinkedIn caption** — the weekly editorial writes it in the same
  Sonnet call (`--captions` backfills older editions). It renders in a
  "Post this to LinkedIn" box with a one-tap Copy button.
- **An RSS feed** at `/feed.xml` (one item per weekly edition, full write-up
  included). Point Substack's RSS import — or any reader — at it.

## Scheduling (later / v2)

Not built in v1 — run the two commands by hand. To automate later, a `cron` job
or a GitHub Actions workflow can run them on a schedule and commit the result.

## How it fits together

```
watchlist.yaml ─▶ feeds.py ─▶ store.filter_new ─▶ classify.py (Haiku 4.5)
                                                      │
                                     data/mentions.json ◀─ store.py
                                                      │
                          sitegen.py (Jinja2) ─▶ docs/  (GitHub Pages)
                                                      ▲
weekly:  weekly.py (Sonnet 5) ─▶ data/weeks.json ─────┘
```

- `config.py` — env + watchlist + tunables
- `feeds.py` — Google News RSS → articles
- `store.py` — flat-file records, dedup, ISO weeks
- `classify.py` — per-article relevance/category/one-liner/tags
- `weekly.py` — weekly lede + "why it matters"
- `sitegen.py` — renders the newspaper into `docs/`
- `monitor.py` — the CLI that wires it together

## Tests

```bash
pytest -q
```
Tests mock the Anthropic client — no network, no cost.
