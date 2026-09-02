#!/usr/bin/env bash
# The database and the MP3s live on the orphan branch `state`, as a single
# commit that is replaced on every run rather than extended.
#
# Committing them to main gave the repository a 4.2 GB history by Sep 2026 —
# 4.1 GB of MP3s that the 30-day cleanup had long since deleted from the
# tree, plus 0.5 GB of daily copies of a 4.6 MB SQLite file that never
# deltas — growing ~30 MB a day for as long as the podcast runs. A branch
# with no parent commits has no history to grow: what it holds is only ever
# the current 30 days.
#
#   scripts/state.sh pull   restore data/posts.db and data/audio/ from the branch
#   scripts/state.sh push   replace the branch with the current data/ contents
#
# Both are safe to run from a checkout of main; the files are gitignored
# there, and `push` uses a throwaway index so main's own index is untouched.

set -euo pipefail

REMOTE="${STATE_REMOTE:-origin}"
BRANCH="${STATE_BRANCH:-state}"
cd "$(git rev-parse --show-toplevel)"

case "${1:-}" in
  pull)
    if git fetch --quiet "$REMOTE" "$BRANCH" 2>/dev/null; then
      git archive FETCH_HEAD | tar -x
      echo "state: restored data/ from $REMOTE/$BRANCH ($(git rev-parse --short FETCH_HEAD))"
    else
      echo "state: no '$BRANCH' branch on $REMOTE yet — starting with empty data/"
    fi
    ;;
  push)
    if [[ ! -f data/posts.db ]]; then
      echo "state: data/posts.db is missing; refusing to publish an empty state" >&2
      exit 1
    fi
    index="$(mktemp)"; rm -f "$index"
    export GIT_INDEX_FILE="$index"
    git add -f data/posts.db
    find data/audio -maxdepth 1 -name '*.mp3' -print0 2>/dev/null \
      | xargs -0 -r git add -f
    tree="$(git write-tree)"
    unset GIT_INDEX_FILE; rm -f "$index"
    commit="$(git commit-tree "$tree" \
      -m "state $(date -u +%Y-%m-%dT%H:%M:%SZ) from $(git rev-parse --short HEAD)")"
    git push --quiet --force "$REMOTE" "$commit:refs/heads/$BRANCH"
    echo "state: published $(git ls-tree -r "$tree" --name-only | wc -l | tr -d ' ') files as $REMOTE/$BRANCH ($(git rev-parse --short "$commit"))"
    ;;
  *)
    echo "usage: $0 pull|push" >&2
    exit 2
    ;;
esac
