"""The schema of config.yaml, and loading it.

config.yaml holds every setting. A field here has a default only where leaving
the setting out means "none" or "off". Unknown keys are refused, so a misspelt
setting fails loading instead of quietly being ignored.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, PositiveFloat, PositiveInt


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeedConfig(_Strict):
    """Configuration for a single feed."""

    name: str
    url: str
    mode: Literal["summarize", "verbatim", "auto"]
    prompt: str | None = None
    skip_patterns: list[str] | None = None


class PodcastMetaConfig(_Strict):
    """Podcast metadata configuration."""

    title: str
    description: str
    author: str
    email: str
    language: str
    base_url: str
    # The iTunes category the channel is listed under.
    category: str
    image_url: str | None = None
    # WebSub hub (the W3C standard, formerly PubSubHubbub). Declared in the
    # channel so apps can subscribe; CI pings it after each deploy. Pocket Casts
    # polls a small private feed on its own schedule — hours, on a bad day — but
    # acts on a hub notification within a minute or two. None or "" omits it.
    hub_url: str | None = None


class NewsSource(_Strict):
    """A single news RSS source for the daily briefing."""

    name: str
    url: str
    category: str


class MathsFilterConfig(_Strict):
    """Skip audio for posts that are too mathematical to follow by ear."""

    enabled: bool
    threshold_per_1k: float


class NewsBriefingConfig(_Strict):
    """Configuration for the daily news briefing."""

    enabled: bool
    lookback_hours: int
    prompt: str
    sources: list[NewsSource]
    # Stories fetched in full for the writer; 0 = blurbs only, the old behaviour.
    full_text_stories: int
    max_article_chars: int


class PredictionMarketsConfig(_Strict):
    """Prediction-market odds on the briefing's stories, and big unexplained moves.

    See src/markets.py. The rest of the rules (volume floors, exclusions,
    topics) live in MarketRules, with defaults from a 30-day backtest.
    """

    enabled: bool = False
    polymarket_tags: list[str]
    # Kalshi has no search; these are the AI series scanned for moves and
    # matched against stories. Its own tag listing caps out before the AGI
    # and OpenAI IPO series, so they are named here.
    kalshi_series: list[str] = []
    move: float
    major_move: float
    max_moves: int


class TTSConfig(_Strict):
    """The narrating voice."""

    # The recording the voice is cloned from, relative to the repository root.
    voice_sample: str


class Config(_Strict):
    """Full application configuration."""

    podcast: PodcastMetaConfig
    default_prompt: str
    # How recent a post must be to be narrated; None disables the cutoff.
    max_age_hours: PositiveFloat | None
    # Days an episode stays in the feed, and a failure in the retry queue.
    retention_days: PositiveInt
    # An `auto` feed's post is read out in full up to this many characters.
    auto_verbatim_limit: PositiveInt
    feeds: list[FeedConfig]
    news_briefing: NewsBriefingConfig | None = None
    maths_filter: MathsFilterConfig
    # Second-model check of every written script against its source.
    fidelity_check: bool
    prediction_markets: PredictionMarketsConfig
    tts: TTSConfig
    # Word -> spelling the voice says right, applied to the spoken text only.
    pronunciations: dict[str, str] = {}


def load_config(config_path: Path) -> Config:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return Config(**data)
