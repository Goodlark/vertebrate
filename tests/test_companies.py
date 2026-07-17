from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import companies


def test_anchors_keeps_onsite_dedupes_drops_junk():
    html = ('<a href="/blog/alpha">Alpha post title</a>'
            '<a href="/blog/alpha">Alpha again</a>'
            '<a href="https://twitter.com/co">social</a>'
            '<a href="/blog/beta">Beta post title</a>'
            '<a href="/x">no</a>')
    out = companies._anchors(html, "https://co.com/blog")
    urls = [u for _, u in out]
    assert "https://co.com/blog/alpha" in urls
    assert "https://co.com/blog/beta" in urls
    assert all("twitter.com" not in u for u in urls)            # off-site dropped
    assert sum(u.endswith("/blog/alpha") for u in urls) == 1    # deduped


def test_list_posts_via_rss():
    co = {"name": "Neura", "url": "https://neura.com", "rss": "https://neura.com/feed/", "topic": "x"}
    fake = SimpleNamespace(entries=[{"title": "Neura raises $1B", "link": "https://neura.com/p1"}])
    with patch("companies.feedparser.parse", return_value=fake):
        arts = companies.list_posts(co, MagicMock())
    assert arts[0].title == "Neura raises $1B"
    assert arts[0].url == "https://neura.com/p1"
    assert arts[0].source == "Neura"


def test_list_posts_via_html_model_extraction():
    co = {"name": "Figure", "url": "https://figure.ai/news", "rss": None, "topic": "x"}
    html = '<a href="/news/launch">Figure launches a robot</a>'
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=companies.PostLinks(
        posts=[companies.PostLink(title="Figure launches a robot", url="https://figure.ai/news/launch")]))
    with patch("companies.requests.get", return_value=SimpleNamespace(text=html)):
        arts = companies.list_posts(co, client)
    assert arts[0].url == "https://figure.ai/news/launch"
    assert arts[0].source == "Figure"
