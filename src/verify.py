"""Check a written script against its source with a second model, and fix it once.

The writer is a single completion with no tools: when its input is thin it
fills gaps from memory, and when a post quotes someone the author disagrees
with, the summary can hand the author the other person's view (a figure the
author quotes in order to correct it, repeated as fact). A listener has no
way to notice.

So the checker role, a different and cheaper model, reads the script against
the source and lists what is contradicted, distorted or unsupported. If anything material comes
back, the writer gets one pass to fix exactly those points, then the checker
reads the result again so the email can say honestly what remains. Omissions
and paraphrase are never flagged: the point is fidelity, not completeness,
and a nitpicking checker would push the writer into hedged mush.

The check (`verify_script`) never raises. A check that fails leaves the
script as written and says so: a failed first check is reported as such, and
a failed revision or re-check keeps the flags the first check found.
`write_checked`, which also writes the script, raises when the writer fails.
"""

from dataclasses import asdict, dataclass, field

from .bundle import writer_bundle
from .llm import EmptyCompletion, complete, extract_json

MATERIAL = ("high", "medium")


def material_flags(flags: list[dict]) -> list[dict]:
    """The flags worth a revision and a line in the email: high and medium severity."""
    return [f for f in flags if f.get("severity") in MATERIAL]


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
    # Which model read the script for the flags the email shows, as
    # llm.Completion.credit() records it: the re-check's once the script was
    # revised. None when no check succeeded, and on rows stored before the
    # field existed.
    checker: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def material(self) -> list[dict]:
        return material_flags(self.flags)


def parse_flags(raw: str) -> tuple[int, list[dict]]:
    """Pull (claims_total, flags) out of a reply, tolerating fences and prose."""
    data = extract_json(raw, dict)
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


# Sonnet reasons before it answers, and the reasoning counts against
# max_tokens. Left to the provider's defaults it can consume the whole budget
# (a 16,000 cap has come back with finish_reason=length and no visible text).
# So: a fixed thinking budget first, and if the reply is still empty, once
# more with reasoning off. Verification does not need a long think.
CHECK_ATTEMPTS = (
    {"budget": 4000},
    {"off": True},
)


async def check(script: str, source: str, client=None) -> tuple[int, list[dict]]:
    """(claims_total, flags) for `script` read against `source`."""
    total, flags, _ = await _check(script, source, client)
    return total, flags


async def _check(script: str, source: str, client=None) -> tuple[int, list[dict], dict]:
    """check(), plus the credit of the model that read the script."""
    user = f"SOURCE:\n{source}\n\nSCRIPT:\n{script}"
    last = ""
    for i, reasoning in enumerate(CHECK_ATTEMPTS):
        try:
            done = await complete(
                "checker", max_tokens=16000, temperature=0, client=client,
                reasoning=reasoning, label="checker",
                messages=[{"role": "system", "content": CHECK_PROMPT},
                          {"role": "user", "content": user}],
                # An empty first reply is the budget-eaten case this loop
                # exists for: retry with reasoning off (from the primary
                # again) rather than hand the check to a sibling model and
                # report a fallback. The last attempt may fall back like any
                # other call.
                fallback_on_empty=(i == len(CHECK_ATTEMPTS) - 1))
        except EmptyCompletion as e:
            last = str(e)
            print(f"    checker: empty reply {reasoning}: {e}")
            continue
        finish, content, usage = done.finish_reason, done.text or "", done.usage
        print(f"    checker: finish={finish} "
              f"out={getattr(usage, 'completion_tokens', '?')} chars={len(content)} {reasoning}")
        try:
            return (*parse_flags(content), done.credit())
        except ValueError as e:
            last = (f"{e} (finish_reason={finish}, "
                    f"{len(content)} chars: {content[:160]!r})")
            if content.strip():
                break  # a real but unparseable reply; retrying will not help
    raise ValueError(last)


def _flags_text(flags: list[dict]) -> str:
    return "\n".join(
        f"- [{f['verdict']}, {f['severity']}] \"{f['script_quote']}\" — {f['explanation']}"
        + (f" (source: \"{f['source_quote']}\")" if f.get("source_quote") else "")
        for f in flags)


async def revise(script: str, source: str, flags: list[dict],
                 writer_system_prompt: str, client=None) -> str:
    user = (f"SOURCE:\n{source}\n\nYOUR SCRIPT:\n{script}\n\n"
            f"PROBLEMS FOUND:\n{_flags_text(flags)}\n\n{REVISE_PROMPT}")
    done = await complete(
        "writer", max_tokens=16000, client=client, label="revision",
        messages=[{"role": "system", "content": writer_system_prompt},
                  {"role": "user", "content": user}])
    return (done.text or "").strip()


async def verify_script(script: str, source: str, *, writer_system_prompt: str,
                        label: str = "", client=None) -> tuple[str, Fidelity]:
    """Check `script` against `source`; fix it once if needed. Returns (script, fidelity).

    When the revision or its re-check fails, the draft ships as written with
    the flags the first check found ("flagged"), so the email still says what
    is wrong with it; when the first check itself fails it is "skipped", and
    the email says the check failed and why.
    """
    where = f" ({label})" if label else ""
    try:
        total, flags, checker = await _check(script, source, client)
    except Exception as e:  # noqa: BLE001 — a failed check must never fail the episode
        print(f"    Fidelity check failed{where}: {e!r}")
        return script, Fidelity(status="skipped", note=repr(e))
    fid = Fidelity(status="clean", claims_total=total, flags=flags, checker=checker)
    material = fid.material
    print(f"    Fidelity check{where}: {total} claims, {len(flags)} flags, {len(material)} material")
    if not material:
        return script, fid
    fid.status = "flagged"
    try:
        revised = await revise(script, source, material, writer_system_prompt, client)
    except Exception as e:  # noqa: BLE001 — the draft ships with its flags instead
        fid.note = f"revision failed: {e!r}"
        print(f"    Fidelity{where}: {fid.note}")
        return script, fid
    if len(revised) < 0.6 * len(script):
        fid.note = f"revision rejected: {len(revised)} chars vs {len(script)}"
        print(f"    Fidelity{where}: {fid.note}")
        return script, fid
    try:
        _, after, checker = await _check(revised, source, client)
    except Exception as e:  # noqa: BLE001 — an unchecked revision does not ship
        fid.note = f"re-check of the revision failed, draft kept: {e!r}"
        print(f"    Fidelity{where}: {fid.note}")
        return script, fid
    fid.status = "revised"
    fid.revised = True
    fid.remaining = material_flags(after)
    fid.checker = checker
    print(f"    Revised; {len(fid.remaining)} material flags remain")
    return revised, fid


def fidelity_summary(fid: dict | None) -> str:
    """One line for the email. '' when no check ran."""
    if not fid or not fid.get("status"):
        return ""
    if fid["status"] == "skipped":
        note = str(fid.get("note") or "")[:200]
        return f"Fidelity check failed: {note}" if note else "Fidelity check failed"
    n, rem = len(material_flags(fid.get("flags", []))), len(fid.get("remaining", []))
    plural = lambda k: "issue" if k == 1 else "issues"  # noqa: E731
    if fid["status"] == "clean":
        return "Checked against source: no issues"
    if fid["status"] == "flagged":
        return f"Checked against source: {n} {plural(n)} flagged, not corrected"
    # `remaining` is a fresh read of the revised script, so it can hold flags
    # the first pass never raised, and subtracting it from the draft count can
    # go negative. Say what each number is instead.
    if rem:
        total = len(fid.get("flags", []))
        return (f"Checked against source: {total} {plural(total)} flagged in the draft "
                f"({n} material), revised once; {rem} still flagged")
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


@dataclass
class Written:
    """A writer's script after the fidelity check, and what its episode records about it."""

    text: str                 # the script, revised once if the check asked for it
    writer: dict              # who wrote it (`Completion.credit()`)
    fidelity: dict | None     # the check (`Fidelity.to_dict()`); None when it is off
    bundle: str               # what the writer saw and wrote (src/bundle.py)


async def write_checked(system_prompt: str, user_message: str, *, title: str, label: str,
                        check_label: str, verify: bool, client=None) -> Written:
    """Write a script with the writer role, check it against `user_message`, and bundle both.

    `title` heads the bundle; `label` names the writer call in the logs and the
    fallback notices, `check_label` the fidelity check in the logs. With
    `verify` off the draft is the script and no check runs.

    Raises what `llm.complete` raises when the writer fails on every target,
    so the caller can fail the entry; the check itself never raises.
    """
    done = await complete(
        "writer", max_tokens=16000, client=client, label=label,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_message}])
    script, fidelity = done.text, None
    if verify:
        script, fidelity = await verify_script(
            done.text, user_message, writer_system_prompt=system_prompt,
            label=check_label, client=client)
    bundle = writer_bundle(
        title=title, model=done.target.label, system_prompt=system_prompt,
        user_message=user_message, response=script,
        notes=fidelity_markdown(fidelity, done.text if fidelity and fidelity.revised else None))
    return Written(text=script, writer=done.credit(),
                   fidelity=fidelity.to_dict() if fidelity else None, bundle=bundle)
