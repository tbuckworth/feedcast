#!/usr/bin/env python3
"""Render the model-comparison JSON into a single self-contained HTML page.

    uv run python scripts/build_comparison_report.py [--mock]

--mock renders the page from synthetic data so the layout can be checked
without spending anything on model calls.
"""

import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data" / "model_comparison.json"
OUT = ROOT / "output" / "model_comparison.html"

FABLE_PRICE = (10.00, 50.00)


def money(x: float) -> str:
    return f"${x:.4f}" if x < 1 else f"${x:.2f}"


def per_month(cost_per_run: float, runs_per_month: int) -> float:
    return cost_per_run * runs_per_month


def card(run: dict, artefact_key: str) -> str:
    """One setup's output for one artefact."""
    if run.get("error"):
        return f"""
        <article class="out err" data-setup="{escape(run['key'])}">
          <header><h3>{escape(run['label'])}</h3><span class="pill bad">failed</span></header>
          <p class="mono small">{escape(run['error'])}</p>
        </article>"""

    stages = run.get("stages") or []
    brief = ""
    if len(stages) > 1:
        analysis = stages[0].get("text", "")
        brief = f"""
          <details class="brief">
            <summary>Analyst brief from {escape(stages[0]['model'].split('/')[-1])}
              &middot; {len(analysis.split())} words &middot; not heard by you</summary>
            <div class="brief-body">{"".join(
                f"<p>{escape(p.strip())}</p>" for p in analysis.split(chr(10)) if p.strip())}</div>
          </details>"""

    body = "".join(f"<p>{escape(p.strip())}</p>"
                   for p in run.get("output", "").split("\n") if p.strip())
    chain = " → ".join(escape(m.split("/")[-1]) for m in run["models"])

    return f"""
        <article class="out" data-setup="{escape(run['key'])}">
          <header>
            <h3>{escape(run['label'])}</h3>
            <span class="pill">{money(run['cost'])}</span>
          </header>
          <div class="meta mono small">{chain}<br>
            {run['words']} words &middot; {run['usage']['in']:,} in / {run['usage']['out']:,} out
            &middot; {run['seconds']:.0f}s</div>
          {brief}
          <div class="script">{body}</div>
        </article>"""


def cost_table(results: dict) -> str:
    """One row per setup: per-run cost for each artefact, then a monthly projection."""
    # Measured 30-day volume: 1 briefing/day, ~2.3 summarised posts/day.
    BRIEFINGS, POSTS = 30, 61
    rows, keys = [], []
    for name in ("news_briefing", "maths_post"):
        for r in results["artefacts"].get(name, {}).get("runs", []):
            if r["key"] not in keys:
                keys.append(r["key"])

    for k in keys:
        nb = next((r for r in results["artefacts"].get("news_briefing", {}).get("runs", [])
                   if r["key"] == k), None)
        mp = next((r for r in results["artefacts"].get("maths_post", {}).get("runs", [])
                   if r["key"] == k), None)
        if not nb or not mp or nb.get("error") or mp.get("error"):
            continue
        monthly = per_month(nb["cost"], BRIEFINGS) + per_month(mp["cost"], POSTS)
        cls = ' class="pick"' if k == "opus5_opus46" else ""
        rows.append(f"""
        <tr{cls}><td>{escape(nb['label'])}</td>
          <td class="num">{money(nb['cost'])}</td>
          <td class="num">{money(mp['cost'])}</td>
          <td class="num strong">${monthly:,.2f}</td></tr>""")

    # Fable projection from the Opus 5 single-pass token counts.
    fest = []
    for name, n in (("news_briefing", BRIEFINGS), ("maths_post", POSTS)):
        f = results["artefacts"].get(name, {}).get("fable_estimate")
        if f:
            fest.append((f["cost"], n))
    if len(fest) == 2:
        fm = sum(c * n for c, n in fest)
        rows.append(f"""
        <tr class="est"><td>Fable 5 <span class="tag">estimated</span></td>
          <td class="num">{money(fest[0][0])}</td>
          <td class="num">{money(fest[1][0])}</td>
          <td class="num strong">${fm:,.2f}</td></tr>""")

    return f"""
    <div class="scroll"><table>
      <thead><tr><th>Setup</th><th class="num">Per briefing</th>
        <th class="num">Per post</th><th class="num">Per month</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    <p class="small muted">Monthly assumes the measured cadence: {BRIEFINGS} briefings and
    {POSTS} summarised posts per 30 days. Only summarised posts incur this cost —
    verbatim episodes skip the model entirely. Excludes TTS (~$1.30/mo) and the
    TTS-normalisation pass, which is unchanged across every setup.</p>"""


def section(results: dict, key: str, title: str, blurb: str) -> str:
    block = results["artefacts"].get(key)
    if not block:
        return ""
    meta = block.get("meta", {})
    src = block.get("source_text", "")
    src_note = ""
    if meta.get("latex_count"):
        src_note = (f"{meta['latex_count']} LaTeX expressions &middot; "
                    f"{block['source_chars']:,} chars")
    elif meta.get("article_count"):
        src_note = (f"{meta['article_count']} articles &middot; "
                    f"{block['source_chars']:,} chars")

    link = (f' &middot; <a href="{escape(meta["url"], quote=True)}">source</a>'
            if meta.get("url") else "")

    return f"""
  <section id="{escape(key)}">
    <div class="head">
      <div class="eyebrow">{escape(src_note)}{link}</div>
      <h2>{escape(title)}</h2>
      <p class="lede">{blurb}</p>
    </div>
    <details class="source">
      <summary>The input every setup was given (identical bytes)</summary>
      <pre>{escape(src[:6000])}{'…' if len(src) > 6000 else ''}</pre>
    </details>
    <div class="grid">{''.join(card(r, key) for r in block['runs'])}</div>
  </section>"""


def build(results: dict) -> str:
    when = results.get("generated_at", "")[:16].replace("T", " ")
    return f"""<title>Feedcast Model Bake-Off</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=Inter+Tight:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
  :root {{
    --ground:#F4F3F0; --surface:#FFF; --surface-2:#ECEAE5; --ink:#1B1A17;
    --ink-soft:#403E39; --muted:#6E6A62; --rule:#DEDBD4;
    --accent:#7A3E1D; --accent-soft:#F3E7DE; --good:#2F6B4F; --bad:#9B3232;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --ground:#131211; --surface:#1B1A18; --surface-2:#232120; --ink:#EDEAE4;
      --ink-soft:#C6C1B8; --muted:#8D8880; --rule:#302D2A;
      --accent:#D98E5F; --accent-soft:#2B211A; --good:#6FBF95; --bad:#E08585;
    }}
  }}
  :root[data-theme="dark"] {{
    --ground:#131211; --surface:#1B1A18; --surface-2:#232120; --ink:#EDEAE4;
    --ink-soft:#C6C1B8; --muted:#8D8880; --rule:#302D2A;
    --accent:#D98E5F; --accent-soft:#2B211A; --good:#6FBF95; --bad:#E08585;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--ground);color:var(--ink);
    font-family:"Inter Tight",system-ui,sans-serif;font-size:15.5px;line-height:1.6}}
  .wrap{{max-width:1500px;margin:0 auto;padding:48px 24px 90px}}
  h1,h2{{font-family:Newsreader,Georgia,serif;margin:0;text-wrap:balance;font-weight:600}}
  h1{{font-size:clamp(2rem,4.4vw,2.9rem);letter-spacing:-.02em;line-height:1.1}}
  h2{{font-size:clamp(1.35rem,2.6vw,1.8rem);letter-spacing:-.01em}}
  h3{{font-family:"Inter Tight",sans-serif;font-size:1rem;font-weight:600;margin:0}}
  p{{margin:0}}
  .eyebrow{{font-family:"JetBrains Mono",monospace;font-size:.68rem;letter-spacing:.11em;
    text-transform:uppercase;color:var(--accent)}}
  .lede{{color:var(--ink-soft);max-width:72ch}}
  .muted{{color:var(--muted)}} .small{{font-size:.8rem}}
  .mono{{font-family:"JetBrains Mono",monospace}}
  a{{color:var(--accent)}}
  header.top{{border-bottom:2px solid var(--ink);padding-bottom:26px;
    display:flex;flex-direction:column;gap:12px}}
  section{{padding:52px 0 0;display:flex;flex-direction:column;gap:18px}}
  .head{{display:flex;flex-direction:column;gap:7px}}

  .scroll{{overflow-x:auto;border:1px solid var(--rule);border-radius:9px;background:var(--surface)}}
  table{{border-collapse:collapse;width:100%;font-size:.9rem}}
  th,td{{text-align:left;padding:11px 15px;border-bottom:1px solid var(--rule);white-space:nowrap}}
  th{{font-family:"JetBrains Mono",monospace;font-size:.66rem;letter-spacing:.09em;
    text-transform:uppercase;color:var(--muted);font-weight:500;background:var(--surface-2)}}
  tbody tr:last-child td{{border-bottom:0}}
  .num{{text-align:right;font-variant-numeric:tabular-nums;font-family:"JetBrains Mono",monospace}}
  .strong{{font-weight:600}}
  tr.pick td{{background:var(--accent-soft)}}
  tr.pick td:first-child{{box-shadow:inset 3px 0 0 var(--accent);font-weight:600}}
  tr.est td{{color:var(--muted);font-style:italic}}
  .tag{{font-family:"JetBrains Mono",monospace;font-size:.62rem;letter-spacing:.06em;
    text-transform:uppercase;border:1px solid var(--rule);padding:1px 5px;border-radius:3px;
    margin-left:6px;font-style:normal}}

  .grid{{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));
    align-items:start}}
  .out{{background:var(--surface);border:1px solid var(--rule);border-radius:9px;
    padding:16px 18px;display:flex;flex-direction:column;gap:10px}}
  .out.err{{border-color:var(--bad)}}
  .out > header{{display:flex;justify-content:space-between;align-items:baseline;gap:10px}}
  .pill{{font-family:"JetBrains Mono",monospace;font-size:.72rem;background:var(--surface-2);
    border-radius:20px;padding:2px 9px;white-space:nowrap}}
  .pill.bad{{background:var(--bad);color:#fff}}
  .meta{{color:var(--muted);line-height:1.5}}
  .script p{{margin:0 0 10px 0;font-size:.94rem;line-height:1.62;color:var(--ink)}}
  .script p:last-child{{margin-bottom:0}}

  details{{border:1px solid var(--rule);border-radius:7px;background:var(--surface-2)}}
  summary{{cursor:pointer;padding:8px 12px;font-size:.79rem;color:var(--muted);
    font-family:"JetBrains Mono",monospace}}
  summary:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
  .brief-body{{padding:2px 12px 12px;max-height:340px;overflow:auto}}
  .brief-body p{{margin:0 0 8px 0;font-size:.83rem;line-height:1.55;color:var(--ink-soft)}}
  details.source pre{{margin:0;padding:12px 14px;max-height:400px;overflow:auto;
    font-family:"JetBrains Mono",monospace;font-size:.76rem;line-height:1.55;
    white-space:pre-wrap;color:var(--ink-soft)}}
  footer{{margin-top:56px;padding-top:20px;border-top:1px solid var(--rule);
    color:var(--muted);font-size:.82rem}}
</style>
<div class="wrap">
  <header class="top">
    <div class="eyebrow">Generated {escape(when)}</div>
    <h1>Which models should write what you hear?</h1>
    <p class="lede">Five setups, two real artefacts, identical inputs and identical
    output targets. Every cost below is measured from the actual token usage each
    call reported — not estimated. Read the scripts, pick what sounds right.</p>
  </header>

  <section id="cost">
    <div class="head"><div class="eyebrow">Measured</div><h2>What each setup costs</h2></div>
    {cost_table(results)}
  </section>

  {section(results, "news_briefing", "Daily News Briefing",
           "Today's real articles, synthesized into the briefing you would hear.")}

  {section(results, "maths_post", "Maths-heavy LessWrong post",
           "A post built on real mathematics. The pipeline's RSS feed strips MathJax "
           "entirely, so today this arrives as sentences with holes in them — this "
           "comparison uses the markdown source, where the LaTeX survives, to show "
           "what a model that can actually read the maths does with it.")}

  <footer>
    Every setup received byte-identical source text and the same audio-output rules,
    so differences are the models, not the prompts. Two-stage setups pass only the
    analyst's brief to the writer — the writer never sees the source. Fable 5 was not
    run; its row projects the Opus 5 single-pass token counts at Fable pricing
    (${FABLE_PRICE[0]:.0f}/${FABLE_PRICE[1]:.0f} per million).
  </footer>
</div>"""


def mock() -> dict:
    """Synthetic data, for checking layout without spending anything."""
    def r(k, label, models, cost, words, brief=False):
        st = [{"role": "comprehend", "model": models[0], "text": "Analyst notes.\n" * 6,
               "usage": {"in": 4000, "out": 900}, "seconds": 20, "cost": cost / 2}] if brief else []
        st.append({"role": "write" if brief else "single-pass", "model": models[-1],
                   "text": "", "usage": {"in": 1200, "out": 600}, "seconds": 15,
                   "cost": cost / 2 if brief else cost})
        return {"key": k, "label": label, "models": models, "cost": cost, "words": words,
                "usage": {"in": 5200, "out": 1500}, "seconds": 35,
                "output": ("Sample script paragraph one.\n\n"
                           "Sample script paragraph two, a little longer.\n"), "stages": st}

    runs = [r("baseline", "Gemini 3 Flash", ["google/gemini-3-flash-preview"], 0.0071, 430),
            r("opus46", "Opus 4.6", ["anthropic/claude-opus-4.6"], 0.061, 445),
            r("opus5", "Opus 5", ["anthropic/claude-opus-5"], 0.064, 441),
            r("opus5_opus46", "Opus 5 → Opus 4.6",
              ["anthropic/claude-opus-5", "anthropic/claude-opus-4.6"], 0.098, 438, True),
            r("sonnet5_opus46", "Sonnet 5 → Opus 4.6",
              ["anthropic/claude-sonnet-5", "anthropic/claude-opus-4.6"], 0.071, 436, True)]
    art = lambda meta, n: {"meta": meta, "source_chars": n, "source_text": "SOURCE " * 200,
                           "runs": runs,
                           "fable_estimate": {"basis": "opus5", "usage": {"in": 5200, "out": 1500},
                                              "cost": 0.127}}
    return {"generated_at": datetime.now().isoformat(),
            "artefacts": {"news_briefing": art({"article_count": 63, "url": ""}, 13630),
                          "maths_post": art({"latex_count": 76,
                                             "url": "https://example.com"}, 8091)}}


def main() -> int:
    if "--mock" in sys.argv:
        results = mock()
        print("  rendering from MOCK data")
    else:
        if not DATA.exists():
            print(f"ERROR: {DATA} not found — run scripts/model_comparison.py first")
            return 1
        results = json.loads(DATA.read_text())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(results))
    print(f"  wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
