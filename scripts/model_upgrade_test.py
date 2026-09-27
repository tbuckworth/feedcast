"""One-off: replay a saved briefing through two model setups and meter every call.

Takes the writer bundle of one episode (data/sources/<id>.md: the exact system
prompt and user message the writer saw), then for each setup runs what the
pipeline runs after story selection: write, fidelity check, one revision if
anything material comes back, re-check, and the email digest. The setups swap
`llm.ROLES` wholesale, so every call goes through the pipeline's own code.

    bwsrun bash -c 'export OPENROUTER_API_KEY="$ARROW_OPENROUTER_API_KEY" \
        OPENAI_API_KEY="$ARROW_OPENAI_API_KEY"; \
        uv run python -m scripts.model_upgrade_test data/sources/<id>.md --out DIR'

`--system-file` replaces the bundle's system prompt (to test a prompt change
on the same input); `--setups` picks which setups to run.
"""

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

from src import digest, llm, verify
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
    "google/gemini-3-flash-preview": (0.5, 3.0),
}

# Anthropic direct, not OpenRouter: since 2026-09-22 OpenRouter has refused
# every Claude request with 403 "violation of provider Terms Of Service", so
# production's writer and checker are served by their Anthropic-direct
# backups. Primaries only here, so a fallback cannot muddy the meter.
SETUPS = {
    "current": {
        "writer": (Target("anthropic", "claude-opus-4-6"),),
        "checker": (Target("anthropic", "claude-sonnet-5"),),
        "bullets": (Target("openai", "gpt-5.6-sol", {"off": True}),),
    },
    # Opus 5.5 as writer and digest. Its thinking cannot be switched off and
    # the anthropic route sends no reasoning setting, so it runs at the
    # model's default effort (medium); thinking is billed as output.
    "proposed": {
        "writer": (Target("anthropic", "claude-opus-5-5"),),
        "checker": (Target("anthropic", "claude-sonnet-5"),),
        "bullets": (Target("anthropic", "claude-opus-5-5"),),
    },
}

calls: list[dict] = []
_orig_completion = llm._completion


def _metered(response, target, where):
    done = _orig_completion(response, target, where)
    u = response.usage
    extra = getattr(u, "model_extra", None) or {}
    details = getattr(u, "completion_tokens_details", None)
    pin, pout = PRICES.get(target.model, (0, 0))
    listed = u.prompt_tokens * pin / 1e6 + u.completion_tokens * pout / 1e6
    calls.append({
        "call": where, "model": target.label,
        "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
        "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
        "billed_usd": extra.get("cost"), "list_usd": round(listed, 5),
        "chars_out": len(done.text or ""),
    })
    print(f"    [{where}] {target.label}: in={u.prompt_tokens} out={u.completion_tokens} "
          f"cost={extra.get('cost', round(listed, 5))}")
    return done


llm._completion = _metered


BUNDLE_HEADS = ("System prompt", "What the writer was given", "What the writer wrote",
                "Fidelity check")


def sections(text: str) -> dict[str, str]:
    """The bundle's own sections. The user message has ## headings of its own."""
    marks = [(m.start(), m.end(), m.group(1)) for m in re.finditer(r"^## (.+)$", text, re.M)
             if m.group(1).strip() in BUNDLE_HEADS]
    return {name.strip(): text[end:(marks[i + 1][0] if i + 1 < len(marks) else len(text))].strip()
            for i, (_, end, name) in enumerate(marks)}


def selected_sources(user: str) -> list[dict]:
    """The briefing's selected stories, as digest link targets."""
    block = user.split("## Selected stories", 1)[-1].split("## Other headlines", 1)[0]
    return [{"source": m[0], "title": m[1].strip(), "url": m[2].strip()}
            for m in re.findall(r"^- \[([^\]]+)\] (.+)\n\s+URL: (\S+)", block, re.M)]


async def run(setup: str, system: str, user: str, is_briefing: bool, sources: list[dict]) -> dict:
    llm.ROLES.update(SETUPS[setup])
    start = len(calls)
    t0 = time.monotonic()
    draft = (await llm.complete("writer", max_tokens=16000, label="write", messages=[
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


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--setups", default="current,proposed")
    ap.add_argument("--system-file", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    secs = sections(args.bundle.read_text(encoding="utf-8"))
    system = args.system_file.read_text() if args.system_file else secs["System prompt"]
    user = secs["What the writer was given"]
    is_briefing = "## Today's articles:" in user
    sources = selected_sources(user) if is_briefing else []
    print(f"{args.bundle.name}: system {len(system)} chars, user {len(user)} chars, "
          f"{len(sources)} link targets")

    for setup in args.setups.split(","):
        print(f"\n== {setup}")
        result = await run(setup, system, user, is_briefing, sources)
        result["production"] = secs.get("What the writer wrote", "")
        (args.out / f"{setup}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"  {setup}: ${result['cost_usd']} over {len(result['calls'])} calls, "
              f"{result['seconds']}s, 'matters because' x"
              f"{result['script'].lower().count('matters because')}")


if __name__ == "__main__":
    asyncio.run(main())
