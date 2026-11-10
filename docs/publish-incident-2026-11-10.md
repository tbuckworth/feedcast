# Pages deploy stalled on 2026-11-10, and re-running it could not recover

[Run 42762503733](https://github.com/tbuckworth/feedcast/actions/runs/42762503733)
(desktop cron dispatch, 05:30 UTC) wrote and narrated today's briefing and
five episodes. It emailed the list (FEEDCAST_EMAIL_TO and 11 BCC) at 05:33,
then pushed main and `state`. The narrate job read two posts out in full and
pushed them too.

The first publish ("deploy / publish") then failed. `actions/deploy-pages`
created the Pages deployment at 05:34:56, and the deployment sat at
`syncing_files` until the action's 10-minute limit. The action cancelled it
at 05:44:58 and failed. GitHub's status page reported no incident. From
10 Oct to 10 Nov the slowest of 39 successful deploys had taken 176 seconds,
and 34 of the 39 had taken under 30.
The second publish ("deploy-narrated") was skipped, because it needs the
first. The live site kept serving the 9 Nov feed, so the email's audio links
returned 404.

## Why re-running the publish could not recover it

The watchdog launched an agent at 05:45, which ran
`gh run rerun 42762503733 --failed`. The re-run's deployment never got a
status. It reported an empty status from the first read, while the stalled
one had reported `syncing_files`.

`actions/deploy-pages` names each deployment after the commit the run
started from (`GITHUB_SHA`, sent as `pages_build_version`), and that name is
also the deployment's ID. The re-run therefore made a deployment under the
same name, 1e1315c3b3129e26f693e7baedd112d132291e8e, as the one just
cancelled. GitHub's API asks for a unique build version. A second deployment
under a name whose first deployment succeeded does go live: the
narrated-post publish does this every day. A deployment under the name of a
cancelled one never starts. The action reads `GITHUB_SHA` itself, and the
runner resets that variable for every action step, so a workflow cannot
give the action another name.

## Recovery

At 05:51 the agent cancelled the re-run and dispatched a forced dev run,
`gh workflow run update-feed.yml --ref main -f force=true`
([run 42764771311](https://github.com/tbuckworth/feedcast/actions/runs/42764771311)).
It started from a newer commit (4ffb58c), so its deployment had a new name.
It found no new posts, sent no email, and deployed in about 20 seconds; the
site was live at 05:55. The live feed then matched main's feed.xml byte for
byte. It listed today's briefing and five episodes, and all 78 of its
enclosures returned 200 with the length the feed gives.

## Fix

`scripts/deploy-pages.sh` replaces `actions/deploy-pages` in
`.github/workflows/publish-pages.yml`. It makes the deployment through the
same API, under a name built from the commit, the run, the artifact's name
(which carries the run attempt) and the try. It allows each try five
minutes, then cancels it and tries again under a new name. It makes two
tries, which together get the same ten minutes the action allowed one. A
re-run of a failed publish now deploys under names of its own, and so does
each of a run's two publishes. Tests in `tests/test_workflow_dev_mode.py`
run the workflow's deploy step against a stand-in for the Pages API. The
stand-in stalls deployments, fails them, and gives no status to a deployment
made under a cancelled name.
