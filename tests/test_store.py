from datetime import datetime

import store
from feeds import Article


def _mention(url, week="2026-W29", why=None):
    return store.Mention(
        url=url, title="T", source="S", published="", topic="Physical AI",
        category="launch", one_line="one", companies=["Figure"], people=["Musk"],
        themes=["humanoid"], first_seen="2026-07-15T00:00:00", week=week, why=why,
    )


def test_iso_week_format():
    assert store.iso_week(datetime(2026, 7, 15)) == "2026-W29"


def test_normalize_tags_dedupes_case_insensitively_keeping_first():
    assert store.normalize_tags([" Figure ", "figure", "Waymo"]) == ["Figure", "Waymo"]


def test_filter_new_drops_known_urls():
    arts = [Article("A", "http://a", "S", "", ""), Article("B", "http://b", "S", "", "")]
    assert [a.url for a in store.filter_new(arts, {"http://a"})] == ["http://b"]


def test_mentions_roundtrip_json(tmp_path):
    p = tmp_path / "m.json"
    store.save_mentions([_mention("http://a")], str(p))
    loaded = store.load_mentions(str(p))
    assert len(loaded) == 1
    assert loaded[0].url == "http://a"
    assert loaded[0].companies == ["Figure"]


def test_load_mentions_missing_file_returns_empty(tmp_path):
    assert store.load_mentions(str(tmp_path / "nope.json")) == []


def test_mentions_for_week_filters():
    ms = [_mention("http://a", week="2026-W29"), _mention("http://b", week="2026-W28")]
    got = store.mentions_for_week(ms, "2026-W29")
    assert [m.url for m in got] == ["http://a"]


def test_weeks_roundtrip(tmp_path):
    p = tmp_path / "w.json"
    store.save_weeks({"2026-W29": {"lede": "hi"}}, str(p))
    assert store.load_weeks(str(p))["2026-W29"]["lede"] == "hi"
