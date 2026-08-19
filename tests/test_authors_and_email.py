"""Tests for author extraction and the emailed run report."""

from datetime import datetime

import pytest

from src.email_report import (
    ReportEpisode, RunReport, _meta_bits, build_html, build_text, format_duration,
)
from src.monitor import MAX_AUTHORS, extract_authors, format_authors


class TestFormatAuthors:
    def test_single(self):
        assert format_authors(["Zvi Mowshowitz"]) == "Zvi Mowshowitz"

    def test_two_use_and(self):
        assert format_authors(["A", "B"]) == "A and B"

    def test_three_use_serial_and(self):
        assert format_authors(["A", "B", "C"]) == "A, B and C"

    def test_caps_at_five_and_says_others(self):
        out = format_authors(["A", "B", "C", "D", "E", "F", "G"])
        assert out == "A, B, C, D, E and others"
        assert "F" not in out

    def test_exactly_five_has_no_others(self):
        assert format_authors(["A", "B", "C", "D", "E"]) == "A, B, C, D and E"

    def test_empty(self):
        assert format_authors([]) == ""


class TestExtractAuthors:
    def test_reads_authors_list(self):
        entry = {"authors": [{"name": "Ada"}, {"name": "Grace"}]}
        assert extract_authors(entry, "Feed") == ["Ada", "Grace"]

    def test_caps_at_max(self):
        entry = {"authors": [{"name": f"P{i}"} for i in range(9)]}
        assert len(extract_authors(entry, "Feed")) == MAX_AUTHORS

    def test_dedupes(self):
        entry = {"authors": [{"name": "Ada"}, {"name": "Ada"}, {"name": "Grace"}]}
        assert extract_authors(entry, "Feed") == ["Ada", "Grace"]

    def test_falls_back_to_author_string(self):
        assert extract_authors({"author": "Scott Alexander"}, "Feed") == ["Scott Alexander"]

    def test_falls_back_to_feed_name(self):
        assert extract_authors({}, "LessWrong Frontpage") == ["LessWrong Frontpage"]

    def test_ignores_blank_names(self):
        entry = {"authors": [{"name": "  "}, {"name": "Ada"}]}
        assert extract_authors(entry, "Feed") == ["Ada"]

    def test_blank_author_string_falls_through(self):
        assert extract_authors({"author": "   "}, "Feed") == ["Feed"]


class TestEmailReport:
    def _ep(self, **kw):
        base = dict(
            title="A Post", author="Ada Lovelace", feed_name="LessWrong Frontpage",
            link="https://example.com/post", audio_url="https://example.com/a.mp3",
            duration_seconds=245,
        )
        base.update(kw)
        return ReportEpisode(**base)

    def test_duration_formatting(self):
        assert format_duration(245) == "4 min 05 sec"
        assert format_duration(3725) == "1 hr 02 min"
        assert format_duration(0) == ""

    def test_meta_bits_dedupe_author_and_feed(self):
        ep = self._ep(author="Scott Alexander", feed_name="Scott Alexander")
        assert _meta_bits(ep).count("Scott Alexander") == 1

    def test_meta_bits_keep_distinct_feed(self):
        assert _meta_bits(self._ep()) == ["Ada Lovelace", "LessWrong Frontpage", "4 min 05 sec"]

    def test_html_has_content_and_links(self):
        r = RunReport(episodes=[self._ep()], feed_url="https://f/feed.xml",
                      site_url="https://f", total_in_feed=9)
        html = build_html(r, datetime(2026, 8, 19))
        assert "A Post" in html
        assert "Ada Lovelace" in html
        assert "https://example.com/post" in html
        assert "https://example.com/a.mp3" in html
        assert "1 new episode" in html

    def test_html_escapes_hostile_titles(self):
        r = RunReport(episodes=[self._ep(title="<script>alert(1)</script>")])
        html = build_html(r, datetime(2026, 8, 19))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_briefing_body_rendered(self):
        ep = self._ep(is_briefing=True, briefing_text="Para one.\n\nPara two.")
        html = build_html(RunReport(episodes=[ep]), datetime(2026, 8, 19))
        assert "Para one." in html and "Para two." in html

    def test_failures_listed(self):
        r = RunReport(episodes=[], failures=[("Broken", "TTSError: 502")])
        html = build_html(r, datetime(2026, 8, 19))
        assert "Broken" in html and "TTSError: 502" in html
        assert "No new episodes" in html

    def test_text_alternative_covers_the_same_ground(self):
        r = RunReport(episodes=[self._ep()], feed_url="https://f/feed.xml")
        txt = build_text(r, datetime(2026, 8, 19))
        assert "A Post" in txt
        assert "https://example.com/post" in txt
        assert "https://example.com/a.mp3" in txt

    def test_send_skipped_without_config(self, monkeypatch):
        from src import email_report
        for var in ("FEEDCAST_EMAIL_TO", "SMTP_USER", "SMTP_PASSWORD", "GMAIL_APP_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        assert email_report.send_report(RunReport()) is False


class TestSendPath:
    """Exercise send_report end to end with a stand-in SMTP server."""

    @pytest.fixture
    def fake_smtp(self, monkeypatch):
        sent = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                sent["host"], sent["port"] = host, port

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def starttls(self, context=None):
                sent["starttls"] = True

            def login(self, user, password):
                sent["login"] = (user, password)

            def send_message(self, msg):
                sent["msg"] = msg

        monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
        for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_PASSWORD", "FEEDCAST_EMAIL_FROM"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("FEEDCAST_EMAIL_TO", "reader@example.com")
        monkeypatch.setenv("SMTP_USER", "sender@example.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
        return sent

    def _report(self):
        return RunReport(episodes=[ReportEpisode(
            title="A Post", author="Ada Lovelace", feed_name="LessWrong Frontpage",
            link="https://example.com/post", audio_url="https://example.com/a.mp3",
            duration_seconds=245,
        )])

    def test_sends_multipart_alternative(self, fake_smtp):
        from src.email_report import send_report
        assert send_report(self._report(), datetime(2026, 8, 19)) is True

        msg = fake_smtp["msg"]
        assert msg["To"] == "reader@example.com"
        assert msg["From"] == "sender@example.com"
        assert "1 new episode" in msg["Subject"]

        types = {p.get_content_type() for p in msg.walk()}
        assert "text/plain" in types and "text/html" in types

        html = msg.get_body(("html",)).get_content()
        assert "Ada Lovelace" in html and "https://example.com/a.mp3" in html

    def test_defaults_to_gmail_starttls(self, fake_smtp):
        from src.email_report import send_report
        send_report(self._report(), datetime(2026, 8, 19))
        assert fake_smtp["host"] == "smtp.gmail.com"
        assert fake_smtp["port"] == 587
        assert fake_smtp["starttls"] is True
        assert fake_smtp["login"] == ("sender@example.com", "app-password")

    def test_blank_host_var_falls_back(self, fake_smtp, monkeypatch):
        """Unset GitHub Actions vars arrive as '' — must not become the host."""
        from src.email_report import send_report
        monkeypatch.setenv("SMTP_HOST", "")
        monkeypatch.setenv("SMTP_PORT", "")
        send_report(self._report(), datetime(2026, 8, 19))
        assert fake_smtp["host"] == "smtp.gmail.com"
        assert fake_smtp["port"] == 587

    def test_smtp_failure_is_swallowed(self, fake_smtp, monkeypatch):
        from src.email_report import send_report

        def boom(*a, **k):
            raise OSError("connection refused")

        monkeypatch.setattr("smtplib.SMTP", boom)
        assert send_report(self._report(), datetime(2026, 8, 19)) is False
