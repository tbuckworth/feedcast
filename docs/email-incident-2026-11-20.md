# Gmail blocked the daily email on 2026-11-20, and nothing noticed

[Run 44681420252](https://github.com/tbuckworth/feedcast/actions/runs/44681420252)
(desktop cron dispatch, 05:30 UTC) handed the daily email to `smtp.gmail.com`
at 05:34:13. Gmail accepted it, and the pipeline logged
`Email report sent to *** and 11 bcc`.

Two seconds later Gmail refused to deliver it. Its Mail Delivery Subsystem
mailed the sender twelve delivery status notifications, one for the To
address and one for each of the eleven blind-copied readers:

```
** Message blocked **
Your message to <recipient> has been blocked.
Action: failed
Status: 5.7.1
Diagnostic-Code: smtp; Message rejected. For more information, go to https://support.google.com/mail/answer/69585
```

Nobody received the email. These were the sending account's only notices of
this kind for a Feedcast email in 90 days.

## Why nothing noticed

The pipeline counted an email as sent once the SMTP server accepted it, and
the refusal came afterwards, to the sender's inbox, which nothing read. The
update job therefore succeeded, and `scripts/watchdog.py` takes a successful
update job to mean the email went out. The same run's second publish failed
for another reason
([publish-incident-2026-11-20.md](publish-incident-2026-11-20.md)); the agent
the watchdog launched for it read the log line above and reported the email
as sent. Titus reported the missing email at 09:57.

## Recovery

A resend run rebuilds the last run's email from the database: the same
briefing and summaries, without the prediction-market notes and charts and
without the run's notices.

- 10:00: `gh workflow run update-feed.yml --ref main -f resend_report=true`
  ([run 44715321543](https://github.com/tbuckworth/feedcast/actions/runs/44715321543)),
  which emails only the To address. No notice followed.
- 10:04: the same with `-f notify_list=true`
  ([run 44715865004](https://github.com/tbuckworth/feedcast/actions/runs/44715865004)),
  which emails the list. No notice followed.

## Why Gmail blocked it

Gmail does not say, and the block could not be reproduced. Each of these was
sent to the To address alone through the Gmail API, and each was delivered:

- the lines that only the blocked email had (the market notes, the run's
  notices and the link to a post still being narrated), as plain text;
- its two chart images;
- the blocked email itself, forwarded.

Google's Workspace status page listed no incident.

What differed was the machine the email came from. The blocked email was sent
from a GitHub-hosted runner in AWS (`Cloud: AWS`, `Region: us-west-2` in the
job's log); both resends came from runners in Azure. GitHub first placed a
job of this workflow in AWS on 16 Nov, and of the 113 update, narrate and
publish jobs between 27 Oct and 20 Nov, four ran there. Twenty-five emails
went to the list in that period. Gmail delivered all twenty-three that came
from Azure. Two came from AWS: the email of 16 Nov (`us-east-1`), which was
delivered, and this one. The address the email came from is therefore the
likeliest cause, since mail servers commonly distrust shared cloud addresses,
but one blocked email cannot show it.

## Fix

After each send the pipeline waits 20 seconds and reads the sender's inbox
over IMAP, with the SMTP login (`src/bounces.py`). A delivery status
notification that is dated after the send and reports a failure for one of
the email's recipients makes the send a failed one, and so does an inbox that
cannot be read. A failed send fails the update job after it has published,
which launches the watchdog's agent. `scripts/watchdog_brief.md` tells the
agent to resend to Titus alone. When that resend passes and the first email
bounced for every recipient, no reader has the email, and the agent resends
it to the list without asking, as Titus decided on 20 Nov. In every other
case it asks him first.

The check first read the real inbox at 11:58 on 20 Nov, in a resend to Titus
alone ([run 44731686732](https://github.com/tbuckworth/feedcast/actions/runs/44731686732)),
and found no bounce.

The tests read a stand-in inbox that serves a notice copied from one of the
twelve.
