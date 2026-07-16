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
    assert "VERTERBRATE" in index
    assert "Figure hits the line" in index      # feed item
    assert "Figure" in index                     # tag index

    assert (out / "CNAME").read_text().strip() == "verterbrate.ai"
    assert (out / "style.css").exists()

    weekly = (out / "weekly" / "2026-W29.html").read_text(encoding="utf-8")
    assert "The week the humanoid clocked in." in weekly
    assert "Because it matters." in weekly       # why-it-matters

    assert (out / "weekly" / "index.html").exists()
    assert (out / "tag" / "figure.html").exists()  # slug of "Figure"
