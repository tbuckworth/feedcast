#!/usr/bin/env bash
# Copy the MP3s restored from the state branch (data/audio/) into the Pages
# site (output/audio/), and fail if output/feed.xml lists an enclosure that is
# not among them. Run from the repository root, after `scripts/state.sh pull`.
#
# ci-commit-and-push.sh pushes the state branch before main, so the audio for
# any feed.xml on main is already on the state branch: a missing file is a
# real fault, and publishing would ship enclosures that 404.

set -euo pipefail

mkdir -p output/audio
shopt -s nullglob
mp3s=(data/audio/*.mp3)
if (( ${#mp3s[@]} )); then cp "${mp3s[@]}" output/audio/; fi
echo "Copied ${#mp3s[@]} MP3s"

python3 - <<'PY'
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

listed = [Path(unquote(urlparse(e.get("url", "")).path)).name
          for e in ET.parse("output/feed.xml").iter("enclosure")]
missing = [name for name in listed if not (Path("output/audio") / name).is_file()]
for name in missing:
    print(f"::error::feed.xml lists audio/{name}, which is not on the state branch")
print(f"feed.xml lists {len(listed)} enclosures; {len(missing)} missing")
sys.exit(1 if missing else 0)
PY
