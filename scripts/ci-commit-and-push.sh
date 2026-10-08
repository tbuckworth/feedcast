#!/usr/bin/env bash
# Commit the published files to main and the database + MP3s to `state`.
#
# Shared by the update job (first publish) and the narrate job (second). The
# database and MP3s are gitignored on main; they go to the `state` branch.
# Main gets the feed, the site pages, transcripts and the per-episode source
# bundles.
set -euo pipefail
message="${1:-Update podcast feed}"
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add output/ data/sources/
git diff --staged --quiet || git commit -m "$message"
# Pull latest — if rebase fails (e.g. binary conflicts), fall back to merge
if ! git pull --rebase origin main; then
  echo "Rebase failed, falling back to merge..."
  git rebase --abort
  git pull --no-rebase origin main -X ours
  git add output/ data/sources/
  git diff --staged --quiet || git commit -m "$message (merge)"
fi
# State first: if this push lands and the main push fails, the next run
# regenerates feed.xml from the database anyway. The other order can
# advertise audio that was never published.
scripts/state.sh push
git push
