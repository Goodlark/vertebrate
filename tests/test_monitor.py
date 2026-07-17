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
                                    out_dir=str(out_dir), data_dir=str(data_dir), company_list=[])

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
                                    out_dir=str(tmp_path / "docs"), data_dir=str(tmp_path / "data"), company_list=[])
    assert summary["relevant"] == 0 and summary["added"] == 0


def test_run_backfill_stores_week_and_writes_editorial(tmp_path):
    import store
    import weekly
    topics = [Topic("Physical AI", "humanoid")]
    art = Article("Old humanoid news", "http://x", "The Verge", "", "snippet")

    def parse_side_effect(**kwargs):
        if kwargs.get("output_format") is weekly.WeeklyRollup:
            return SimpleNamespace(parsed_output=weekly.WeeklyRollup(
                summary="Big thing happened.", lede="The week in review.",
                linkedin="→ Big thing happened.\n#Robotics",
                entries=[weekly.WhyEntry(url="http://x", why="It mattered.")]))
        return SimpleNamespace(parsed_output=classify.Assessment(
            relevant=True, category="launch", one_line="o", companies=["Figure"], people=[], themes=["humanoid"]))

    client = MagicMock()
    client.messages.parse.side_effect = parse_side_effect
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "docs"
    with patch("monitor.feeds.fetch_topic", return_value=[art]):
        monitor.run_backfill(datetime(2026, 7, 15), "2026-W28", topics, client,
                             out_dir=str(out_dir), data_dir=str(data_dir))

    stored = store.load_mentions(str(data_dir / "mentions.json"))
    assert any(m.week == "2026-W28" and m.url == "http://x" for m in stored)
    weeks = store.load_weeks(str(data_dir / "weeks.json"))
    assert weeks["2026-W28"]["lede"] == "The week in review."
    assert "#Robotics" in weeks["2026-W28"]["linkedin"]
    wk = (out_dir / "weekly" / "2026-W28.html").read_text(encoding="utf-8")
    assert "Old humanoid news" in wk and "It mattered." in wk
    assert (out_dir / "feed.xml").exists()            # syndication feed built


def test_run_captions_backfills_missing_linkedin(tmp_path):
    import store
    import weekly
    data_dir = tmp_path / "data"
    store.save_mentions(
        [store.Mention(url="http://a", title="T", source="S", published="", topic="Physical AI",
                       category="launch", one_line="o", companies=["Figure"], people=[], themes=[],
                       first_seen="2026-07-06T00:00:00", week="2026-W28")],
        str(data_dir / "mentions.json"))
    store.save_weeks({"2026-W28": {"summary": "s", "lede": "l"}}, str(data_dir / "weeks.json"))

    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(
        parsed_output=weekly.LinkedInCaption(linkedin="→ Figure did X.\n#Robotics"))
    monitor.run_captions(datetime(2026, 7, 16), client,
                         out_dir=str(tmp_path / "docs"), data_dir=str(data_dir))

    weeks = store.load_weeks(str(data_dir / "weeks.json"))
    assert weeks["2026-W28"]["linkedin"].startswith("→")


def test_run_daily_dedupes_same_story_from_two_outlets(tmp_path):
    import store
    topics = [Topic("Driverless", "waymo")]
    arts = [
        Article("Shirtless man vandalizes Waymo in East Hollywood, video shows - KTLA", "http://k", "KTLA", "", ""),
        Article("Shirtless man destroys Waymo in East Hollywood intersection, video shows - ABC7", "http://a", "ABC7", "", ""),
    ]
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=classify.Assessment(
        relevant=True, category="other", one_line="o", companies=["Waymo"], people=[], themes=["driverless"]))
    with patch("monitor.feeds.fetch_topic", return_value=arts):
        summary = monitor.run_daily(datetime(2026, 7, 15), topics, client,
                                    out_dir=str(tmp_path / "docs"), data_dir=str(tmp_path / "data"), company_list=[])
    stored = store.load_mentions(str(tmp_path / "data" / "mentions.json"))
    assert len(stored) == 1                 # two outlets, one story
    assert summary["stored"] == 1


def test_run_daily_keeps_company_news_drops_essays(tmp_path):
    import store
    co = {"name": "Figure", "url": "https://figure.ai/news", "rss": None,
          "topic": "Physical AI & Humanoids"}
    posts = [Article("Figure launches a robot", "https://figure.ai/news/x", "Figure", "", ""),
             Article("Our company culture", "https://figure.ai/news/y", "Figure", "", "")]

    def parse_side(**kwargs):
        content = kwargs["messages"][0]["content"].lower()
        return SimpleNamespace(parsed_output=classify.Assessment(
            relevant=True, is_news=("culture" not in content), category="launch",
            one_line="Figure launched a robot.", companies=["Figure"], people=[], themes=[]))

    client = MagicMock()
    client.messages.parse.side_effect = parse_side
    with patch("monitor.feeds.fetch_topic", return_value=[]), \
         patch("monitor.companies.list_posts", return_value=posts), \
         patch("monitor.sources.fetch_text", return_value="body text"):
        monitor.run_daily(datetime(2026, 7, 15), [], client,
                          out_dir=str(tmp_path / "docs"), data_dir=str(tmp_path / "data"),
                          company_list=[co])

    stored = store.load_mentions(str(tmp_path / "data" / "mentions.json"))
    urls = {m.url for m in stored}
    assert "https://figure.ai/news/x" in urls        # the news post is kept
    assert "https://figure.ai/news/y" not in urls     # the culture essay is dropped
