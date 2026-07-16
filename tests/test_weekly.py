from types import SimpleNamespace
from unittest.mock import MagicMock

import weekly
import store


def _m(url):
    return store.Mention(url=url, title="T", source="S", published="", topic="Physical AI",
                         category="launch", one_line="one", first_seen="", week="2026-W29")


def test_write_weekly_uses_sonnet_and_returns_rollup():
    roll = weekly.WeeklyRollup(summary="A did X.", lede="The week...", linkedin="→ A did X.\n#Robotics",
                               entries=[weekly.WhyEntry(url="http://a", why="because")])
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=roll)
    out = weekly.write_weekly(client, [_m("http://a")])
    assert out.lede.startswith("The week")
    assert out.linkedin.startswith("→")
    _, kwargs = client.messages.parse.call_args
    assert kwargs["model"] == "claude-sonnet-5"


def test_write_weekly_returns_none_on_error():
    client = MagicMock()
    client.messages.parse.side_effect = RuntimeError("boom")
    assert weekly.write_weekly(client, [_m("http://a")]) is None


def test_apply_rollup_sets_why_by_url():
    ms = [_m("http://a"), _m("http://b")]
    roll = weekly.WeeklyRollup(summary="s", lede="x", linkedin="c",
                               entries=[weekly.WhyEntry(url="http://a", why="deep")])
    weekly.apply_rollup(ms, roll)
    assert ms[0].why == "deep"
    assert ms[1].why is None


def test_write_linkedin_returns_caption():
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(
        parsed_output=weekly.LinkedInCaption(linkedin="→ Figure hit the line.\n#Robotics"))
    out = weekly.write_linkedin(client, "2026-W29", "sum", "lede", [_m("http://a")])
    assert "#Robotics" in out


def test_write_linkedin_returns_none_on_error():
    client = MagicMock()
    client.messages.parse.side_effect = RuntimeError("boom")
    assert weekly.write_linkedin(client, "2026-W29", "s", "l", [_m("http://a")]) is None
