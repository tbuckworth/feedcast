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


def test_indented_lines_become_sub_bullets_of_the_headline_above():
    raw = ("- Anthropic's report covers seven categories of misuse it disrupted.\n"
           "  - Alibaba peaked at nearly 3 million exchanges a day from 3,500 fake accounts.\n"
           "  - Moonshot and DeepSeek forwarded users' queries to Claude. || https://x/y\n"
           "- Trump called AI existential risk a hoax, which Zvi calls a rhetorical Rubicon.")
    out = parse_bullets(raw, {"https://x/y"})
    assert len(out) == 2
    assert out[0]["text"].startswith("Anthropic's report")
    assert len(out[0]["sub"]) == 2
    assert out[0]["sub"][1] == {"text": "Moonshot and DeepSeek forwarded users' queries to Claude.",
                                "url": "https://x/y"}
    # A headline with no link and no detail stays a plain string.
    assert out[1] == "Trump called AI existential risk a hoax, which Zvi calls a rhetorical Rubicon."


def test_level_is_relative_and_orphans_follow_their_rejected_headline():
    # The whole reply indented by two spaces: still headlines, not sub-bullets.
    # A heading line ("Key points:") is dropped together with its children,
    # rather than those children attaching to the previous headline.
    raw = ("  - First headline claim, long enough to be kept as one.\n"
           "    - Detail under the first headline claim here.\n"
           "  - Key points:\n"
           "    - Orphaned detail that must not attach to the first headline.\n"
           "  - Second headline claim, also long enough to be kept.")
    out = parse_bullets(raw)
    assert [b["text"] if isinstance(b, dict) else b for b in out] == [
        "First headline claim, long enough to be kept as one.",
        "Second headline claim, also long enough to be kept.",
    ]
    assert out[0]["sub"] == ["Detail under the first headline claim here."]


def test_invented_urls_are_dropped_but_the_bullet_stays():
    raw = "- A claim with a made-up link at the end of it. || https://invented.example/nope"
    assert parse_bullets(raw, {"https://real.example/a"}) == [
        "A claim with a made-up link at the end of it."]


def test_sub_bullets_render_nested_in_html_and_indented_in_text():
    report = _report(bullets=[{"text": "Headline claim about the report",
                               "sub": ["Detail one of the claim", "Detail two of the claim"]}])
    html = build_html(report, datetime(2026, 9, 16))
    text = build_text(report, datetime(2026, 9, 16))
    assert html.count("<ul") == 2 and "Detail two of the claim" in html
    assert "  - Headline claim about the report" in text
    assert "      - Detail one of the claim" in text
