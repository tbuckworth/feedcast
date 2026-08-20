#!/usr/bin/env python3
"""Compare model setups on the two things Feedcast actually produces.

Runs every setup over the same two sources — a real daily news briefing and a
genuinely maths-heavy LessWrong post — records real token usage and cost from
OpenRouter, and writes results to a JSON file for the HTML report.

    OPENROUTER_API_KEY=... uv run python scripts/model_comparison.py

Fairness rules, so the comparison means something:
  - every setup sees byte-identical source text
  - every setup is given the same output target (length, register, audience)
  - max_tokens is generous everywhere, so nothing is truncated
  - cost comes from each response's own usage, not an estimate

The maths post is fetched as MARKDOWN via LessWrong's GraphQL API. The RSS feed
the pipeline currently reads has MathJax stripped out entirely, so formulas
arrive as holes ("a function f is anytime computable if ___ where ___ is
finitely computable"). No model can explain maths it was never shown, so
comparing models on the RSS text would measure nothing.
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processor import ContentProcessor  # noqa: E402

OUT = Path(__file__).parent.parent / "data" / "model_comparison.json"
UA = {"User-Agent": "Mozilla/5.0 (feedcast research)"}

# $ per 1M tokens (in, out) — OpenRouter list prices.
PRICING = {
    "google/gemini-3-flash-preview": (0.50, 3.00),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "anthropic/claude-sonnet-5": (2.00, 10.00),
    "anthropic/claude-opus-4.6": (5.00, 25.00),
    "anthropic/claude-opus-5": (5.00, 25.00),
    "anthropic/claude-fable-5": (10.00, 50.00),
}

# (key, label, [stage models]) — one model = single pass, two = comprehend then write.
SETUPS = [
    ("baseline", "Gemini 3 Flash", ["google/gemini-3-flash-preview"]),
    ("opus46", "Opus 4.6", ["anthropic/claude-opus-4.6"]),
    ("opus5", "Opus 5", ["anthropic/claude-opus-5"]),
    ("opus5_opus46", "Opus 5 → Opus 4.6",
     ["anthropic/claude-opus-5", "anthropic/claude-opus-4.6"]),
    ("sonnet5_opus46", "Sonnet 5 → Opus 4.6",
     ["anthropic/claude-sonnet-5", "anthropic/claude-opus-4.6"]),
]

# Not run — estimated from the measured token counts of the closest setup.
FABLE = "anthropic/claude-fable-5"

# --- prompts -----------------------------------------------------------------
# The audio rule is the same everywhere so no setup gets a stylistic advantage.
AUDIO_RULES = """\
This will be read aloud by a text-to-speech voice to one listener on headphones.

- Natural spoken English only. No bullet points, headings, markdown or lists.
- Never speak notation. Do not say "backslash", "dollar sign", "subscript",
  "open paren", or read a formula symbol by symbol.
- Where the source contains mathematics, say what it MEANS at the level a
  colleague would explain it on a walk: what quantity is being described, what
  the relationship is, and why it matters. High-level intuition over low-level
  detail. If an equation defines a condition, state the condition in words.
- Write numbers, dates and percentages as spoken words ("forty-five percent").
- Do not open with a greeting or close with a sign-off."""

POST_TARGET = """\
Produce roughly 400 to 450 words — about three minutes spoken.
The listener is a PhD-level AI safety researcher: keep technical terminology
and nuance, skip background explanation they already have."""

SINGLE_POST = f"""You are writing an audio summary of a technical blog post.

Read the post carefully, work out what it actually argues, and explain it.

{AUDIO_RULES}

{POST_TARGET}

Output only the script."""

COMPREHEND_POST = """You are the analysis stage of a two-stage pipeline. You will NOT be heard.

Read this technical blog post and produce a dense written brief for the writer
who comes after you. They will not see the original, so anything you omit is
lost. Include:

1. The central claim, stated precisely.
2. The argument structure — what is actually being shown, and how.
3. Every piece of mathematics, TRANSLATED INTO PLAIN LANGUAGE: what each
   quantity is, what each expression asserts, and what the result means.
   Do not reproduce notation; explain it.
4. What is genuinely novel or surprising here.
5. Caveats, limitations or hedges the author states.

Be thorough and specific. Prose or terse notes, no length limit."""

WRITE_POST = f"""You are the writing stage of a two-stage pipeline. An analyst has read a
technical blog post and written you the brief below. Turn it into an audio script.

You did not see the original post — work only from the brief, and trust it.

{AUDIO_RULES}

{POST_TARGET}

Output only the script."""

BRIEF_TARGET = """\
Produce roughly 600 to 700 words — about five minutes spoken.
Cover only the four or five most significant stories. Ruthlessly drop the rest;
a short sharp briefing beats a comprehensive one.
Order: AI safety and policy, then AI capabilities, then geopolitics, then
economics and markets. Attribute major claims to their source."""

SINGLE_BRIEF = f"""You are a news anchor delivering a daily briefing to a technically
sophisticated audience.

Synthesize the articles below into one coherent briefing.
Open with "Here is your daily news briefing for {{date}}."

{AUDIO_RULES}

{BRIEF_TARGET}

Output only the script."""

COMPREHEND_BRIEF = """You are the analysis stage of a two-stage pipeline. You will NOT be heard.

Read today's articles below and produce a dense written brief for the writer who
comes after you. They will not see the articles, so anything you omit is lost.

1. Identify the four or five genuinely significant stories. Say why each matters.
2. For each: the core facts, the source, the context a reader needs, and the
   implication. Merge articles covering the same story.
3. Flag anything that looks like duplicate coverage, hype, or a non-story.
4. Note any connections between stories worth drawing out.

Be thorough and specific. Prose or terse notes, no length limit."""

WRITE_BRIEF = f"""You are the writing stage of a two-stage pipeline. An analyst has read today's
news and written you the brief below. Turn it into an audio script.

You did not see the articles — work only from the brief, and trust it.
Open with "Here is your daily news briefing for {{date}}."

{AUDIO_RULES}

{BRIEF_TARGET}

Output only the script."""


# --- sources -----------------------------------------------------------------
def fetch_maths_post() -> dict:
    """Fetch a maths-heavy LessWrong post as markdown, so the LaTeX survives."""
    post_id = "MgYCraoxMwfWwgWa5"
    q = {"query": '{post(input:{selector:{_id:"%s"}}){result{title pageUrl '
                  'contents{markdown}}}}' % post_id}
    d = httpx.post("https://www.lesswrong.com/graphql", json=q, timeout=90,
                   headers=UA).json()
    r = d["data"]["post"]["result"]
    md = r["contents"]["markdown"]
    tex = len(re.findall(r"\$[^$\n]{2,80}\$", md))
    print(f"  maths post: {r['title']!r} — {len(md)} chars, {tex} LaTeX expressions")
    return {"title": r["title"], "url": r["pageUrl"], "text": md, "latex_count": tex}


def fetch_news() -> dict:
    """Fetch today's real news articles, exactly as the pipeline would."""
    cfg = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml"))
    nb = cfg["news_briefing"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=nb["lookback_hours"])
    arts = []
    for s in nb["sources"]:
        try:
            f = feedparser.parse(s["url"])
        except Exception:
            continue
        for e in f.entries:
            pp = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
            if not pp:
                continue
            when = datetime(*pp[:6], tzinfo=timezone.utc)
            if when < cutoff:
                continue
            arts.append({"title": e.get("title", "Untitled"), "source": s["name"],
                         "category": s["category"],
                         "summary": (e.get("summary") or e.get("description") or "")[:500]})
    by_cat: dict[str, list] = {}
    for a in arts:
        by_cat.setdefault(a["category"], []).append(a)
    blocks = []
    for cat, items in sorted(by_cat.items()):
        lines = [f"## {cat.upper().replace('_', ' ')}"]
        lines += [f"- [{i['source']}] {i['title']}\n  {i['summary']}" for i in items]
        blocks.append("\n".join(lines))
    text = "\n\n".join(blocks)
    print(f"  news: {len(arts)} articles across {len(by_cat)} categories, {len(text)} chars")
    return {"title": "Daily News Briefing", "url": "", "text": text,
            "article_count": len(arts)}


# --- runner ------------------------------------------------------------------
def cost_of(model: str, usage: dict) -> float:
    pin, pout = PRICING.get(model, (0.0, 0.0))
    return usage["in"] / 1e6 * pin + usage["out"] / 1e6 * pout


async def call(client: httpx.AsyncClient, model: str, system: str, user: str) -> dict:
    """One OpenRouter chat completion. Returns text + real usage."""
    t0 = time.monotonic()
    r = await client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        json={"model": model, "max_tokens": 16000,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
    )
    r.raise_for_status()
    d = r.json()
    if "choices" not in d:
        raise RuntimeError(f"{model}: {json.dumps(d)[:300]}")
    u = d.get("usage") or {}
    return {
        "text": d["choices"][0]["message"]["content"] or "",
        "usage": {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)},
        "seconds": round(time.monotonic() - t0, 1),
    }


async def run_setup(client, setup, artefact, prompts) -> dict:
    """Run one setup over one artefact. One model = single pass, two = staged."""
    key, label, models = setup
    single, comprehend, write = prompts
    stages, total = [], {"in": 0, "out": 0}

    try:
        if len(models) == 1:
            res = await call(client, models[0], single, artefact["text"])
            stages.append({"role": "single-pass", "model": models[0], **res})
            final = res["text"]
        else:
            a = await call(client, models[0], comprehend, artefact["text"])
            stages.append({"role": "comprehend", "model": models[0], **a})
            b = await call(client, models[1], write, a["text"])
            stages.append({"role": "write", "model": models[1], **b})
            final = b["text"]
    except Exception as e:
        print(f"    {label:22s} FAILED: {type(e).__name__}: {str(e)[:120]}")
        return {"key": key, "label": label, "models": models, "error":
                f"{type(e).__name__}: {e}", "stages": stages}

    cost = 0.0
    for s in stages:
        total["in"] += s["usage"]["in"]
        total["out"] += s["usage"]["out"]
        s["cost"] = round(cost_of(s["model"], s["usage"]), 6)
        cost += s["cost"]

    words = len(final.split())
    print(f"    {label:22s} {words:4d} words  {total['in']:6d}in/{total['out']:5d}out  "
          f"${cost:.4f}  {sum(s['seconds'] for s in stages):.0f}s")
    return {"key": key, "label": label, "models": models, "output": final,
            "words": words, "usage": total, "cost": round(cost, 6),
            "seconds": sum(s["seconds"] for s in stages),
            "stages": [{k: v for k, v in s.items() if k != "text"} |
                       {"text": s["text"]} for s in stages]}


async def main() -> int:
    # Allow a local .env (gitignored) so the key never has to be pasted into a shell
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY must be set")
        return 1

    print("Fetching sources...")
    maths = fetch_maths_post()
    news = fetch_news()
    today = datetime.now().strftime("%A, %-d %B %Y")

    artefacts = [
        ("maths_post", maths,
         (SINGLE_POST, COMPREHEND_POST, WRITE_POST)),
        ("news_briefing", news,
         (SINGLE_BRIEF.replace("{date}", today),
          COMPREHEND_BRIEF,
          WRITE_BRIEF.replace("{date}", today))),
    ]

    results = {"generated_at": datetime.now().isoformat(), "artefacts": {}}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(600.0),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json",
                 "X-Title": "feedcast-model-comparison"},
    ) as client:
        for name, artefact, prompts in artefacts:
            print(f"\n=== {name} ({len(artefact['text'])} chars in) ===")
            runs = await asyncio.gather(
                *[run_setup(client, s, artefact, prompts) for s in SETUPS]
            )
            results["artefacts"][name] = {
                "meta": {k: v for k, v in artefact.items() if k != "text"},
                "source_chars": len(artefact["text"]),
                "source_text": artefact["text"],
                "runs": list(runs),
            }

    # Fable estimate: same token counts as the most similar setup we did run.
    for name, block in results["artefacts"].items():
        ref = next((r for r in block["runs"]
                    if r["key"] == "opus5" and "usage" in r), None)
        if ref:
            block["fable_estimate"] = {
                "basis": "opus5 single-pass token counts",
                "usage": ref["usage"],
                "cost": round(cost_of(FABLE, ref["usage"]), 6),
            }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
