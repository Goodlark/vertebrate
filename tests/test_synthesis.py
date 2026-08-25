from types import SimpleNamespace
from unittest.mock import MagicMock

import store
import synthesis


def _m(url, title, company="Waymo", one_line="fact"):
    return store.Mention(url=url, title=title, source="Src", published="", topic="Driverless",
                         category="launch", one_line=one_line, companies=[company], people=[],
                         themes=[], first_seen="2026-07-15T00:00:00", week="2026-W29")


def test_synthesize_day_combines_a_company_thread():
    ms = [_m("http://a", "Waymo comes to Denver"),
          _m("http://b", "Waymo comes to Tampa"),
          _m("http://c", "Figure unveils a robot", company="Figure")]
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=synthesis.SynthResult(
        stories=[synthesis.SynthStory(ids=[0, 1], title="Waymo Expands to Denver and Tampa",
                                      summary="Waymo launched robotaxis in Denver and Tampa.",
                                      category="launch")]))
    n = synthesis.synthesize_day(client, ms)
    assert n == 1

    reps = [m for m in ms if m.sources]
    assert len(reps) == 1
    rep = reps[0]
    assert rep.title == "Waymo Expands to Denver and Tampa"
    assert "Denver and Tampa" in rep.one_line
    assert len(rep.sources) == 2                       # both sources kept
    assert sum(1 for m in ms if m.folded) == 1         # the non-representative is folded

    fig = next(m for m in ms if "Figure" in m.companies)
    assert not fig.folded and not fig.sources          # a singleton company is untouched


def test_write_article_returns_html_body():
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(text="<p>Waymo launched in three cities.</p><p>It matters.</p>")])
    html = synthesis.write_article(client, "Waymo Expands", "summary",
                                   [{"title": "a", "one_line": "x", "source": "KTLA"}])
    assert "<p>" in html and "Waymo launched in three cities" in html


def test_write_missing_articles_fills_body():
    m = _m("http://rep", "Waymo Expands")
    m.sources = [{"url": "http://1", "title": "A", "source": "KTLA"},
                 {"url": "http://2", "title": "B", "source": "ABC7"}]
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(text="<p>The full story.</p>")])
    assert synthesis.write_missing_articles(client, [m]) == 1
    assert "full story" in m.body and m.slug


def test_synthesize_day_ignores_singletons():
    ms = [_m("http://a", "Waymo one story")]            # only one mention -> nothing to combine
    assert synthesis.synthesize_day(MagicMock(), ms) == 0
    assert not ms[0].sources and not ms[0].folded
