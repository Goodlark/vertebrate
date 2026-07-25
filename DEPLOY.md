# Deploying vertebrate.ai on Netlify

The site is a **pre-built static site** in `docs/` (regenerated daily by the GitHub
Action). Netlify just serves that folder and re-deploys automatically whenever the
Action pushes new content — no build step, no server, no database.

Why Netlify over GitHub Pages: Netlify serves HTML with `must-revalidate`
(configured in `netlify.toml`), so readers' browsers always check for the latest
news instead of holding a stale copy for up to 10 minutes.

Everything Netlify needs is already in the repo:
- `netlify.toml` — publish folder (`docs`), always-fresh HTML headers, `www` → apex redirect.
- `docs/` — the built site, committed and kept current by the daily Action.
- `docs/404.html` — a branded not-found page (served automatically).

## One-time setup (~15 minutes)

### 1. Create the site
1. Sign in at **app.netlify.com** — "Log in with GitHub" is easiest (free).
2. **Add new site → Import an existing project → GitHub → `Goodlark/vertebrate`.**
3. Netlify reads `netlify.toml` automatically (publish = `docs`, no build). Click **Deploy**.
4. When it finishes you get a `random-name.netlify.app` URL. Open it and confirm it
   shows today's dispatch. ✅ The site now redeploys on every push to `main`.

### 2. Point your domain at Netlify
In the new site: **Domain management → Add a domain → `vertebrate.ai`.** Then pick one:

**Option A — let Netlify run DNS (simplest, recommended)**
- Netlify shows two **nameservers** (e.g. `dns1.p0X.nsone.net`, …).
- At **GoDaddy → your domain → Nameservers → Change → Enter my own nameservers**,
  paste Netlify's nameservers, save.
- Netlify then manages `vertebrate.ai` and `www` for you, HTTPS included.

**Option B — keep DNS at GoDaddy**
- In GoDaddy DNS, set the apex record to Netlify:
  - `A` record, host `@`, value **`75.2.60.5`**
  - `CNAME`, host `www`, value **`<your-site>.netlify.app`**
- (If GoDaddy blocks the apex `A`, use Netlify's shown ALIAS/ANAME target instead.)

### 3. HTTPS
Netlify provisions a free Let's Encrypt certificate automatically once DNS resolves
(a few minutes). In **Domain management → HTTPS**, make sure "Force HTTPS" is on.

### 4. Retire the GitHub Pages custom domain (avoid a conflict)
Once DNS points to Netlify: repo **Settings → Pages → Custom domain → remove
`vertebrate.ai`**. (If Netlify says the domain is "already in use," this is why.)
Leave the Action and everything else exactly as-is.

## What stays the same
- The **daily / weekly GitHub Actions** keep running and pushing to `main`.
- Netlify sees each push and redeploys `docs/` within seconds.
- You never run a deploy by hand.

## Optional: deploy from your terminal instead
```bash
npm i -g netlify-cli
netlify login
netlify deploy --prod --dir=docs   # one-off manual publish of the current docs/
```
Git-connected (above) is preferred — it stays in sync with the daily Action.
