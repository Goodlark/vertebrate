import sitegen
import store


def _m(url, topic="Physical AI", companies=None, people=None, themes=None):
    return store.Mention(url=url, title="T", source="S", published="", topic=topic,
                         category="launch", one_line="one", companies=companies or [],
                         people=people or [], themes=themes or [], first_seen="", week="2026-W29")


def test_slugify():
    assert sitegen.slugify("Physical AI") == "physical-ai"
    assert sitegen.slugify("  Fei-Fei Li ") == "fei-fei-li"


def test_size_class_scales():
    assert sitegen.size_class(1, 10) == "s1"
    assert sitegen.size_class(10, 10) == "s5"


def test_build_tag_index_counts_and_kinds():
    ms = [_m("a", companies=["Figure"], themes=["humanoid"]),
          _m("b", companies=["Figure"], people=["Musk"])]
    idx = {t.label: t for t in sitegen.build_tag_index(ms)}
    assert idx["Figure"].count == 2 and idx["Figure"].kind == "company"
    assert idx["Musk"].kind == "person"
    assert idx["humanoid"].kind == "theme"
    assert sitegen.build_tag_index(ms)[0].label == "Figure"  # highest count first


def test_group_by_topic_preserves_first_seen_order():
    ms = [_m("a", topic="Driverless"), _m("b", topic="Physical AI"), _m("c", topic="Driverless")]
    grouped = sitegen.group_by_topic(ms)
    assert list(grouped.keys()) == ["Driverless", "Physical AI"]
    assert [m.url for m in grouped["Driverless"]] == ["a", "c"]
