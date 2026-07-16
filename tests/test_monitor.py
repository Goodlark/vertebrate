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
