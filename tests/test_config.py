"""config.yaml is the one place each setting lives, and a bad one fails loading.

The code used to carry its own copy of most settings as defaults, and they had
drifted: NewsBriefingConfig said 48 hours of news where config.yaml said 24.
A misspelt key was silently ignored, so the setting it meant fell back to the
code's value without a word.
"""

import copy
import json
from urllib.parse import urljoin

import pytest
import yaml
from pydantic import ValidationError

from src import main
from src.config import CONFIG_PATH, ROOT, load_config

REAL = yaml.safe_load(CONFIG_PATH.read_text())


def _load(tmp_path, data) -> object:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_config(path)


def _section(data: dict, path: tuple) -> dict:
    for key in path:
        data = data[key]
    return data


def test_the_real_config_loads():
    config = load_config()
    assert config.tts.voice_path.is_file()


@pytest.mark.parametrize("path", [
    (), ("podcast",), ("feeds", 0), ("maths_filter",), ("prediction_markets",),
    ("news_briefing",), ("news_briefing", "sources", 0), ("tts",),
])
def test_a_misspelt_key_fails_loading(tmp_path, path):
    data = copy.deepcopy(REAL)
    _section(data, path)["lookback_hour"] = 24
    with pytest.raises(ValidationError, match="lookback_hour"):
        _load(tmp_path, data)


@pytest.mark.parametrize("path", [
    ("max_age_hours",), ("retention_days",), ("auto_verbatim_limit",), ("fidelity_check",),
    ("podcast", "category"), ("podcast", "language"), ("feeds", 0, "mode"),
    ("maths_filter", "threshold_per_1k"), ("news_briefing", "lookback_hours"),
    ("news_briefing", "full_text_stories"), ("news_briefing", "max_article_chars"),
    ("prediction_markets", "move"), ("prediction_markets", "polymarket_tags"),
    ("tts", "voice_sample"),
])
def test_a_missing_setting_fails_loading_rather_than_taking_a_code_default(tmp_path, path):
    data = copy.deepcopy(REAL)
    del _section(data, path[:-1])[path[-1]]
    with pytest.raises(ValidationError, match=str(path[-1])):
        _load(tmp_path, data)


def test_the_age_cutoff_is_disabled_by_null_and_never_by_zero(tmp_path):
    data = copy.deepcopy(REAL)
    data["max_age_hours"] = None
    assert _load(tmp_path, data).max_age_hours is None
    data["max_age_hours"] = 0
    with pytest.raises(ValidationError, match="max_age_hours"):
        _load(tmp_path, data)


@pytest.mark.parametrize("value, expected", [("", "all"), ("first", "first"),
                                             ("narrate", "narrate"), (" First ", "first")])
def test_feedcast_pass_values(monkeypatch, value, expected):
    monkeypatch.setenv("FEEDCAST_PASS", value)
    assert main._run_pass() == expected


def test_an_unknown_feedcast_pass_fails_instead_of_running_both_halves(monkeypatch):
    """A typo in the workflow used to run the whole day in one pass, quietly."""
    monkeypatch.setenv("FEEDCAST_PASS", "narration")
    with pytest.raises(ValueError, match="narration"):
        main._run_pass()


def test_the_share_app_works_wherever_the_site_is_served():
    """start_url and the share target resolve against the manifest's own URL,
    so the app no longer names the /feedcast/ path the site happens to sit on."""
    manifest = json.loads((ROOT / "output" / "app" / "manifest.json").read_text())
    for base in (load_config().podcast.base_url, "https://elsewhere.test"):
        at = f"{base}/app/manifest.json"
        assert urljoin(at, manifest["start_url"]) == f"{base}/app/"
        assert urljoin(at, manifest["share_target"]["action"]) == f"{base}/app/"
