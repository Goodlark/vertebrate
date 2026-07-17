from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import classify
import sources


def test_strip_html_removes_tags_and_scripts():
    markup = ("<html><head><style>p{color:red}</style></head><body>"
              "<script>evil()</script><p>Hello <b>World</b></p></body></html>")
    out = sources._strip_html(markup)
    assert "Hello World" in out
    assert "evil()" not in out and "color:red" not in out


def test_resolve_passes_through_non_google_url():
    assert sources.resolve("https://example.com/story") == "https://example.com/story"


def test_fetch_text_empty_on_non_html():
    resp = SimpleNamespace(status_code=200, headers={"content-type": "application/json"}, text="{}")
    with patch("sources.requests.get", return_value=resp):
        assert sources.fetch_text("http://x") == ""


def test_fetch_text_strips_when_html():
    resp = SimpleNamespace(status_code=200, headers={"content-type": "text/html; charset=utf-8"},
                           text="<p>Realbotix ships <b>Sally</b></p>")
    with patch("sources.requests.get", return_value=resp):
        assert "Realbotix ships Sally" in sources.fetch_text("http://x")


def test_extract_from_source_returns_parsed():
    client = MagicMock()
    client.messages.parse.return_value = SimpleNamespace(parsed_output=classify.SourceExtract(
        companies=["Realbotix"], people=["Andrew Kiguel"], one_line="Realbotix deploys a robot."))
    out = classify.extract_from_source(client, "Title", "body text about Realbotix")
    assert out.companies == ["Realbotix"] and out.people == ["Andrew Kiguel"]


def test_extract_from_source_none_on_error():
    client = MagicMock()
    client.messages.parse.side_effect = RuntimeError("boom")
    assert classify.extract_from_source(client, "t", "b") is None
