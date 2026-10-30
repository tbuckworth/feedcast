"""The schema of config.yaml, and loading it."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class FeedConfig(BaseModel):
    """Configuration for a single feed."""

    name: str
    url: str
    mode: Literal["summarize", "verbatim", "auto"] = "auto"
    prompt: str | None = None
    skip_patterns: list[str] | None = None


class PodcastMetaConfig(BaseModel):
    """Podcast metadata configuration."""

    title: str
    description: str
    author: str
    email: str
    language: str = "en-us"
    base_url: str
    image_url: str | None = None
    # WebSub hub declared in feed.xml and pinged by CI after deploy. "" disables.
    hub_url: str | None = "https://pubsubhubbub.appspot.com/"


class NewsSource(BaseModel):
    """A single news RSS source for the daily briefing."""

    name: str
    url: str
    category: str


class MathsFilterConfig(BaseModel):
    """Skip audio for posts that are too mathematical to follow by ear."""

    enabled: bool = True
    threshold_per_1k: float = 8.0


class NewsBriefingConfig(BaseModel):
    """Configuration for the daily news briefing."""

    enabled: bool = True
    lookback_hours: int = 48
    prompt: str
    sources: list[NewsSource]
    # Stories fetched in full for the writer; 0 = blurbs only, the old behaviour.
    full_text_stories: int = 12
    max_article_chars: int = 6000


class PredictionMarketsConfig(BaseModel):
    """Prediction-market odds on the briefing's stories, and big unexplained moves.

    See src/markets.py. The rest of the rules (volume floors, exclusions,
    topics) live in MarketRules, with defaults from a 30-day backtest.
    """

    enabled: bool = False
    polymarket_tags: list[str] = ["ai", "openai", "anthropic"]
    # Kalshi has no search; these are the AI series scanned for moves and
    # matched against stories. Its own tag listing caps out before the AGI
    # and OpenAI IPO series, so they are named here.
    kalshi_series: list[str] = []
    move: float = 0.15
    major_move: float = 0.20
    max_moves: int = 3


class Config(BaseModel):
    """Full application configuration."""

    podcast: PodcastMetaConfig
    default_prompt: str
    feeds: list[FeedConfig]
    news_briefing: NewsBriefingConfig | None = None
    maths_filter: MathsFilterConfig = MathsFilterConfig()
    # Second-model check of every written script against its source.
    fidelity_check: bool = True
    prediction_markets: PredictionMarketsConfig = PredictionMarketsConfig()
    # Word -> spelling the voice says right, applied to the spoken text only.
    pronunciations: dict[str, str] = {}


def load_config(config_path: Path) -> Config:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return Config(**data)
