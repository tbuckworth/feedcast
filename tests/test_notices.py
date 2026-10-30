"""The run's notices: what it fell back on or skipped, whichever module did it."""

from datetime import datetime

from src import notices
from src.email_report import RunReport, build_html, build_text
from src.run_report import build_run_report


def test_notices_keep_their_order_and_collapse_repeats():
    notices.add("normaliser: served by Haiku")
    notices.add("TTS: turbo busy; rest of run on multilingual")
    notices.add("normaliser: served by Haiku")
    assert notices.report() == ["normaliser: served by Haiku (2 calls)",
                                "TTS: turbo busy; rest of run on multilingual"]


def test_a_headline_leads_the_list_however_late_it_came():
    notices.add("prediction markets skipped: ReadTimeout")
    notices.add("openrouter account unavailable for the rest of the run", headline=True)
    notices.add("openrouter account unavailable for the rest of the run", headline=True)
    assert notices.report() == ["openrouter account unavailable for the rest of the run",
                                "prediction markets skipped: ReadTimeout"]


def test_reset_starts_a_new_run():
    notices.add("a note")
    notices.add("a headline", headline=True)
    notices.reset()
    assert notices.report() == []


def test_the_run_report_carries_every_modules_notices():
    notices.add("prediction markets skipped: ReadTimeout")
    report = build_run_report([], [], set(), [], "https://example.com")
    assert report.notices == ["prediction markets skipped: ReadTimeout"]


def test_the_email_calls_them_fallbacks_and_skips():
    report = RunReport(notices=["prediction markets skipped: ReadTimeout"])
    html = build_html(report, datetime(2026, 10, 30))
    text = build_text(report, datetime(2026, 10, 30))
    assert "Fallbacks and skips this run" in html and "Model fallbacks" not in html
    assert "Fallbacks and skips this run:\n  - prediction markets skipped" in text
