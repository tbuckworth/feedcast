Feedcast's morning run on $date has not got the email and the episodes out, and scripts/watchdog.py launched you to recover it. Titus listens from $ready_by ($timezone): get the briefing and today's episodes into the live feed ($feed_url), with audio that plays, before then. Recover first and diagnose afterwards.

What the watchdog saw: $reason

Today's runs of update-feed.yml:
$runs

Follow AGENTS.md. In particular:
- Never send the daily email to the BCC list a second time. A run that is dispatched by hand with an input is a dev run, and it emails only Titus. A bare dispatch is the daily run, and it emails the list.
- The email goes out before the audio is published. Do not propose holding it.

Recovery, by what failed (`gh run view ID --log-failed` shows the step):
- No run today has a successful update job, and none sent the email: the job failed in setup, in the pipeline, or never started. Dispatch the daily run as scripts/cron-backstop.sh does: `gh workflow run update-feed.yml --ref main`. It emails the list once, which is right, because nothing went out.
- The update job sent the email but did not push ("Commit and push" failed), or a deploy failed after the push: run `gh run rerun ID --failed`. If the push itself keeps failing, dispatch `gh workflow run update-feed.yml --ref main -f force=true`. That is a dev run: it republishes and emails only Titus.
- The narrate job failed: run `gh run rerun ID --failed`. The posts it was reading out wait in the database, and the next run retries them anyway.
- A run is queued or stuck: look at GitHub's status page (https://www.githubstatus.com) before you dispatch anything. A second run queues behind the first.

Verify that it worked:
- The live feed.xml lists today's briefing and each episode added today. Fetch it with a query string, which gets past the site's 10-minute cache.
- Each of those episodes' audio answers 200 with the length the feed gives.

Then:
- Email Titus as soon as the episodes are live (`agent-mail send`, after `agent-mail guide`), saying what failed and what you did.
- Find the root cause and fix it on your branch, with a test, as a pull request against main. Merge only if Titus says so.
- Record milestones with `agent-status note`.
