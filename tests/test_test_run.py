"""A test run must never reach the BCC list."""

from datetime import datetime

from src.email_report import ReportEpisode, RunReport, is_test_run, send_report


def _report():
    return RunReport(episodes=[ReportEpisode(title="t", author="a", feed_name="f", link="",
                                             audio_url="https://x/a.mp3", duration_seconds=60,
                                             fidelity={"status": "clean", "flags": []})],
                     recent=[], failures=[], feed_url="https://x/feed.xml", site_url="https://x",
                     total_in_feed=1)


class FakeSMTP:
    sent = {}

    def __init__(self, host, port, timeout=None): ...
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, **kw): ...
    def login(self, u, p): ...
    def send_message(self, msg): FakeSMTP.sent["msg"] = msg


def _env(monkeypatch, **extra):
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    for k, v in {"FEEDCAST_EMAIL_TO": "titus@example.com", "SMTP_USER": "s@example.com",
                 "GMAIL_APP_PASSWORD": "pw", "FEEDCAST_EMAIL_BCC": "friend@example.com", **extra}.items():
        monkeypatch.setenv(k, v)


def test_normal_run_bccs_and_shows_the_check_line(monkeypatch):
    _env(monkeypatch); monkeypatch.delenv("FEEDCAST_TEST_RUN", raising=False)
    assert not is_test_run()
    assert send_report(_report(), datetime(2026, 9, 3)) is True
    msg = FakeSMTP.sent["msg"]
    assert msg["Bcc"] == "friend@example.com" and not msg["Subject"].startswith("[TEST]")
    html = msg.get_body(preferencelist=("html",)).get_content()
    text = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Checked against source: no issues" in html and "(Checked against source: no issues)" in text


def test_test_run_drops_bcc_and_tags_subject(monkeypatch):
    _env(monkeypatch, FEEDCAST_TEST_RUN="true")
    assert is_test_run()
    assert send_report(_report(), datetime(2026, 9, 3)) is True
    msg = FakeSMTP.sent["msg"]
    assert msg["Bcc"] is None and msg["To"] == "titus@example.com"
    assert msg["Subject"].startswith("[TEST] Feedcast")


def test_false_string_is_not_a_test_run(monkeypatch):
    _env(monkeypatch, FEEDCAST_TEST_RUN="false")
    assert not is_test_run()
