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
