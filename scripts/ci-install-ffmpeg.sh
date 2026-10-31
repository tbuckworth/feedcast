#!/usr/bin/env bash
# Install ffmpeg on a GitHub runner, bounded and retried.
#
# apt hung here indefinitely on 2026-08-19: the azure.archive.ubuntu.com
# mirror failed every index (Ign:), the fallback stalled mid-fetch, and apt
# has no default timeout. Skip apt when ffmpeg is already on the image, and
# bound + retry it when it isn't. Shared by the update and narrate jobs.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/retry.sh"
if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg already present: $(ffmpeg -version | head -1)"
  exit 0
fi
APT_OPTS=(
  -o Acquire::Retries=3
  -o Acquire::http::Timeout=20
  -o Acquire::https::Timeout=20
  -o Acquire::ForceIPv4=true
)
install_ffmpeg() {
  echo "::group::ffmpeg install"
  sudo timeout 90 apt-get update "${APT_OPTS[@]}" \
    && sudo timeout 240 apt-get install -y --no-install-recommends "${APT_OPTS[@]}" ffmpeg
  local status=$?
  echo "::endgroup::"
  return "$status"
}
retry "Installing ffmpeg" 3 10 "" install_ffmpeg || exit 1
ffmpeg -version | head -1
