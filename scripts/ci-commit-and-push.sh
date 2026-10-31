#!/usr/bin/env bash
# Commit the published files to main and the database + MP3s to `state`.
#
# Shared by the update job (first publish) and the narrate job (second). The
# database and MP3s are gitignored on main; they go to the `state` branch.
# Main gets the feed, the site pages, transcripts and the per-episode source
# bundles.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/retry.sh"
message="${1:-Update podcast feed}"
# GitHub sometimes refuses a push with a server error, such as "remote: fatal
# error in commit_refs" on 2026-10-31 (docs/publish-incident-2026-10-31.md).
# Each push gets this many attempts, with a pause that doubles after each
# failure (10s, 20s, 40s, 80s).
attempts="${PUSH_ATTEMPTS:-5}"
delay="${PUSH_RETRY_DELAY_SECONDS:-10}"
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add output/ data/sources/
git diff --staged --quiet || git commit -m "$message"

# Pull latest. If the rebase conflicts (e.g. binary files), merge instead with
# -X ours, which settles every conflict in this run's favour; the warning names
# the files that overrode, read before --abort forgets them.
sync_with_main() {
  if ! git pull --rebase origin main; then
    conflicted="$(git diff --name-only --diff-filter=U | paste -sd ' ' -)"
    git rebase --abort
    echo "::warning title=Feedcast commit::Rebase onto main conflicted in: ${conflicted}. Merged with -X ours instead, so this run's side of each conflict replaced main's"
    git pull --no-rebase origin main -X ours
    git add output/ data/sources/
    git diff --staged --quiet || git commit -m "$message (merge)"
  fi
}

sync_with_main
# State first: if this push lands and the main push fails, the next run
# regenerates feed.xml from the database anyway. The other order can
# advertise audio that was never published.
retry "Pushing the state branch" "$attempts" "$delay" "" scripts/state.sh push
# Re-sync before each retry, in case the failure was another push landing on
# main first.
retry "Pushing main" "$attempts" "$delay" sync_with_main git push
