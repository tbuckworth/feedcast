"""What the voice is given to say: titles without a doubled byline, and the
respellings that make the voice say a word right."""

import asyncio
from datetime import datetime

import pytest

from src.monitor import FeedEntry
from src.processor import ContentProcessor, spoken_title


@pytest.mark.parametrize("title, author, spoken", [
    ("“The Curve Bends You” by Zvi", "Zvi Mowshowitz", "“The Curve Bends You”"),
    ("“AI #188: Gemini Dot Argon” by Zvi", "Zvi Mowshowitz", "“AI #188: Gemini Dot Argon”"),
    ("Senate Testimony by Daniel Kokotajlo", "Daniel Kokotajlo", "Senate Testimony"),
    ("Notes by Kokotajlo.", "Daniel Kokotajlo", "Notes"),
    ("Stand by Me", "Scott Alexander", "Stand by Me"),            # not the author
    ("Death by a Thousand Cuts", "Zvi Mowshowitz", "Death by a Thousand Cuts"),
    ("by Zvi", "Zvi Mowshowitz", "by Zvi"),                       # nothing left: keep it
    ("Plain title", "", "Plain title"),
])
def test_spoken_title(title, author, spoken):
    assert spoken_title(title, author) == spoken


def test_intro_and_outro_say_the_name_once():
    entry = FeedEntry(id="z", title="“The Curve Bends You” by Zvi", link="", content="<p>Body.</p>",
                      published=datetime(2026, 10, 8), author="Zvi Mowshowitz",
                      feed_name="Zvi Mowshowitz")
    text = asyncio.run(ContentProcessor("p").process(entry, "verbatim"))
    assert text.startswith("“The Curve Bends You”. By Zvi Mowshowitz.")
    assert text.endswith("End of “The Curve Bends You”.") and text.count("Zvi") == 1


from src.normalizer import TextNormalizer, respell

TABLE = {"METR": "Meter", "Amodei": "Amo-day", "xAI": "X-A-I", "GitHub": "Git Hub"}


@pytest.mark.parametrize("text, spoken", [
    ("METR found that", "Meter found that"),
    ("Dario Amodei's view.", "Dario Amo-day's view."),
    ("the METRO line and metric units", "the METRO line and metric units"),   # whole words only
    ("XAI and xai differ from xAI.", "XAI and xai differ from X-A-I."),          # case-sensitive
    ("on GitHub, GitHub-hosted code", "on Git Hub, GitHub-hosted code"),      # not inside a compound
])
def test_respell_whole_words_only(text, spoken):
    assert respell(text, TABLE) == spoken


def test_normaliser_respells_its_output_even_when_the_model_returns_nothing(monkeypatch):
    norm = TextNormalizer.__new__(TextNormalizer)
    norm.respellings, norm.unnormalized_chars = TABLE, 0

    async def refuse(paragraphs):
        return "\n\n".join(paragraphs)            # the narrate-as-written fallback
    norm._normalize_resilient = refuse
    assert asyncio.run(norm.normalize_for_tts("METR and Amodei.")) == "Meter and Amo-day."


def test_configured_respellings_load():
    import src.main as main
    cfg = main.load_config(main.Path(__file__).resolve().parent.parent / "config.yaml")
    assert cfg.pronunciations["METR"] == "Meter" and "OpenAI" not in cfg.pronunciations
