# Main push refused on 2026-10-31: email sent, audio never published

[Run 41172828466](https://github.com/tbuckworth/feedcast/actions/runs/41172828466)
(desktop cron dispatch, 05:30 UTC) wrote and narrated two episodes:

- Daily News Briefing - 2026-10-31
- "Childhood and Education #22: Voice Without Exit" by Zvi

It emailed the list (FEEDCAST_EMAIL_TO and 11 BCC) and published the database
and both MP3s to the `state` branch. Then GitHub refused the push to main:

```
remote: fatal error in commit_refs
 ! [remote rejected] main -> main (failure)
```

This error came from GitHub's server, not from a conflict: the rebase just
before it reported main up to date. `scripts/ci-commit-and-push.sh` ran `git push`
once. When it failed, the "Commit and push" step failed, `pushed` was false,
and the deploy and narrate jobs were skipped. GitHub Pages kept serving
the 30 Oct site. The email's audio links (`audio/<file>.mp3`) returned 404, and
the feed had no item for 31 Oct, so Pocket Casts showed nothing new.

No other episode was affected: every one of the 74 enclosures in the live
feed returned 200 before the recovery.

## Recovery

A forced dev run, `gh workflow run update-feed.yml --ref main -f force=true`
([run 41187202717](https://github.com/tbuckworth/feedcast/actions/runs/41187202717),
09:05 UTC). It restored `state` (92d2131), skipped the briefing because
today's already existed, found no new posts, regenerated `feed.xml` from the
database, pushed main and deployed. A dev run emails only FEEDCAST_EMAIL_TO,
so the list was not emailed again. Its successful push also makes the
`guard` stop GitHub's late scheduled run for the day, which would otherwise
have run as a normal run and emailed the list a second time.

Checked afterwards: both MP3s return 200 `audio/mp3`, the same size as the
blobs on `state`. The live feed lists today's briefing first, and all 73 of its
enclosures return 200. The WebSub hub accepted the publish ping (HTTP 204).

## Fix

`scripts/ci-commit-and-push.sh` retries each push up to 5 times, waiting 10s,
20s, 40s and 80s between attempts. Before each retry of the main push it
re-syncs with main. This covers the case where another push landed in between.
If all five attempts fail, the step still fails as before. The state branch is
already published by then, so the next run regenerates the feed.
Tests in `tests/test_bundle.py` use a pre-receive hook to make a local remote
refuse pushes.

The email still goes out before the publish, so a deploy that fails for any
other reason would again leave the email's links dead until a re-run.
