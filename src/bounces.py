"""Bounces: the emails a mail server accepted and then refused to deliver.

An SMTP server can accept a message and refuse it seconds later. Gmail did so
on 2026-11-20: it blocked the daily email for all twelve recipients two
seconds after accepting it (docs/email-incident-2026-11-20.md). smtplib has
returned by then. The server reports the refusal as a delivery status
notification (RFC 3464), one per recipient, mailed to the sender. `bounced`
reads the sender's inbox over IMAP for those notices, once, WAIT_SECONDS
after the send. A refusal that comes later, from a recipient's own server
after its retries for one, is not seen.
"""

import email
import imaplib
import ssl
import time
from collections.abc import Iterable
from datetime import datetime, timedelta
from email import policy
from email.message import EmailMessage, Message
from email.utils import parsedate_to_datetime

IMAP_PORT = 993
# How long after the send the inbox is read. Gmail's notices of 2026-11-20
# arrived two seconds after it.
WAIT_SECONDS = 20
# A notice is dated by the mail server's clock and the send by this machine's,
# so a notice dated this long before the send still counts as the send's. Two
# sends to one recipient are minutes apart at the closest.
CLOCK_SLACK = timedelta(seconds=60)


def bounced(host: str, user: str, password: str, recipients: Iterable[str],
            sent_at: datetime) -> dict[str, str]:
    """The recipients a message sent at `sent_at` bounced for, with the server's reason for each.

    Waits WAIT_SECONDS, then reads the notices in `user`'s inbox on `host`
    that are dated after the send and name one of `recipients`. The inbox is
    opened read-only, so the notices stay unread there. `sent_at` carries its
    time zone. Raises when the inbox cannot be read (OSError, imaplib's
    errors, RuntimeError for a command the server refused).
    """
    time.sleep(WAIT_SECONDS)
    wanted = {recipient.lower() for recipient in recipients}
    earliest = sent_at - CLOCK_SLACK
    # SINCE compares dates only, in the server's own time zone, so ask from the
    # day before and compare the times here.
    since = imaplib.Time2Internaldate(earliest - timedelta(days=1))[1:12]
    # Servers send their notices as MAILER-DAEMON or as postmaster. Asking for
    # those two keeps the rest of the inbox unfetched; _failures then tells a
    # notice from any other mail of theirs.
    senders = ("OR", "FROM", '"mailer-daemon"', "FROM", '"postmaster"')
    found: dict[str, str] = {}
    with imaplib.IMAP4_SSL(host, IMAP_PORT, ssl_context=ssl.create_default_context(),
                           timeout=60) as inbox:
        inbox.login(user, password)
        _ok("SELECT", inbox.select("INBOX", readonly=True))
        numbers = _ok("SEARCH", inbox.search(None, *senders, "SINCE", since))
        for number in numbers[0].split():
            fetched = _ok("FETCH", inbox.fetch(number, "(BODY.PEEK[])"))
            notice = email.message_from_bytes(fetched[0][1], policy=policy.default)
            if parsedate_to_datetime(notice["Date"]) < earliest:
                continue
            found.update((recipient, reason) for recipient, reason in _failures(notice).items()
                         if recipient in wanted)
    return found


def _ok(command: str, response: tuple[str, list]) -> list:
    """The data of an IMAP response; imaplib returns a refused command instead of raising."""
    status, data = response
    if status != "OK":
        raise RuntimeError(f"IMAP {command} answered {status}: {data!r}")
    return data


def _failures(notice: EmailMessage) -> dict[str, str]:
    """Each recipient a delivery status notification reports as failed, lower-cased, with the reason.

    {} for a message that is not such a notification, and for a recipient the
    notice only reports as delayed or delivered.
    """
    if (notice.get_content_type() != "multipart/report"
            or notice.get_param("report-type") != "delivery-status"):
        return {}
    failed = {}
    for part in notice.walk():
        if part.get_content_type() != "message/delivery-status":
            continue
        # The parser gives this part's blocks of fields as messages with no
        # body: the first is about the message, the others one per recipient.
        blocks: list[Message] = part.get_payload()
        for block in blocks:
            if block.get("Action", "").strip().lower() != "failed":
                continue
            # "rfc822; reader@example.com"
            recipient = block["Final-Recipient"].split(";", 1)[1].strip().lower()
            failed[recipient] = " ".join(block.get("Diagnostic-Code", block["Status"]).split())
    return failed
