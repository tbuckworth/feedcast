#!/usr/bin/env bash
# Run scripts/watchdog.py from the desktop crontab, a few minutes after
# scripts/cron-backstop.sh. Cron starts in $HOME with a bare PATH, and gh, uv
# and agent-spawn live in ~/.local/bin.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PATH="$HOME/.local/bin:$PATH"
exec uv run python -m scripts.watchdog
