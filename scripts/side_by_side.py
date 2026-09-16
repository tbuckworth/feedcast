"""One-off: Opus 4.6 v2b against the true-Sol v2b, side by side, stories aligned.

Reads the saved outputs of scripts/email_v2_test.py (--variant tiered, Opus)
and scripts/sol_true_test.py, aligns each episode's headline bullets by shared
source URLs and shared content words, and renders a two-column HTML page (and a
plain-text fallback). The scripts the bullets came from are aligned the same
way, paragraph by paragraph, in a second table per episode.

    uv run python scripts/side_by_side.py --dir SCRATCH/v2 --out SCRATCH/sbs.html
"""

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import email_v2_test as h  # noqa: E402
from src.digest_variants import parse_tiered  # noqa: E402
from src.email_report import ACCENT, INK, MUTED, RULE, _STOP, bullet_parts  # noqa: E402

LEFT, RIGHT = "Opus 4.6 (as sent in v2b)", "GPT-5.6 Sol (true test)"


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 4 and w not in _STOP}


def flat(b) -> str:
    text, _ = bullet_parts(b)
    subs = b.get("sub", []) if isinstance(b, dict) else []
    return " ".join([text] + [bullet_parts(s)[0] for s in subs])


def urls(b) -> set[str]:
    out = set()
    _, u = bullet_parts(b)
    if u:
        out.add(u)
    for s in (b.get("sub", []) if isinstance(b, dict) else []):
        _, su = bullet_parts(s)
        if su:
            out.add(su)
    return out


def score(a, b) -> float:
    wa, wb = words(flat(a)), words(flat(b))
    if not wa or not wb:
        return 0.0
    s = len(wa & wb) / min(len(wa), len(wb))
    if urls(a) & urls(b):
        s += 0.5
    return s


def align(left: list, right: list, threshold: float = 0.2) -> list[tuple]:
    """Greedy, left order preserved; unmatched right items appended.

    An unmatched item whose content lives inside an already-matched item on
    the other side (a story one writer gave its own headline and the other
    folded into a neighbour) is paired with a string pointer to that row
    instead of a blank, so "not covered" means not covered.
    """
    used, pairs = set(), []
    for a in left:
        best, best_s = None, threshold
        for j, b in enumerate(right):
            if j in used:
                continue
            s = score(a, b)
            if s > best_s:
                best, best_s = j, s
        if best is None:
            folded = max(((score(a, b), b) for j, b in enumerate(right) if j in used),
                         default=(0, None), key=lambda t: t[0])
            pairs.append((a, ("folded", folded[1]) if folded[0] > threshold else None))
        else:
            pairs.append((a, right[best]))
            used.add(best)
    for j, b in enumerate(right):
        if j in used:
            continue
        folded = max(((score(a, b), a) for a in left), default=(0, None), key=lambda t: t[0])
        pairs.append((("folded", folded[1]) if folded[0] > threshold else None, b))
    return pairs


def cell_bullet(b) -> str:
    if b is None:
        return f'<span style="color:{MUTED};font-style:italic;">— not covered —</span>'
    if isinstance(b, tuple) and b[0] == "folded":
        head = bullet_parts(b[1])[0] if not isinstance(b[1], str) else b[1]
        return (f'<span style="color:{MUTED};font-style:italic;">— folded into the row '
                f'&ldquo;{escape(head[:70])}&hellip;&rdquo; —</span>')
    text, url = bullet_parts(b)
    link = (f' <a href="{escape(url, quote=True)}" style="color:{ACCENT};text-decoration:none;'
            f'white-space:nowrap;">Source&nbsp;&rarr;</a>') if url else ""
    out = f'<div style="font-weight:600;">{escape(text)}{link}</div>'
    subs = b.get("sub", []) if isinstance(b, dict) else []
    if subs:
        items = ""
        for s in subs:
            st, su = bullet_parts(s)
            sl = (f' <a href="{escape(su, quote=True)}" style="color:{ACCENT};text-decoration:none;'
                  f'white-space:nowrap;">Source&nbsp;&rarr;</a>') if su else ""
            items += f'<li style="margin:3px 0;">{escape(st)}{sl}</li>'
        out += f'<ul style="margin:4px 0 0 0;padding-left:16px;font-size:12px;">{items}</ul>'
    return out


def paragraphs(script: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", script) if p.strip()]


def two_col(rows: list[tuple[str, str]], head_l: str, head_r: str) -> str:
    th = (f'style="text-align:left;padding:6px 8px;border:1px solid {RULE};background:#f0f0ee;'
          f'font-size:12px;width:50%;"')
    td = f'style="vertical-align:top;padding:7px 8px;border:1px solid {RULE};font-size:13px;line-height:1.45;width:50%;"'
    body = "".join(f"<tr><td {td}>{l}</td><td {td}>{r}</td></tr>" for l, r in rows)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse;table-layout:fixed;margin:6px 0 16px;">'
            f"<tr><th {th}>{escape(head_l)}</th><th {th}>{escape(head_r)}</th></tr>{body}</table>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--intro", type=Path, help="HTML fragment placed above the tables")
    args = ap.parse_args()

    opus_raw = json.loads((args.dir / "raw_tiered.json").read_text())
    sol = json.loads((args.dir / "record_true_sol.json").read_text())
    db = {r["id"]: r for r in h.rows()}

    sections, text_out = [], []
    for eid, rec in sol.items():
        row = db[eid]
        is_briefing = eid.startswith("news-briefing-")
        allowed = {s["url"] for s in h.briefing_sources(row)} if is_briefing else set()
        left = parse_tiered(opus_raw[eid]["full_raw"], allowed)
        right = parse_tiered(rec["sol_digest_raw"], allowed)
        pairs = align(left, right)
        of, sf = rec["opus_fidelity"] or {}, rec["sol_fidelity"] or {}
        meta = (f"Opus: {len(left)} headlines, {sum(len(b.get('sub', [])) for b in left)} sub-bullets, "
                f"{len(of.get('remaining', []))} checker complaints remaining &middot; "
                f"Sol: {len(right)} headlines, {sum(len(b.get('sub', [])) for b in right)} sub-bullets, "
                f"{len(sf.get('remaining', []))} remaining")
        sections.append(
            f'<h3 style="font-size:16px;margin:22px 0 2px;color:{INK};">{escape(rec["title"])}</h3>'
            f'<div style="font-size:12px;color:{MUTED};margin-bottom:6px;">{meta}</div>'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;'
            f'color:{MUTED};margin:10px 0 2px;">Email bullets</div>'
            + two_col([(cell_bullet(a), cell_bullet(b)) for a, b in pairs], LEFT, RIGHT)
        )
        # scripts, paragraph-aligned
        lp, rp = paragraphs(rec["opus_script"]), paragraphs(rec["sol_script"])
        ppairs = align(lp, rp, threshold=0.15)
        def pcell(p) -> str:
            if p is None:
                return f'<span style="color:{MUTED};font-style:italic;">— no matching paragraph —</span>'
            if isinstance(p, tuple):
                return (f'<span style="color:{MUTED};font-style:italic;">— covered in the paragraph '
                        f'starting &ldquo;{escape(p[1][:60])}&hellip;&rdquo; —</span>')
            return escape(p)
        sections.append(
            f'<div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;'
            f'color:{MUTED};margin:10px 0 2px;">Spoken script the bullets came from '
            f'({len(rec["opus_script"].split())} vs {len(rec["sol_script"].split())} words)</div>'
            + two_col([(pcell(a), pcell(b)) for a, b in ppairs],
                      "Opus 4.6 script (this is today's audio)", "GPT-5.6 Sol script (no audio made)")
        )
        text_out.append(f"== {rec['title']} ==")
        def tflat(x) -> str:
            if x is None:
                return "— not covered —"
            if isinstance(x, tuple):
                return "— folded into: " + bullet_parts(x[1])[0][:60] + "… —"
            return flat(x)

        for a, b in pairs:
            text_out.append("OPUS: " + tflat(a))
            text_out.append("SOL:  " + tflat(b))
            text_out.append("")

    intro = args.intro.read_text() if args.intro else ""
    html = (f'<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Helvetica,Arial,sans-serif;'
            f'color:{INK};max-width:900px;margin:0 auto;padding:12px;">{intro}{"".join(sections)}</div>')
    args.out.write_text(html, encoding="utf-8")
    args.out.with_suffix(".txt").write_text(
        re.sub(r"<[^>]+>", "", intro).strip() + "\n\n" + "\n".join(text_out), encoding="utf-8")
    print(f"wrote {args.out} and {args.out.with_suffix('.txt')}")


if __name__ == "__main__":
    main()
