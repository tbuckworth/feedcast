"""Tests for the bullet digests shown in the email."""

import asyncio
from datetime import datetime

from src.digest import MAX_BULLETS, parse_bullets, safe_bullets
from src.email_report import ReportEpisode, RunReport, build_html, build_text


def test_strips_bullet_furniture_the_model_adds_anyway():
    raw = ("- Revenue reached $11.5 billion in the second quarter\n"
           "* Twenty of 25 researchers named AI R&D as the top risk\n"
           "3. METR raised $71 million while staying independent of labs")

    assert parse_bullets(raw) == [
        "Revenue reached $11.5 billion in the second quarter",
        "Twenty of 25 researchers named AI R&D as the top risk",
        "METR raised $71 million while staying independent of labs",
    ]


def test_drops_preamble_and_headings():
    # "Here are the bullets:" is longer than some genuine bullets, so the
    # length floor alone will not catch it — the trailing colon does.
    raw = ("Here are the bullets for this episode:\n"
           "Key points\n\n"
           "The model was trained on 40 billion tokens of curated text")

    assert parse_bullets(raw) == [
        "The model was trained on 40 billion tokens of curated text"
    ]


def test_caps_the_count_and_dedupes():
    raw = "\n".join([f"Claim number {i} about the subject matter at hand" for i in range(10)])

    assert len(parse_bullets(raw)) == MAX_BULLETS
    dupe = "The same claim about revenue growth stated twice"
    assert len(parse_bullets(f"{dupe}\n{dupe}")) == 1


def test_overlong_line_is_dropped_not_truncated():
    # A model that ignores "one sentence" and returns a paragraph should not
    # get a mangled half-sentence rendered as a bullet.
    assert parse_bullets("x " * 400) == []


def test_a_failed_digest_never_propagates():
    class Boom:
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    raise RuntimeError("upstream 500")

    assert asyncio.run(safe_bullets("some text", client=Boom(), label="ep")) == []


def _report(**kw):
    ep = ReportEpisode(
        title="AI #182", author="Zvi", feed_name="Zvi Mowshowitz",
        link="https://example.com/x", audio_url="https://example.com/a.mp3",
        duration_seconds=600, **kw,
    )
    return RunReport(episodes=[ep], feed_url="f", site_url="s")


def test_briefing_bullets_replace_the_full_text():
    report = _report(is_briefing=True, briefing_text="Full spoken briefing paragraph.",
                     bullets=["OpenAI is under new operational command"])
    html = build_html(report, datetime(2026, 8, 21))

    assert "<li" in html and "OpenAI is under new operational command" in html
    assert "Full spoken briefing paragraph." not in html


def test_briefing_falls_back_to_full_text_when_the_digest_failed():
    # An empty news section is worse than an unbulleted one.
    report = _report(is_briefing=True, briefing_text="Full spoken briefing paragraph.",
                     bullets=[])
    html = build_html(report, datetime(2026, 8, 21))

    assert "Full spoken briefing paragraph." in html


def test_bullets_are_escaped():
    report = _report(bullets=['Revenue rose 14x & "beat" <expectations>'])
    html = build_html(report, datetime(2026, 8, 21))

    assert "&amp;" in html and "<expectations>" not in html


def test_text_alternative_lists_bullets():
    report = _report(bullets=["First claim", "Second claim"])
    text = build_text(report, datetime(2026, 8, 21))

    assert "  - First claim" in text and "  - Second claim" in text


def test_linked_post_without_a_recorded_score_omits_the_number():
    # A zero would read as "no maths at all", which is the opposite of why the
    # post was linked.
    from src.email_report import LinkedPost

    report = RunReport(
        linked=[LinkedPost(title="Creativity Beyond the Manifold", author="A",
                           feed_name="LessWrong Frontpage", link="https://x/y",
                           maths_score=0.0, source="unrecorded")],
        feed_url="f", site_url="s",
    )
    html = build_html(report, datetime(2026, 8, 21))
    text = build_text(report, datetime(2026, 8, 21))

    assert "maths matches per 1000 words" not in html
    assert "0/1k" not in text
    assert "Creativity Beyond the Manifold" in html


def test_linked_post_with_a_score_still_shows_it():
    from src.email_report import LinkedPost

    report = RunReport(
        linked=[LinkedPost(title="An Anytime Algorithm", author="A",
                           feed_name="Alignment Forum", link="https://x/y",
                           maths_score=23.1, source="markdown")],
        feed_url="f", site_url="s",
    )

    assert "23.1 maths matches per 1000 words" in build_html(report, datetime(2026, 8, 21))
