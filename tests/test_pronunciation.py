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
