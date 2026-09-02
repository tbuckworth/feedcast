"""Check a written script against its source with a second model, and fix it once.

The writer is a single completion with no tools: when its input is thin it
fills gaps from memory, and when a post quotes someone the author disagrees
with, the summary can hand the author the other person's view. An audit of
three summaries on 2026-09-02 found exactly that — Yudkowsky's "zero of 1,200
agents" repeated as fact after Zvi had corrected it to six; a claim the agents
"were not capable enough" where Zvi approvingly quotes the opposite — and a
listener has no way to notice.

So a cheaper model (Sonnet) reads the script against the source and lists
what is contradicted, distorted or unsupported. If anything material comes
back, the writer gets one pass to fix exactly those points, then the checker
reads the result again so the email can say honestly what remains. Omissions
and paraphrase are never flagged: the point is fidelity, not completeness,
and a nitpicking checker would push the writer into hedged mush.

Never raises. A check that fails leaves the script as written and says so.
"""

import json
import re
from dataclasses import asdict, dataclass, field

from .llm import MODEL_CHECKER, MODEL_WRITER, get_client

MATERIAL = ("high", "medium")
VERDICTS = ("contradicted", "distorted", "unsupported")

CHECK_PROMPT = """You audit a script written for audio against the source material it was written from.

Split the SCRIPT into its factual claims and decide whether the SOURCE supports each one. Report only claims that are:
- contradicted: the source says something incompatible.
- distorted: present in the source but changed in a way that matters — wrong attribution (the author's own view versus someone the author quotes, summarises or argues against), a stance inverted or overstated, a hedge or qualifier dropped, a number or date changed, a speculation stated as fact.
- unsupported: not in the source at all.

Rules:
- Omission is not an error. Paraphrase is not an error. Condensing is the job.
- Background a listener would take as common knowledge is low severity. Anything a listener would repeat as "the author said" is high.
- Numbers may be spelled out in the script ("forty-five percent" for 45%). That is never a discrepancy.
- Keep every quote under 200 characters and verbatim from the text it comes from.
- Report at most 12 flags, the most material first.

Return ONLY JSON:
{"claims_total": <int>,
 "flags": [{"verdict": "contradicted|distorted|unsupported", "severity": "high|medium|low",
            "script_quote": "...", "source_quote": "...", "explanation": "..."}]}"""

REVISE_PROMPT = """A second model checked the script you wrote against the source and found the problems listed below. Produce a corrected script.

Fix exactly these problems — correct the attribution, restore the hedge, replace or remove the unsupported detail — and change nothing else. Keep the length, structure, voice and every other sentence as they are. Return only the corrected script, with no preamble or commentary."""


@dataclass
class Fidelity:
    """What the check found and what was done about it. Stored as JSON."""

    status: str                       # clean | revised | flagged | skipped
    claims_total: int = 0
    flags: list[dict] = field(default_factory=list)      # on the original script
    remaining: list[dict] = field(default_factory=list)  # material flags after revision
    revised: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def material(self) -> list[dict]:
        return [f for f in self.flags if f.get("severity") in MATERIAL]


def parse_flags(raw: str) -> tuple[int, list[dict]]:
    """Pull (claims_total, flags) out of a reply, tolerating fences and prose."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object in checker reply")
    data = json.loads(m.group(0))
    flags = []
    for f in data.get("flags", []) or []:
        if not isinstance(f, dict):
            continue
        verdict = str(f.get("verdict", "")).lower()
        if verdict not in VERDICTS:
            continue
        severity = str(f.get("severity", "medium")).lower()
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        flags.append({
            "verdict": verdict, "severity": severity,
            "script_quote": str(f.get("script_quote", ""))[:300],
            "source_quote": str(f.get("source_quote", ""))[:300],
            "explanation": str(f.get("explanation", ""))[:600],
        })
    try:
        total = int(data.get("claims_total", 0))
    except (TypeError, ValueError):
        total = 0
    return total, flags


async def check(script: str, source: str, client) -> tuple[int, list[dict]]:
    user = f"SOURCE:\n{source}\n\nSCRIPT:\n{script}"
    # Sonnet reasons before it answers and the reasoning counts against
    # max_tokens: a 1,900-character reply cost 5,300 output tokens on
    # 2026-09-02, and a 6,000 cap truncated the JSON on both scripts that day.
    response = await client.chat.completions.create(
        model=MODEL_CHECKER, max_tokens=16000, temperature=0,
        messages=[{"role": "system", "content": CHECK_PROMPT},
                  {"role": "user", "content": user}])
    choice = response.choices[0]
    content = choice.message.content or ""
    try:
        return parse_flags(content)
    except ValueError as e:
        raise ValueError(f"{e} (finish_reason={choice.finish_reason}, "
                         f"{len(content)} chars: {content[:160]!r})") from e


def _flags_text(flags: list[dict]) -> str:
    return "\n".join(
        f"- [{f['verdict']}, {f['severity']}] \"{f['script_quote']}\" — {f['explanation']}"
        + (f" (source: \"{f['source_quote']}\")" if f.get("source_quote") else "")
        for f in flags)


async def revise(script: str, source: str, flags: list[dict],
                 writer_system_prompt: str, client) -> str:
    user = (f"SOURCE:\n{source}\n\nYOUR SCRIPT:\n{script}\n\n"
            f"PROBLEMS FOUND:\n{_flags_text(flags)}\n\n{REVISE_PROMPT}")
    response = await client.chat.completions.create(
        model=MODEL_WRITER, max_tokens=16000,
        messages=[{"role": "system", "content": writer_system_prompt},
                  {"role": "user", "content": user}])
    return (response.choices[0].message.content or "").strip()


async def verify_script(script: str, source: str, *, writer_system_prompt: str,
                        label: str = "", client=None, revise_once: bool = True,
                        ) -> tuple[str, Fidelity]:
    """Check `script` against `source`; fix it once if needed. Returns (script, fidelity)."""
    try:
        client = client or get_client()
        total, flags = await check(script, source, client)
        fid = Fidelity(status="clean", claims_total=total, flags=flags)
        material = fid.material
        print(f"    Fidelity check{f' ({label})' if label else ''}: "
              f"{total} claims, {len(flags)} flags, {len(material)} material")
        if not material:
            return script, fid
        if not revise_once:
            fid.status = "flagged"
            return script, fid
        revised = await revise(script, source, material, writer_system_prompt, client)
        if len(revised) < 0.6 * len(script):
            fid.status = "flagged"
            fid.note = f"revision rejected: {len(revised)} chars vs {len(script)}"
            return script, fid
        _, after = await check(revised, source, client)
        fid.status = "revised"
        fid.revised = True
        fid.remaining = [f for f in after if f.get("severity") in MATERIAL]
        print(f"    Revised; {len(fid.remaining)} material flags remain")
        return revised, fid
    except Exception as e:  # noqa: BLE001 — a failed check must never fail the episode
        print(f"    Fidelity check skipped{f' ({label})' if label else ''}: {e!r}")
        return script, Fidelity(status="skipped", note=repr(e))


def fidelity_summary(fid: dict | None) -> str:
    """One line for the email. '' when there is nothing worth saying."""
    if not fid or fid.get("status") in (None, "", "skipped"):
        return ""
    material = [f for f in fid.get("flags", []) if f.get("severity") in MATERIAL]
    n, rem = len(material), len(fid.get("remaining", []))
    plural = lambda k: "issue" if k == 1 else "issues"  # noqa: E731
    if fid["status"] == "clean":
        return "Checked against source: no issues"
    if fid["status"] == "flagged":
        return f"Checked against source: {n} {plural(n)} flagged, not corrected"
    if rem:
        return f"Checked against source: {n - rem} corrected, {rem} still flagged"
    return f"Checked against source: {n} {plural(n)} corrected"


def fidelity_markdown(fid: Fidelity | None, draft: str | None = None) -> str:
    """Section for the episode's source bundle."""
    if fid is None:
        return ""
    lines = [f"Status: {fid.status}" + (f" ({fid.note})" if fid.note else ""),
             f"Claims: {fid.claims_total}; flags: {len(fid.flags)}; material: {len(fid.material)}", ""]
    if fid.flags:
        lines += ["Flags on the draft:", _flags_text(fid.flags), ""]
    if fid.revised:
        lines += ["Remaining after revision:",
                  _flags_text(fid.remaining) if fid.remaining else "- none", ""]
        if draft:
            lines += ["### Draft before revision", "", draft.rstrip(), ""]
    return "\n".join(lines)
