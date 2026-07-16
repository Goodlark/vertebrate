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
