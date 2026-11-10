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

## A fix that GitHub refused, reverted the same day

PR #89 replaced `actions/deploy-pages` with a script that made the
deployment through the same API, under a name built from the commit, the
run, the artifact's name and the try. The first publish after it merged
([run 42791455106](https://github.com/tbuckworth/feedcast/actions/runs/42791455106))
got `404 Not Found` from `POST /repos/{owner}/{repo}/pages/deployments` on
both tries. Requests sent with a deliberately invalid OIDC token showed why.
The API answers 404 to any build version that is not the full SHA of a
commit in the repository: an invented 40-character SHA and a 7-character
prefix of a real one were refused too. Only a real commit's full SHA got as
far as the token check. A deployment's name is therefore always a commit,
and a new name needs a new commit. PR #89 was reverted.

A publish whose deployment was cancelled is recovered by dispatching a
forced dev run, `gh workflow run update-feed.yml --ref main -f force=true`.
The failed run has already pushed to main, so the dev run starts from a
newer commit and its deployment gets a new name. Re-running the failed job
reuses the cancelled deployment's name.
