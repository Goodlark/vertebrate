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


def test_iso_week_bounds():
    from datetime import date
    assert store.iso_week_bounds("2026-W28") == (date(2026, 7, 6), date(2026, 7, 12))


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


def _story(url, title, src):
    return store.Mention(url=url, title=title, source=src, published="", topic="Driverless",
                         category="other", one_line="o", first_seen="", week="2026-W29")


def test_dedupe_collapses_same_story_across_outlets():
    ms = [
        _story("1", "Shirtless man destroys Waymo in busy East Hollywood intersection, video shows - ABC7", "ABC7"),
        _story("2", "Shirtless man arrested after police say he vandalized a Waymo in East Hollywood - LA Times", "LA Times"),
        _story("3", "Shirtless man vandalizes Waymo in East Hollywood, video shows - KTLA", "KTLA"),
        _story("4", "Waymo opens driverless service on Phoenix freeways - TechCrunch", "TechCrunch"),
    ]
    urls = [m.url for m in store.dedupe_stories(ms)]
    assert "4" in urls                                    # distinct story kept
    assert len([u for u in urls if u in {"1", "2", "3"}]) == 1  # the trio collapses to one


def test_dedupe_keeps_distinct_stories_sharing_an_entity():
    ms = [
        _story("1", "Waymo opens on Phoenix freeways - TechCrunch", "TechCrunch"),
        _story("2", "Waymo called to carpet over emergency-scene responses - Axios", "Axios"),
    ]
    assert len(store.dedupe_stories(ms)) == 2
