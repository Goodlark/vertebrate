import sitegen
import store


def _m(url, topic="Physical AI", why=None):
    return store.Mention(url=url, title="Figure hits the line", source="The Verge",
                         published="", topic=topic, category="launch",
                         one_line="A sharp sentence.", companies=["Figure"], people=["Musk"],
                         themes=["humanoid"], first_seen="2026-07-15T00:00:00",
                         week="2026-W29", why=why)


def test_build_site_writes_expected_files(tmp_path):
    out = tmp_path / "docs"
    mentions = [_m("http://a", why="Because it matters.")]
    weeks = {"2026-W29": {"lede": "The week the humanoid clocked in."}}
    sitegen.build_site(mentions, weeks, out_dir=str(out), templates_dir="templates")

    index = (out / "index.html").read_text(encoding="utf-8")
    assert "VERTEBRATE" in index
    assert "Figure hits the line" in index      # feed item
    assert "Figure" in index                     # tag index

    assert (out / "CNAME").read_text().strip() == "vertebrate.ai"
    assert (out / "style.css").exists()

    weekly = (out / "weekly" / "2026-W29.html").read_text(encoding="utf-8")
    assert "The week the humanoid clocked in." in weekly
    assert "Because it matters." in weekly       # why-it-matters

    assert (out / "weekly" / "index.html").exists()
    assert (out / "tag" / "figure.html").exists()  # slug of "Figure"


def test_build_site_caps_lead_and_lists_the_rest(tmp_path):
    out = tmp_path / "docs"
    # Distinct titles (no shared significant words) so dedup leaves all 22 in place.
    ms = [store.Mention(url=f"http://{i}", title=f"Alpha{i:02d} Bravo{i:02d} Charlie{i:02d}", source="S",
                        published="", topic="Physical AI", category="other", one_line="o",
                        companies=[], people=[], themes=[],
                        first_seen=f"2026-07-15T{i:02d}:00:00", week="2026-W29", why=None)
          for i in range(22)]
    sitegen.build_site(ms, {}, out_dir=str(out), templates_dir="templates")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Also Happened Today" in index
    # the two oldest overflow into the briefs; a newest one leads the feed
    assert "Alpha00" in index and "Alpha01" in index
    assert "Alpha21" in index


def test_build_site_homepage_shows_only_latest_week(tmp_path):
    out = tmp_path / "docs"

    def M(url, title, week, seen):
        return store.Mention(url=url, title=title, source="S", published="", topic="T",
                             category="launch", one_line="o", companies=[], people=[],
                             themes=[], first_seen=seen, week=week)

    ms = [M("http://old", "LastWeekStory", "2026-W28", "2026-07-06T00:00:00"),
          M("http://new", "ThisWeekStory", "2026-W29", "2026-07-15T00:00:00")]
    sitegen.build_site(ms, {"2026-W28": {"lede": "Last week."}},
                       out_dir=str(out), templates_dir="templates")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "ThisWeekStory" in index          # current week leads the homepage
    assert "LastWeekStory" not in index      # older week is not on the front page
    weekly = (out / "weekly" / "2026-W28.html").read_text(encoding="utf-8")
    assert "LastWeekStory" in weekly         # it lives on its weekly page


def test_build_site_removes_stale_pages(tmp_path):
    out = tmp_path / "docs"

    def M(url, company):
        return store.Mention(url=url, title="T", source="S", published="", topic="T",
                             category="other", one_line="o", companies=[company], people=[],
                             themes=[], first_seen="2026-07-15T00:00:00", week="2026-W29")

    sitegen.build_site([M("http://a", "Foo")], {}, out_dir=str(out), templates_dir="templates")
    assert (out / "tag" / "foo.html").exists()
    # Rebuild with different data — the old tag page must not linger.
    sitegen.build_site([M("http://b", "Bar")], {}, out_dir=str(out), templates_dir="templates")
    assert not (out / "tag" / "foo.html").exists()
    assert (out / "tag" / "bar.html").exists()


def test_build_site_deduplicates_display(tmp_path):
    out = tmp_path / "docs"
    ms = [
        _m("http://1"), _m("http://2"), _m("http://3"),  # identical title "Figure hits the line"
        store.Mention(url="http://4", title="Waymo takes the freeway", source="TechCrunch",
                      published="", topic="Driverless", category="launch", one_line="o",
                      companies=[], people=[], themes=[], first_seen="2026-07-15T00:00:00",
                      week="2026-W29"),
    ]
    sitegen.build_site(ms, {}, out_dir=str(out), templates_dir="templates")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert index.count("Figure hits the line") == 1   # the three duplicates collapse to one
    assert "Waymo takes the freeway" in index
