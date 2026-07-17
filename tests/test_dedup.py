from types import SimpleNamespace
from unittest.mock import MagicMock

import dedup
import store


def _m(url, title, category="other", seen="2026-07-15T00:00:00"):
    return store.Mention(url=url, title=title, source="S", published="", topic="Driverless",
                         category=category, one_line="o", companies=["Waymo"], people=[],
                         themes=[], first_seen=seen, week="2026-W28")


def _client(clusters):
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=clusters)
    return client


def test_cluster_events_groups_same_event():
    ms = [_m("a", "Waymo to start rides in 4 markets"), _m("b", "Waymo comes to Tampa"),
          _m("c", "Figure hits the BMW line")]
    client = _client(dedup.Clusters(groups=[dedup.Group(ids=[0, 1]), dedup.Group(ids=[2])]))
    groups = dedup.cluster_events(client, ms)
    assert sorted(len(g) for g in groups) == [1, 2]


def test_cluster_events_repairs_dropped_ids():
    ms = [_m("a", "x"), _m("b", "y"), _m("c", "z")]
    client = _client(dedup.Clusters(groups=[dedup.Group(ids=[0, 1])]))   # id 2 omitted
    groups = dedup.cluster_events(client, ms)
    assert sorted(i for g in groups for i in g) == [0, 1, 2]


def test_cluster_events_falls_back_to_singletons_on_error():
    ms = [_m("a", "x"), _m("b", "y")]
    client = MagicMock()
    client.messages.parse.side_effect = RuntimeError("boom")
    assert dedup.cluster_events(client, ms) == [[0], [1]]


def test_mark_duplicates_keeps_best_of_each_cluster():
    ms = [_m("a", "Waymo to start rides in 4 markets", category="launch"),
          _m("b", "Waymo comes to Tampa", category="other"),
          _m("c", "Figure hits the line", category="launch")]
    client = _client(dedup.Clusters(groups=[dedup.Group(ids=[0, 1]), dedup.Group(ids=[2])]))
    dropped = dedup.mark_duplicates(client, ms)
    assert dropped == 1
    assert ms[0].duplicate is False   # 'launch' outranks 'other' → kept
    assert ms[1].duplicate is True
    assert ms[2].duplicate is False
