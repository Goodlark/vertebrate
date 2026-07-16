import pytest
import config


def test_load_watchlist_parses_topics(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("topics:\n  - name: A\n    keywords: 'x OR y'\n")
    topics = config.load_watchlist(str(p))
    assert len(topics) == 1
    assert topics[0].name == "A"
    assert topics[0].keywords == "x OR y"


def test_load_watchlist_bad_yaml_raises_configerror(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("topics: [unterminated\n")
    with pytest.raises(config.ConfigError):
        config.load_watchlist(str(p))


def test_load_watchlist_missing_fields_raises(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("topics:\n  - name: A\n")  # no keywords
    with pytest.raises(config.ConfigError):
        config.load_watchlist(str(p))


def test_require_api_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(config.ConfigError):
        config.require_api_key()


def test_require_api_key_returns_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert config.require_api_key() == "sk-ant-test"
