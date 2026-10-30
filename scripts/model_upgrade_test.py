"""Replay a saved writer bundle through model setups and meter every call.

The side-by-side for a model change, run before `llm.ROLES` changes: it
compares the current roles with candidate setups on the same input. Takes the
writer bundle of one episode (data/sources/<id>.md, `src/bundle.py`: the exact
system prompt and user message the writer saw), then for each setup runs what
the pipeline runs after story selection: write, fidelity check, one revision if
anything material comes back, re-check, and the email digest. A setup swaps
`llm.ROLES` wholesale, so every call goes through the pipeline's own code,
efforts and the native Anthropic path included. `current` is the primary of
each role in `llm.ROLES`; a candidate setup names only the roles it changes.

    bwsrun bash -c 'export OPENROUTER_API_KEY="$ARROW_OPENROUTER_API_KEY" \
        OPENAI_API_KEY="$ARROW_OPENAI_API_KEY" ANTHROPIC_API_KEY="$ARROW_ANTHROPIC_API_KEY"; \
        uv run python -m scripts.model_upgrade_test data/sources/<id>.md --out DIR'

`--system-file` replaces the bundle's system prompt, and `--current-prompts`
swaps in today's briefing prompt and previous-briefings header, to test a
prompt change on the same input; `--setups` picks which setups to run. DIR
gets run.json (the arguments, the system prompt and user message sent, and
each setup's targets) and one <setup>.json of results per setup. The meter
reads each call's `Completion.usage`, so it counts the reply that served the
call, not one a fallback replaced.
"""

import argparse
import asyncio
import json
import re
import time
from dataclasses import asdict
from pathlib import Path

from src import bundle, digest, llm, news, verify
from src.config import load_config
from src.llm import Target

# USD per 1M tokens (input, output). OpenRouter's own billed cost is used
# when the response carries it; these are the fallback and the model for
# the monthly estimate. Sol direct: OpenAI list price, 2026-09-16.
PRICES = {
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5": (2.0, 10.0),
    "anthropic/claude-opus-4.6": (5.0, 25.0),
    "anthropic/claude-opus-5.5": (4.0, 20.0),
    "anthropic/claude-sonnet-5": (2.0, 10.0),
    "gpt-5.6-sol": (4.0, 20.0),
    "gpt-6.1-sol": (2.0, 10.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "anthropic/claude-sonnet-5.5": (2.0, 10.0),
    "openai/gpt-6.1-sol": (2.0, 10.0),
    "google/gemini-3-flash-preview": (0.5, 3.0),
}

# Production's primaries only, so a fallback cannot muddy the meter.
CURRENT = {role: targets[:1] for role, targets in llm.ROLES.items()}

SETUPS = {
    # Whatever src/llm.py ships, fallbacks included.
    "main": dict(llm.ROLES),
    "current": CURRENT,
    # Opus 5.5 writes the digest as well, at its default effort (medium): a
    # target with no effort goes over Anthropic's OpenAI-compatible endpoint.
    "proposed": {**CURRENT,
                 "writer": (Target("anthropic", "claude-opus-5-5"),),
                 "bullets": (Target("anthropic", "claude-opus-5-5"),)},
    # The same at low effort, which llm sends over the native Messages API.
    "proposed-low": {**CURRENT,
                     "writer": (Target("anthropic", "claude-opus-5-5", {"effort": "low"}),),
                     "bullets": (Target("anthropic", "claude-opus-5-5", {"effort": "low"}),)},
}

calls: list[dict] = []


async def metered(role: str, messages: list[dict], **kw) -> llm.Completion:
    """`llm.complete`, recording the tokens and cost of the reply that served it.

    Raises KeyError for a reply with no billed cost from a model missing from
    PRICES: costing it at $0 would understate the setup it ran in."""
    done = await llm.complete(role, messages, **kw)
    where, target, u = kw.get("label") or role, done.target, done.usage
    extra = getattr(u, "model_extra", None) or {}
    details = getattr(u, "completion_tokens_details", None)
    billed, price = extra.get("cost"), PRICES.get(target.model)
    if billed is None and price is None:
        raise KeyError(f"{where}: {target.label} billed no cost and {target.model} "
                       "has no list price; add it to PRICES")
    listed = (round(u.prompt_tokens * price[0] / 1e6 + u.completion_tokens * price[1] / 1e6, 5)
              if price else None)
    calls.append({
        "call": where, "model": target.label,
        "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
        "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
        "billed_usd": billed, "list_usd": listed,
        "chars_out": len(done.text or ""),
    })
    print(f"    [{where}] {target.label}: in={u.prompt_tokens} out={u.completion_tokens} "
          f"cost={billed if billed is not None else listed}")
    return done


# verify and digest import `complete` by name; theirs is the metered one too.
verify.complete = digest.complete = metered


def selected_sources(user: str) -> list[dict]:
    """The briefing's selected stories, as digest link targets."""
    block = user.split(news.SELECTED_STORIES_HEADING, 1)[-1]
    block = block.split(news.OTHER_HEADLINES_HEADING, 1)[0]
    return [{"source": m[0], "title": m[1].strip(), "url": m[2].strip()}
            for m in re.findall(r"^- \[([^\]]+)\] (.+)\n\s+URL: (\S+)", block, re.M)]


async def run(setup: str, system: str, user: str, is_briefing: bool, sources: list[dict]) -> dict:
    llm.ROLES.update(SETUPS[setup])
    start = len(calls)
    t0 = time.monotonic()
    draft = (await metered("writer", max_tokens=16000, label="write", messages=[
        {"role": "system", "content": system}, {"role": "user", "content": user}])).text
    script, fid = await verify.verify_script(draft, user, writer_system_prompt=system, label=setup)
    bullets = await digest.to_bullets(script, is_briefing, sources=sources, label=setup)
    mine = calls[start:]
    return {
        "setup": setup, "draft": draft, "script": script, "fidelity": fid.to_dict(),
        "bullets": bullets, "calls": mine, "seconds": round(time.monotonic() - t0),
        "cost_usd": round(sum(c["billed_usd"] if c["billed_usd"] is not None else c["list_usd"]
                              for c in mine), 4),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--setups", default="current,proposed",
                    help=f"comma-separated, from: {', '.join(SETUPS)}")
    ap.add_argument("--system-file", type=Path)
    ap.add_argument("--current-prompts", action="store_true",
                    help="briefing: today's config.yaml prompt and previous-briefings header")
    args = ap.parse_args(argv)
    args.setups = args.setups.split(",")
    unknown = [s for s in args.setups if s not in SETUPS]
    if unknown:
        ap.error(f"unknown setup(s) {', '.join(unknown)}; choose from {', '.join(SETUPS)}")
    return args


async def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    secs = bundle.read_bundle(args.bundle.read_text(encoding="utf-8"))
    system = args.system_file.read_text() if args.system_file else secs[bundle.SYSTEM_PROMPT]
    user = secs[bundle.WRITER_INPUT]
    is_briefing = news.ARTICLES_HEADING in user
    if args.current_prompts and is_briefing:
        if not args.system_file:
            system = load_config().news_briefing.prompt
        user = re.sub(r"^## Previous briefings.*$", lambda _: news.PREVIOUS_BRIEFINGS_HEADER, user,
                      count=1, flags=re.M)
    sources = selected_sources(user) if is_briefing else []
    print(f"{args.bundle.name}: system {len(system)} chars, user {len(user)} chars, "
          f"{len(sources)} link targets")

    # What the run was given, so its results can be traced and repeated.
    (args.out / "run.json").write_text(json.dumps({
        "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "system": system, "user": user,
        "setups": {name: {role: [asdict(t) for t in targets]
                          for role, targets in SETUPS[name].items()}
                   for name in args.setups},
    }, indent=2), encoding="utf-8")

    for setup in args.setups:
        print(f"\n== {setup}")
        result = await run(setup, system, user, is_briefing, sources)
        result["production"] = secs.get(bundle.WRITER_OUTPUT, "")
        (args.out / f"{setup}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"  {setup}: ${result['cost_usd']} over {len(result['calls'])} calls, "
              f"{result['seconds']}s, 'matters because' x"
              f"{result['script'].lower().count('matters because')}")


if __name__ == "__main__":
    asyncio.run(main())
