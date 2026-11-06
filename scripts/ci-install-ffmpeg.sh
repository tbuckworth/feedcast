#!/usr/bin/env bash
# Install ffmpeg on a GitHub runner, bounded and retried.
#
# apt hung here indefinitely on 2026-08-19: the azure.archive.ubuntu.com
# mirror failed every index (Ign:), the fallback stalled mid-fetch, and apt
# has no default timeout. Skip apt when ffmpeg is already on the image, and
# bound + retry it when it isn't. Shared by the update and narrate jobs.
#
# apt keeps the packages it fetches in FFMPEG_DEB_CACHE, a directory the
# setup-pipeline action restores from and saves to the Actions cache: the
# mirror trickled the 63 MB at about 40 KB/s on 2026-10-27 and 2026-11-06,
# and every attempt timed out. With the cache restored, apt fetches only
# packages that changed since it was saved.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/retry.sh"
if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg already present: $(ffmpeg -version | head -1)"
  exit 0
fi
cache="${FFMPEG_DEB_CACHE:?FFMPEG_DEB_CACHE must name the directory apt keeps its packages in}"
# apt refuses an archives directory without partial/.
mkdir -p "$cache/partial" || exit 1
echo "ffmpeg packages already cached: $(ls "$cache" | grep -c '\.deb$')"
APT_OPTS=(
  -o Acquire::Retries=3
  -o Acquire::http::Timeout=20
  -o Acquire::https::Timeout=20
  -o Acquire::ForceIPv4=true
  -o "Dir::Cache::Archives=$cache"
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
# apt ran as root: hand the packages to the runner, which archives them, and
# leave out its lock and partial downloads.
sudo chown -R "$(id -u):$(id -g)" "$cache" || exit 1
rm -rf "$cache/partial" "$cache/lock" || exit 1
ffmpeg -version | head -1
