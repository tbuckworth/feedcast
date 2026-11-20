# Second publish failed on 2026-11-20: GitHub did not list the artifact just uploaded

[Run 44681420252](https://github.com/tbuckworth/feedcast/actions/runs/44681420252)
(desktop cron dispatch, 05:30 UTC) wrote the briefing, emailed the list
(FEEDCAST_EMAIL_TO and 11 BCC) at 05:34, and pushed. The first publish
("deploy / publish") went live at 05:35 with the briefing and Zvi's "AI #195:
Opening Bell". The narrate job read "The AI Forecasting Agenda" out in full
and pushed it at 05:36.

The second publish ("deploy-narrated / publish") then failed in its "Deploy to
GitHub Pages" step:

```
05:38:18.224 Artifact github-pages-narrated-attempt-1.zip successfully finalized. Artifact ID 14604134164
05:38:18.657 Fetching artifact metadata for "github-pages-narrated-attempt-1" in this workflow run
05:38:18.890 Found 1 artifact(s)
05:38:18.892 ##[error]Fetching artifact metadata failed. Is githubstatus.com reporting issues with API requests, Pages, or Actions? Please re-run the deployment at a later time.
05:38:19.027 ##[error]Error: No artifacts named "github-pages-narrated-attempt-1" were found for this workflow run.
```

The site kept serving the first publish, whose feed.xml does not list "The AI
Forecasting Agenda". GitHub's status page reported no incident.

## Why it failed

`actions/deploy-pages` finds the artifact to deploy by listing the run's
artifacts and picking the one with the name it was given
(`getArtifactMetadata` in its `src/internal/api-client.js`). The run held two
artifacts by then: the first publish's, and the one the same job had finished
uploading 0.4 seconds before. GitHub's list returned one, the first
publish's. The list lagged the upload.

The request was not unusually early. In the 44 publishes that succeeded
between 30 Oct and 20 Nov, the action asked for the list 0.28 to 0.51 seconds
after the upload was finalized; here it asked after 0.43 seconds. The same
list, read two minutes later by the re-run, showed all three artifacts (both
of the first attempt's and the re-run's own).

The action asks once and fails when the name is missing. That is unchanged up
to v5.0.1, its latest release, so a newer version would not have helped.

## Recovery

The watchdog launched an agent at 05:39, which ran
`gh run rerun 44681420252 --failed`. The re-run uploaded
`github-pages-narrated-attempt-2`, found it, and deployed; the job finished
at 05:41. At 05:42 the live feed listed the briefing and both episodes, and
each of the three enclosures downloaded in full at the length the feed gives.
The re-run started no pipeline job, so no email was sent again.

## Fix

The action fails here before it creates a Pages deployment, so the same job
can deploy again. `publish-pages.yml` now tries the deploy a second time,
after a 30-second pause, when the first try failed without creating a
deployment. It tells the two kinds of failure apart by the action's
`page_url` output, which the action sets once the deployment exists: the
failed job above reported no URL, and the job whose deployment timed out on
10 Nov reported one. A deployment that was created and then failed is still
not tried again, because a second one under its name never starts
([publish-incident-2026-11-10.md](publish-incident-2026-11-10.md)).

The second try has not yet run on GitHub: the lag cannot be produced on
demand, and a trial run would deploy to the live site. The tests cover the
step that decides between the two kinds of failure, and the order and
conditions of the steps around it.
