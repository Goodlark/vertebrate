from __future__ import annotations

import html
import logging
import re

import requests

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # pragma: no cover - optional dependency
    gnewsdecoder = None

log = logging.getLogger("pressmonitor.sources")

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def resolve(url: str) -> str:
    """Resolve a Google News redirect to the real publisher URL; pass others through.

    Google News RSS hands us encrypted redirect links, so the article's real URL
    (and its full text, where the company names live) is hidden until decoded.
    """
    if "news.google.com" not in url or gnewsdecoder is None:
        return url
    try:
        out = gnewsdecoder(url, interval=1)
        if out.get("status") and out.get("decoded_url"):
            return out["decoded_url"]
    except Exception as e:  # noqa: BLE001
        log.warning("resolve failed: %s", e)
    return url


_BLOCK = re.compile(r"(?is)<(script|style|noscript|head|nav|footer|form).*?</\1>")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _strip_html(markup: str) -> str:
    markup = _BLOCK.sub(" ", markup)
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", markup))).strip()


def fetch_text(url: str, max_chars: int = 6000, timeout: int = 20) -> str:
    """Fetch an article and return best-effort plain text ('' on any failure)."""
    try:
        r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "").lower():
            return ""
        return _strip_html(r.text)[:max_chars]
    except Exception as e:  # noqa: BLE001
        log.warning("fetch failed for %s: %s", url, e)
        return ""


def article_text(url: str, **kw) -> str:
    """Resolve a (possibly Google News) URL and return the article's plain text."""
    return fetch_text(resolve(url), **kw)
