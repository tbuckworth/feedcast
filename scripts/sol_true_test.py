"""One-off: replay today's writer calls on GPT-5.6 Sol, end to end, and render v2b.

For each episode of the latest run that has a writer bundle, feed Sol exactly
what Opus 4.6 was given (system prompt and user message from
data/sources/<id>.md), then run the pipeline's own fidelity check (Sonnet 5
via OpenRouter), a Sol revision if anything material comes back, the re-check,
and finally the tiered email digest on Sol's own script. The email is then the
one Titus would have received had MODEL_WRITER been Sol that morning, with
one exception: the briefing's story selection (also an Opus call) is baked
into the saved input and is not redone.

    bwsrun uv run python scripts/sol_true_test.py --out DIR [--effort none]
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import email_v2_test as h  # noqa: E402  (rows, durations, bundle_sections, briefing_sources)
from src import digest_variants, verify  # noqa: E402
from src.email_report import build_html, build_text  # noqa: E402
from src.feed import Episode  # noqa: E402
from src.llm import get_client  # noqa: E402
from src.main import _build_run_report, generate_episode_id  # noqa: E402

MODEL = "gpt-5.6-sol"
PRICE_IN, PRICE_OUT = 4.00, 20.00   # USD per 1M, OpenAI direct, 2026-09-16


async def sol(client, system: str, user: str, effort: str, max_out: int, label: str) -> tuple[str, dict]:
    t0 = time.monotonic()
    resp = await client.chat.completions.create(
        model=MODEL, max_completion_tokens=max_out, reasoning_effort=effort,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    text = (resp.choices[0].message.content or "").strip()
    u = resp.usage
    details = getattr(u, "completion_tokens_details", None)
    usage = {
        "call": label, "model": MODEL, "effort": effort,
        "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
        "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
        "cost_usd": round(u.prompt_tokens * PRICE_IN / 1e6 + u.completion_tokens * PRICE_OUT / 1e6, 5),
        "seconds": round(time.monotonic() - t0, 1), "finish": resp.choices[0].finish_reason,
    }
    print(f"    {label}: {usage}")
    if resp.choices[0].finish_reason == "length":
        # A cut-off draft would sail through the check and into the email as
        # if complete; the pipeline's own guard only covers the revision.
        raise RuntimeError(f"{label}: output truncated at {max_out} tokens")
    return text, usage


async def verify_with_sol(script: str, source: str, system: str, sol_client, or_client,
                          effort: str, usage: list, label: str) -> tuple[str, dict]:
    """verify.verify_script, with the revision written by Sol instead of MODEL_WRITER."""
    total, flags = await verify.check(script, source, or_client)
    fid = verify.Fidelity(status="clean", claims_total=total, flags=flags)
    material = fid.material
    print(f"    check ({label}): {total} claims, {len(flags)} flags, {len(material)} material")
    if not material:
        return script, fid.to_dict()
    user = (f"SOURCE:\n{source}\n\nYOUR SCRIPT:\n{script}\n\n"
            f"PROBLEMS FOUND:\n{verify._flags_text(material)}\n\n{verify.REVISE_PROMPT}")
    revised, u = await sol(sol_client, system, user, effort, 16000, f"revise:{label}")
    usage.append(u)
    if len(revised) < 0.6 * len(script):
        fid.status = "flagged"
        fid.note = f"revision rejected: {len(revised)} chars vs {len(script)}"
        return script, fid.to_dict()
    _, after = await verify.check(revised, source, or_client)
    fid.status, fid.revised = "revised", True
    fid.remaining = [f for f in after if f.get("severity") in verify.MATERIAL]
    print(f"    revised ({label}); {len(fid.remaining)} material flags remain")
    return revised, fid.to_dict()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--effort", default="none")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from openai import AsyncOpenAI
    sol_client = AsyncOpenAI(api_key=os.environ["ARROW_OPENAI_API_KEY"], timeout=600, max_retries=2)
    or_client = get_client()

    db = h.rows()
    latest = max(r["processed_at"][:10] for r in db)
    todays = [r for r in db if r["processed_at"][:10] == latest and r["audio_file"]]
    dur = h.durations()
    episodes = [
        Episode(id=r["id"], title=r["title"], description="", audio_file=r["audio_file"],
                published=datetime.fromisoformat(r["published"]),
                duration_seconds=dur.get(r["audio_file"], 0),
                link=r["link"] or None, author=(r.get("author") or "").strip() or r["feed_name"])
        for r in db if r["audio_file"]
    ]
    report = _build_run_report(episodes, db, {r["id"] for r in todays}, [], h.BASE_URL)

    usage: list[dict] = []
    record: dict = {}
    for ep in report.episodes:
        row = next(r for r in todays if ep.audio_url.endswith("/" + r["audio_file"]))
        path = h.ROOT / "data/sources" / f"{generate_episode_id(row['id'])}.md"
        if not path.exists():
            print(f"\n{ep.title}: no writer bundle (verbatim episode) — Opus bullets kept")
            continue
        text = path.read_text(encoding="utf-8")
        secs = h.bundle_sections(path)
        system = secs["System prompt"].strip()
        i, j = text.find("## What the writer was given"), text.find("## What the writer wrote")
        user = text[i + len("## What the writer was given"):j].strip()
        opus_script = secs.get("What the writer wrote", "").strip()
        print(f"\n{ep.title}\n  system {len(system)} chars, user {len(user)} chars")

        draft, u = await sol(sol_client, system, user, args.effort, 16000, f"write:{ep.title[:30]}")
        usage.append(u)
        script, fid = await verify_with_sol(draft, user, system, sol_client, or_client,
                                            args.effort, usage, ep.title[:30])

        is_briefing = ep.is_briefing
        sources = h.briefing_sources(row) if is_briefing else []
        msgs, allowed = digest_variants.build_messages("tiered", script, is_briefing, sources)
        raw, u = await sol(sol_client, msgs[0]["content"], msgs[1]["content"], args.effort, 6000,
                           f"digest:{ep.title[:30]}")
        usage.append(u)
        bullets = digest_variants.parse_tiered(raw, allowed)

        ep.bullets = bullets
        ep.fidelity = fid
        if is_briefing:
            ep.briefing_text = script
        record[row["id"]] = {"title": ep.title, "sol_draft": draft, "sol_script": script,
                             "sol_fidelity": fid, "sol_digest_raw": raw,
                             "opus_script": opus_script,
                             "opus_fidelity": json.loads(row.get("fidelity") or "null")}

    when = datetime.fromisoformat(todays[0]["processed_at"])
    note = ('<p style="font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:12px;'
            'color:#6b6b6b;text-align:center;margin:12px 0 0 0;">Experimental, true Sol test: '
            f'scripts, revisions and bullets all written by GPT-5.6 Sol (reasoning {args.effort}) '
            'from the same source Opus 4.6 saw. Sonnet 5 checker unchanged. Audio links still play '
            'the Opus-written episodes. Sent to Titus only.</p>')
    html = build_html(report, when).replace(
        '<div style="margin:0;padding:0;background:#f4f4f2;">',
        '<div style="margin:0;padding:0;background:#f4f4f2;">' + note, 1)
    (args.out / "email_true_sol.html").write_text(html, encoding="utf-8")
    (args.out / "email_true_sol.txt").write_text(
        f"[TEST] True Sol test: scripts, revisions and bullets all by GPT-5.6 Sol (reasoning {args.effort}). "
        "Sonnet 5 checker unchanged. Audio links still play the Opus episodes.\n\n"
        + build_text(report, when), encoding="utf-8")
    (args.out / "usage_true_sol.json").write_text(json.dumps(usage, indent=2), encoding="utf-8")
    (args.out / "record_true_sol.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    total = sum(u["cost_usd"] for u in usage)
    print(f"\nSol total for the run: ${total:.4f} over {len(usage)} calls")
    print(f"Wrote {args.out}/email_true_sol.html, .txt, usage_true_sol.json, record_true_sol.json")


if __name__ == "__main__":
    asyncio.run(main())
