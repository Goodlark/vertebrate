from types import SimpleNamespace
from unittest.mock import MagicMock

import classify
from feeds import Article

ART = Article("Figure hits BMW line", "http://x", "The Verge", "", "snippet")


def _mock_client(assessment):
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=assessment)
    return client


def test_assess_returns_parsed_output():
    a = classify.Assessment(relevant=True, category="launch", one_line="hi",
                            companies=["Figure"], people=[], themes=["humanoid"])
    client = _mock_client(a)
    out = classify.assess(client, ART, "Physical AI")
    assert out is a
    # It called the cheap model with our structured-output type.
    _, kwargs = client.messages.parse.call_args
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["output_format"] is classify.Assessment


def test_assess_returns_none_on_error():
    client = MagicMock()
    client.messages.parse.side_effect = RuntimeError("boom")
    assert classify.assess(client, ART, "Physical AI") is None


def test_build_user_prompt_includes_topic_and_title():
    p = classify.build_user_prompt(ART, "Physical AI")
    assert "Physical AI" in p and "Figure hits BMW line" in p


def test_enrich_batch_maps_by_id():
    item = SimpleNamespace(title="Waymo comes to Tampa", one_line="Waymo arrives.", companies=["Waymo"])
    client = _mock_client(classify.EnrichBatch(items=[
        classify.EnrichItem(id=0, one_line="Waymo launched robotaxis in Tampa.",
                            companies=["Waymo"], people=["Jane Doe"])]))
    out = classify.enrich_batch(client, [item])
    assert out[0].people == ["Jane Doe"]
    assert out[0].companies == ["Waymo"]
    assert "Tampa" in out[0].one_line


def test_enrich_batch_returns_empty_on_error():
    client = MagicMock()
    client.messages.parse.side_effect = RuntimeError("boom")
    assert classify.enrich_batch(client, [SimpleNamespace(title="t", one_line="o", companies=[])]) == {}
