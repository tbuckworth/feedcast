"""Tests for author extraction and the emailed run report."""

import ast
from datetime import datetime
from pathlib import Path

import pytest

from src import main
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

    def test_keeps_every_author_capping_is_the_formatters_job(self):
        entry = {"authors": [{"name": f"P{i}"} for i in range(9)]}
        assert len(extract_authors(entry, "Feed")) == 9
        assert format_authors(extract_authors(entry, "Feed")).count(",") == MAX_AUTHORS - 1

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

    def test_email_is_off_without_a_recipient(self, monkeypatch):
        """FEEDCAST_EMAIL_TO is the off switch: unset, nothing is sent and
        nothing failed, whatever the SMTP credentials say."""
        from src import email_report
        monkeypatch.delenv("FEEDCAST_EMAIL_TO", raising=False)
        monkeypatch.setenv("SMTP_USER", "sender@example.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
        assert email_report.send_report(RunReport()) is None

    @pytest.mark.parametrize("missing", ["SMTP_USER", "GMAIL_APP_PASSWORD"])
    def test_a_recipient_without_credentials_is_a_failed_send(self, monkeypatch, capsys, missing):
        """A missing or rotated CI secret must not quietly stop all reporting."""
        from src import email_report
        monkeypatch.setenv("FEEDCAST_EMAIL_TO", "reader@example.com")
        monkeypatch.setenv("SMTP_USER", "sender@example.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        monkeypatch.setenv(missing, "")
        assert email_report.send_report(RunReport()) is False
        assert "Email report failed" in capsys.readouterr().out


class TestFailedSendFailsTheRun:
    """src.main publishes as normal, then the workflow fails the job."""

    @pytest.mark.parametrize("recipient,user,recorded", [
        ("", "sender@example.com", ""),                      # email off: nothing failed
        ("reader@example.com", "", "report_failed=true\n"),  # on, but no login to send with
    ])
    def test_only_a_failed_send_is_recorded(self, monkeypatch, tmp_path, recipient, user, recorded):
        monkeypatch.setenv("FEEDCAST_EMAIL_TO", recipient)
        monkeypatch.setenv("SMTP_USER", user)
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        outputs = tmp_path / "github_output"
        outputs.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        main._email(RunReport(), operator_only=True)
        assert outputs.read_text() == recorded

    def test_main_sends_every_report_through_the_recording_helper(self):
        tree = ast.parse(Path(main.__file__).read_text())
        callers = [fn.name for fn in ast.walk(tree)
                   if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                   for node in ast.walk(fn)
                   if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "send_report"]
        assert callers == ["_email"]


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
        for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_PASSWORD",
                    "FEEDCAST_EMAIL_FROM", "FEEDCAST_EMAIL_BCC"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("FEEDCAST_EMAIL_TO", "reader@example.com")
        monkeypatch.setenv("SMTP_USER", "sender@example.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
        return sent

    def test_a_report_that_went_out_records_nothing(self, fake_smtp, monkeypatch, tmp_path):
        outputs = tmp_path / "github_output"
        outputs.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        main._email(RunReport())
        assert "msg" in fake_smtp
        assert outputs.read_text() == ""

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

    def test_bcc_recipients_are_added(self, fake_smtp, monkeypatch):
        """Extra readers are blind-copied, one address or several."""
        from src.email_report import send_report
        monkeypatch.setenv("FEEDCAST_EMAIL_BCC", "one@example.com, two@example.com")
        assert send_report(self._report(), datetime(2026, 8, 19)) is True

        msg = fake_smtp["msg"]
        assert msg["To"] == "reader@example.com"
        assert msg["Bcc"] == "one@example.com, two@example.com"

    def test_blank_bcc_var_adds_no_header(self, fake_smtp, monkeypatch):
        """An unset GitHub Actions secret arrives as '' — no empty Bcc header."""
        from src.email_report import send_report
        monkeypatch.setenv("FEEDCAST_EMAIL_BCC", "")
        send_report(self._report(), datetime(2026, 8, 19))
        assert fake_smtp["msg"]["Bcc"] is None

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


class TestRegressions:
    """Both of these were live bugs, caught in review."""

    def test_six_authors_survive_extraction_to_display(self):
        """extract_authors must not pre-truncate, or 'and others' is unreachable
        and the sixth co-author vanishes without trace."""
        entry = {"authors": [{"name": n} for n in ["A", "B", "C", "D", "E", "F"]]}
        names = extract_authors(entry, "Feed")
        assert len(names) == 6, "extraction must keep every author"
        assert format_authors(names) == "A, B, C, D, E and others"

    def test_malformed_smtp_port_is_a_failed_send(self, monkeypatch, capsys):
        """send_report promises never to raise; a bad SMTP_PORT repo var used to
        throw ValueError straight through and fail the whole pipeline run. It
        then quietly became 587 instead; now it is a send that failed, which
        the workflow turns into a failed job, and nothing is sent."""
        from src.email_report import send_report

        captured = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                captured["port"] = port

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def starttls(self, context=None):
                pass

            def login(self, *a):
                pass

            def send_message(self, msg):
                pass

        monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
        monkeypatch.setenv("FEEDCAST_EMAIL_TO", "reader@example.com")
        monkeypatch.setenv("SMTP_USER", "sender@example.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
        monkeypatch.setenv("SMTP_PORT", "not-a-number")

        assert send_report(RunReport(), datetime(2026, 8, 19)) is False
        assert captured == {}
        assert "SMTP_PORT='not-a-number' is not a number" in capsys.readouterr().out
