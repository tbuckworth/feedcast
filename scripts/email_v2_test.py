"""One-off: render the most recent run's email with the full-detail digest.

Rebuilds the report the way `RESEND_REPORT` does, but swaps each episode's
bullets for `src/digest_full.py`'s output, and measures the model calls so the
current and the experimental digest can be costed side by side. Sends nothing:
the HTML, the plain text and a usage JSON land in --out, for the operator to
mail by hand. Reads only the state pulled into data/ (posts.db, sources/) and
output/feed.xml for durations.

    uv run python scripts/email_v2_test.py --out /path/to/dir [--also-model anthropic/claude-sonnet-5]
"""

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import digest, digest_full  # noqa: E402
from src.email_report import build_html, build_text  # noqa: E402
from src.feed import Episode  # noqa: E402
from src.llm import MODEL_WRITER, completion_text, get_client  # noqa: E402
from src.main import _build_run_report, generate_episode_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://tbuckworth.github.io/feedcast"

# USD per 1M tokens, Anthropic list prices (OpenRouter passes them through).
PRICES = {
    "anthropic/claude-opus-4.6": (5.00, 25.00),
    "anthropic/claude-opus-5": (5.00, 25.00),
    "anthropic/claude-sonnet-5": (2.00, 10.00),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
}


def rows() -> list[dict]:
    with sqlite3.connect(ROOT / "data/posts.db") as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM processed_posts ORDER BY published DESC")]


def durations() -> dict[str, int]:
    """audio filename -> seconds, from the published feed (no MP3s locally)."""
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    out = {}
    for item in ET.parse(ROOT / "output/feed.xml").getroot().iter("item"):
        enc = item.find("enclosure")
        dur = item.findtext("itunes:duration", namespaces=ns) or ""
        if enc is None or not dur:
            continue
        parts = [int(p) for p in dur.split(":")]
        secs = 0
        for p in parts:
            secs = secs * 60 + p
        out[enc.get("url").rsplit("/", 1)[-1]] = secs
    return out


def bundle_sections(path: Path) -> dict[str, str]:
    """Split a data/sources bundle on its `## ` headings."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def script_for(row: dict) -> str:
    """The spoken script before normalisation: what the digest is given."""
    if row["id"].startswith("news-briefing-"):
        return row["content"] or ""
    path = ROOT / "data/sources" / f"{generate_episode_id(row['id'])}.md"
    if path.exists():
        wrote = bundle_sections(path).get("What the writer wrote", "")
        if wrote.strip():
            return wrote.strip()
    # Verbatim episodes make no writer call, so there is no bundle: the
    # cleaned post is the script, as in _backfill_bullets.
    from bs4 import BeautifulSoup
    return BeautifulSoup(row["content"] or "", "html.parser").get_text("\n")


_ART = re.compile(r"^- \[(?P<source>[^\]]+)\] (?P<title>.+?)(?:\s+(?P<url>https?://\S+))?$")
_URL = re.compile(r"^\s+URL: (https?://\S+)$")


def briefing_sources(row: dict) -> list[dict]:
    """Rebuild the article list the briefing was written from, from its bundle."""
    path = ROOT / "data/sources" / f"{generate_episode_id(row['id'])}.md"
    if not path.exists():
        return []
    # The article list sits under its own `## CATEGORY` headings inside the
    # "given" section, so slice on the two known markers rather than by heading.
    text = path.read_text(encoding="utf-8")
    start = text.find("## What the writer was given")
    end = text.find("## What the writer wrote")
    given = text[start:end] if 0 <= start < end else ""
    out, pending = [], None
    for line in given.splitlines():
        m = _ART.match(line)
        if m:
            pending = {"title": m["title"].strip(), "source": m["source"], "url": m["url"] or ""}
            if pending["url"]:
                out.append(pending)
                pending = None
            continue
        u = _URL.match(line)
        if u and pending is not None:
            pending["url"] = u.group(1)
            out.append(pending)
            pending = None
    seen, uniq = set(), []
    for s in out:
        if s["url"] not in seen:
            seen.add(s["url"])
            uniq.append(s)
    return uniq


async def measured(client, model: str, messages: list[dict], max_tokens: int) -> tuple[str, dict]:
    t0 = time.monotonic()
    resp = await client.chat.completions.create(
        model=model, max_tokens=max_tokens, messages=messages,
        extra_body={"usage": {"include": True}},
    )
    text = completion_text(resp, model)
    u = resp.usage
    extra = getattr(u, "model_extra", None) or {}
    pin, pout = u.prompt_tokens, u.completion_tokens
    unit_in, unit_out = PRICES.get(model, (0, 0))
    return text, {
        "model": model,
        "prompt_tokens": pin,
        "completion_tokens": pout,
        "openrouter_cost_usd": extra.get("cost"),
        "list_price_usd": round(pin * unit_in / 1e6 + pout * unit_out / 1e6, 5),
        "seconds": round(time.monotonic() - t0, 1),
    }


def current_messages(text: str, is_briefing: bool, sources: list[dict]) -> tuple[list[dict], set[str]]:
    """Exactly what digest.to_bullets sends today."""
    n = "4 to 6" if is_briefing else "3 to 5"
    system = digest.PROMPT.format(n=n)
    allowed = {s["url"] for s in sources if s.get("url")}
    if allowed:
        listing = "\n".join(f"- {s['title']} ({s.get('source', '')}) {s['url']}"
                            for s in sources if s.get("url"))
        system += digest.SOURCES_RULE.format(articles=listing)
    return [{"role": "system", "content": system},
            {"role": "user", "content": text[:digest.MAX_DIGEST_CHARS]}], allowed


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", default=MODEL_WRITER, help="writer for the emailed variant")
    ap.add_argument("--also-model", action="append", default=[],
                    help="extra model(s) to run the full digest on, for cost comparison only")
    ap.add_argument("--skip-current", action="store_true",
                    help="do not re-run today's real digest for token counts")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    db = rows()
    latest = max(r["processed_at"][:10] for r in db)
    todays = [r for r in db if r["processed_at"][:10] == latest and r["audio_file"]]
    print(f"Run of {latest}: {len(todays)} episodes with audio")

    dur = durations()
    episodes = [
        Episode(id=r["id"], title=r["title"], description="", audio_file=r["audio_file"],
                published=datetime.fromisoformat(r["published"]),
                duration_seconds=dur.get(r["audio_file"], 0),
                link=r["link"] or None, author=(r.get("author") or "").strip() or r["feed_name"])
        for r in db if r["audio_file"]
    ]
    report = _build_run_report(episodes, db, {r["id"] for r in todays}, [], BASE_URL)

    client = get_client()
    usage: dict[str, list[dict]] = {"current": [], "full": [], "also": []}
    variants: dict[str, dict] = {}
    for ep in report.episodes:
        row = next(r for r in todays if r["id"] == ep.id)
        is_briefing = ep.is_briefing
        text = script_for(row)
        sources = briefing_sources(row) if is_briefing else []
        print(f"\n{ep.title}\n  script: {len(text)} chars; sources: {len(sources)}")

        if not args.skip_current:
            msgs, allowed = current_messages(text, is_briefing, sources)
            raw, u = await measured(client, MODEL_WRITER, msgs, 1600 if allowed else 1200)
            u["episode"] = ep.title
            u["bullets_kept"] = len(digest.parse_bullets(raw, allowed))
            u["bullets_raw_lines"] = len([l for l in raw.splitlines() if l.strip()])
            usage["current"].append(u)
            variants.setdefault(ep.id, {})["current_raw"] = raw
            print(f"  current digest ({MODEL_WRITER}): {u}")

        msgs, allowed = digest_full.build_messages(text, is_briefing, sources)
        raw, u = await measured(client, args.model, msgs, 6000)
        bullets = digest_full.parse_bullets(raw, allowed, is_briefing)
        u["episode"] = ep.title
        u["bullets_kept"] = len(bullets)
        usage["full"].append(u)
        variants.setdefault(ep.id, {})["full_raw"] = raw
        ep.bullets = bullets
        print(f"  full digest ({args.model}): {u}")

        for m in args.also_model:
            raw2, u2 = await measured(client, m, msgs, 6000)
            u2["episode"] = ep.title
            u2["bullets_kept"] = len(digest_full.parse_bullets(raw2, allowed, is_briefing))
            usage["also"].append(u2)
            variants[ep.id][f"full_raw::{m}"] = raw2
            print(f"  full digest ({m}): {u2}")

    when = datetime.fromisoformat(todays[0]["processed_at"])
    note = ('<p style="font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:12px;'
            'color:#6b6b6b;text-align:center;margin:12px 0 0 0;">Experimental variant: '
            'bullets restate the audio rather than condensing it. Sent to Titus only.</p>')
    html = build_html(report, when)
    html = html.replace('<div style="margin:0;padding:0;background:#f4f4f2;">',
                        '<div style="margin:0;padding:0;background:#f4f4f2;">' + note, 1)
    (args.out / "email_v2.html").write_text(html, encoding="utf-8")
    (args.out / "email_v2.txt").write_text(
        "[TEST] Experimental variant: bullets restate the audio rather than condensing it.\n\n"
        + build_text(report, when), encoding="utf-8")
    (args.out / "usage.json").write_text(json.dumps(usage, indent=2), encoding="utf-8")
    (args.out / "raw_outputs.json").write_text(json.dumps(variants, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out}/email_v2.html, email_v2.txt, usage.json, raw_outputs.json")


if __name__ == "__main__":
    asyncio.run(main())
