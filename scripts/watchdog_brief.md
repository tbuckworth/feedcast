Feedcast's morning run on $date has not got the email and the episodes out, and scripts/watchdog.py launched you to recover it. Titus listens from $ready_by ($timezone): get the briefing and today's episodes into the live feed ($feed_url), with audio that plays, before then. Recover first and diagnose afterwards.

What the watchdog saw: $reason

Today's runs of update-feed.yml:
$runs

Follow AGENTS.md. In particular:
- Never send the daily email to the BCC list a second time. A run that is dispatched by hand with an input is a dev run, and it emails only Titus unless `notify_list=true` is one of its inputs. A bare dispatch is the daily run, and it emails the list.
- The email goes out before the audio is published. Do not propose holding it.

Recovery, by what failed (`gh run view ID --log-failed` shows the step):
- No run today has a successful update job, and none sent the email: the job failed in setup, in the pipeline, or never started. Dispatch the daily run as scripts/cron-backstop.sh does: `gh workflow run update-feed.yml --ref main`. It emails the list once, which is right, because nothing went out.
- The update job failed at "Fail the job if the report email was not sent" (it published first, so do not dispatch the daily run again): the email did not go out, and a line of the "Run pipeline" log that starts "Email report failed" says why. The mail server may have bounced it after accepting it, as Gmail did for all twelve recipients on 2026-11-20 (docs/email-incident-2026-11-20.md). Once the narrate job has finished, so that the email lists the posts it read out, dispatch `gh workflow run update-feed.yml --ref main -f resend_report=true`. That is a dev run: it emails only Titus, and it fails if its email bounced too. If its update job succeeds, and the "Email report failed" line says the first email bounced for every recipient ("bounced for 12 of 12 recipients", the two numbers equal), then no reader has the email: send it to the list with `gh workflow run update-feed.yml --ref main -f resend_report=true -f notify_list=true`, without asking (Titus decided this on 2026-11-20). Dispatch that run once only, whatever becomes of it. In every other case (the dev run's update job failed, the first email bounced for only some of the recipients, or it failed for another reason) do not email the list. Then email Titus: say why the first email failed and for how many recipients, and what each resend did, and if you did not email the list, ask whether you should.
- The update job sent the email but did not push ("Commit and push" failed): run `gh run rerun ID --failed`. If the push keeps failing, dispatch `gh workflow run update-feed.yml --ref main -f force=true`. That is a dev run: it republishes and emails only Titus.
- A deploy failed after the push, and its "Deploy to GitHub Pages" step, or its second try "Deploy to GitHub Pages again", timed out or was cancelled (the deployment stalled at `syncing_files`, say; after the first try the job fails at "Check that deploying again can work"): dispatch `gh workflow run update-feed.yml --ref main -f force=true`. A re-run cannot recover it, because its deployment takes the cancelled one's name and never starts (docs/publish-incident-2026-11-10.md).
- A deploy failed in any other way: run `gh run rerun ID --failed`, and dispatch the forced dev run if the re-run does not publish.
- The narrate job failed: run `gh run rerun ID --failed`. The posts it was reading out wait in the database, and the next run retries them anyway.
- A run is queued or stuck: look at GitHub's status page (https://www.githubstatus.com) before you dispatch anything. A second run queues behind the first.

Verify that it worked:
- The live feed.xml lists today's briefing and each episode added today. Fetch it with a query string, which gets past the site's 10-minute cache.
- Each of those episodes' audio answers 200 with the length the feed gives.

Then:
- Email Titus as soon as the episodes are live (`agent-mail send`, after `agent-mail guide`), saying what failed and what you did.
- Find the root cause and fix it on your branch, with a test, as a pull request against main. Merge only if Titus says so.
- Record milestones with `agent-status note`.
