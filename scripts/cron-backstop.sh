#!/usr/bin/env bash
# Fire the daily pipeline when GitHub's scheduler didn't.
#
# `schedule:` is best-effort: GitHub delivers fires late under load, or drops
# them outright (no run object at all, nothing to retry). This runs from the
# desktop crontab at 05:30 Europe/London, 47 minutes after the 03:43 UTC cron
# slot in summer time and 1 hour 47 minutes after it in winter, asks whether
# any run exists for the UTC day, and dispatches one only if none does.
#
# Safe to run when the scheduled run is merely late rather than missing: the
# workflow's `feedcast-pipeline` concurrency group queues the dispatch behind
# the running one, and a second run over the same posts finds nothing new, so
# it publishes nothing and (with FEEDCAST_EMAIL_ALWAYS unset) sends no email.

set -euo pipefail

REPO="${FEEDCAST_REPO:-tbuckworth/feedcast}"
WORKFLOW="${FEEDCAST_WORKFLOW:-update-feed.yml}"

today="$(date -u +%Y-%m-%d)"

# `created` filters on the run's creation date in UTC, matching the cron slot.
count="$(gh run list --repo "$REPO" --workflow "$WORKFLOW" \
    --created "$today" --limit 50 --json databaseId --jq 'length')"

if [[ "$count" -gt 0 ]]; then
    echo "$(date -Is) ok: $count run(s) already created today"
    exit 0
fi

echo "$(date -Is) no run today — dispatching $WORKFLOW"
gh workflow run "$WORKFLOW" --repo "$REPO" --ref main
