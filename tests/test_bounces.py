"""An email the mail server accepted and then refused is a failed send.

Gmail accepted the daily email on 2026-11-20 and blocked it for every
recipient two seconds later (docs/email-incident-2026-11-20.md). The only
sign was in the sender's inbox, which the `inbox` fixture stands in for.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src import bounces, main
from src.email_report import RunReport, send_report
from tests.conftest import GMAIL_BLOCKED, bounce_notice

LOGIN = ("imap.example.com", "bot@example.com", "pw")
SENT = datetime(2026, 11, 20, 5, 34, 13, tzinfo=UTC)


def test_a_notice_names_the_recipient_and_the_servers_reason(inbox):
    inbox.notices.append(bounce_notice("Reader@Example.com", SENT + timedelta(seconds=2)))
    assert bounces.bounced(*LOGIN, ["reader@example.com", "other@example.com"], SENT) == {
        "reader@example.com": f"smtp; {GMAIL_BLOCKED}"}
    assert (inbox.host, inbox.port, inbox.logins) == ("imap.example.com", 993,
                                                      [("bot@example.com", "pw")])
    # Read-only, so the notices stay unread for the person whose inbox it is.
    assert inbox.selected == [("INBOX", True)]
    # The server is asked for what its two usual senders of notices sent from
    # the day before onwards: its SINCE compares dates only, in a time zone of
    # its own.
    assert inbox.searches == [("OR", "FROM", '"mailer-daemon"', "FROM", '"postmaster"',
                               "SINCE", "19-Nov-2026")]


def test_a_notice_from_postmaster_counts_and_mail_from_anyone_else_does_not(inbox):
    """Some servers send their notices as postmaster. A notice that somebody
    else forwarded is not the server's word on this email."""
    when = SENT + timedelta(seconds=2)
    inbox.notices += [
        bounce_notice("reader@example.com", when, sender="postmaster@example.org"),
        bounce_notice("other@example.com", when, sender="A Reader <someone@example.org>")]
    assert bounces.bounced(*LOGIN, ["reader@example.com", "other@example.com"], SENT) == {
        "reader@example.com": f"smtp; {GMAIL_BLOCKED}"}


def test_an_inbox_with_no_notice_means_nothing_bounced(inbox):
    assert bounces.bounced(*LOGIN, ["reader@example.com"], SENT) == {}


def test_a_notice_from_before_the_send_is_another_emails(inbox):
    inbox.notices.append(bounce_notice("reader@example.com", SENT - timedelta(minutes=4)))
    assert bounces.bounced(*LOGIN, ["reader@example.com"], SENT) == {}


def test_a_notice_for_someone_this_email_did_not_go_to_is_another_emails(inbox):
    inbox.notices.append(bounce_notice("stranger@example.com", SENT + timedelta(seconds=2)))
    assert bounces.bounced(*LOGIN, ["reader@example.com"], SENT) == {}


def test_a_notice_of_a_delay_is_not_a_bounce(inbox):
    inbox.notices.append(bounce_notice("reader@example.com", SENT + timedelta(seconds=2),
                                       action="delayed"))
    assert bounces.bounced(*LOGIN, ["reader@example.com"], SENT) == {}


def test_an_inbox_that_cannot_be_read_raises(inbox, monkeypatch):
    inbox.notices.append(bounce_notice("reader@example.com", SENT + timedelta(seconds=2)))
    monkeypatch.setattr("imaplib.IMAP4_SSL.search", lambda self, *a: ("NO", [b"try later"]))
    with pytest.raises(RuntimeError, match="SEARCH.*try later"):
        bounces.bounced(*LOGIN, ["reader@example.com"], SENT)


def test_the_check_waits_for_the_notices_before_it_reads(inbox, monkeypatch):
    """Gmail's notices came two seconds after the send. The wait is real in
    production; a stand-in sleep records it here."""
    waits = []
    monkeypatch.setattr(bounces, "WAIT_SECONDS", 20)
    monkeypatch.setattr("time.sleep", waits.append)
    bounces.bounced(*LOGIN, ["reader@example.com"], SENT)
    assert waits == [20] and inbox.logins


class TestTheReportEmail:
    """send_report with the stand-in SMTP server (`smtp`) and inbox."""

    @pytest.fixture
    def outputs(self, monkeypatch, tmp_path):
        path = tmp_path / "github_output"
        path.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(path))
        return path

    def test_a_bounced_report_is_a_failed_send(self, smtp, inbox, outputs, capsys):
        """The run of 2026-11-20: accepted, then blocked for the operator and the list."""
        now = datetime.now(UTC)
        inbox.notices += [bounce_notice("operator@example.com", now),
                          bounce_notice("list@example.com", now)]
        main._email(RunReport())
        assert len(smtp) == 1
        assert outputs.read_text() == "report_failed=true\n"
        out = capsys.readouterr().out
        assert "bounced for 2 of 2 recipients" in out and GMAIL_BLOCKED in out
        # The Actions log is public: no blind-copied address in it.
        assert "list@example.com" not in out

    def test_a_reason_that_names_a_reader_is_logged_without_the_address(self, smtp, inbox,
                                                                        capsys):
        """A reader's own mail server often repeats the address it refused."""
        inbox.notices.append(bounce_notice(
            "list@example.com", datetime.now(UTC),
            reason="550 5.1.1 <List@Example.com>: no mailbox list@example.com: User unknown"))
        assert send_report(RunReport()) is False
        out = capsys.readouterr().out
        assert "bounced for 1 of 2 recipients" in out
        assert "550 5.1.1 <address>: no mailbox <address>: User unknown" in out
        assert "list@example.com" not in out.lower()

    def test_a_report_nobody_bounced_is_sent(self, smtp, inbox, outputs, capsys):
        # Yesterday's notice, still in the inbox.
        inbox.notices.append(bounce_notice("operator@example.com",
                                           datetime.now(UTC) - timedelta(days=1)))
        assert send_report(RunReport()) is True
        assert inbox.logins == [("bot@example.com", "pw")]
        assert inbox.host == "imap.gmail.com"
        assert "no bounce" in capsys.readouterr().out

    def test_the_inbox_is_the_one_imap_host_names(self, smtp, inbox, monkeypatch):
        monkeypatch.setenv("IMAP_HOST", "imap.example.org")
        send_report(RunReport())
        assert inbox.host == "imap.example.org"

    def test_a_bounce_for_a_reader_a_dev_run_left_out_is_not_this_emails(self, smtp, inbox,
                                                                         monkeypatch):
        """A dev run emails the operator only, so a notice for the list is not its own."""
        monkeypatch.setenv("FEEDCAST_TEST_RUN", "true")
        inbox.notices.append(bounce_notice("list@example.com", datetime.now(UTC)))
        assert send_report(RunReport()) is True

    def test_a_report_whose_delivery_cannot_be_checked_is_a_failed_send(self, smtp, outputs,
                                                                        monkeypatch, capsys):
        """Not knowing is not the same as delivered: the run must not stay green."""
        def refuse(self, user, password):
            raise OSError("connection reset")

        monkeypatch.setattr("imaplib.IMAP4_SSL.login", refuse)
        main._email(RunReport())
        assert len(smtp) == 1
        assert outputs.read_text() == "report_failed=true\n"
        assert "could not be read for bounces: OSError: connection reset" in capsys.readouterr().out
