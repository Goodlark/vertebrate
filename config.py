from __future__ import annotations

import os
from dataclasses import dataclass

import yaml
from dotenv import load_dotenv

# --- Tunables (kept here so the owner can find and change them in one place) ---
SNIPPET_MAX_CHARS = 500
PER_TOPIC_LIMIT = 25
MAIN_FEED_LIMIT = 20                      # lead stories on the homepage; the rest go to "Also happened today"
CLASSIFY_MODEL = "claude-haiku-4-5"      # cheap, high-volume daily triage
WEEKLY_MODEL = "claude-sonnet-5"         # sharper prose for the weekly editorial
CLASSIFY_MAX_TOKENS = 400
WEEKLY_MAX_TOKENS = 8000
SITE_TITLE = "VERTEBRATE.ai"
SITE_TAGLINE = "the first ai-powered media"
DOMAIN = "vertebrate.ai"


class ConfigError(Exception):
    """Raised for any user-fixable configuration problem, with a clear message."""


@dataclass(frozen=True)
class Topic:
    name: str
    keywords: str


def load_env(path: str = ".env") -> None:
    """Load ANTHROPIC_API_KEY (and anything else) from a local .env file."""
    load_dotenv(path)


def require_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return key


def load_watchlist(path: str = "watchlist.yaml") -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"Watchlist not found at {path}.")
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} is not valid YAML: {e}")

    if not isinstance(data, dict) or "topics" not in data:
        raise ConfigError(f"{path} must have a top-level 'topics:' list.")

    topics = []
    for i, raw in enumerate(data["topics"] or []):
        if not isinstance(raw, dict) or "name" not in raw or "keywords" not in raw:
            raise ConfigError(
                f"{path} topic #{i + 1} must have both 'name' and 'keywords'."
            )
        topics.append(Topic(name=str(raw["name"]), keywords=str(raw["keywords"])))
    if not topics:
        raise ConfigError(f"{path} has no topics — add at least one.")
    return topics
