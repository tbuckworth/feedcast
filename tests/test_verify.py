"""The second-model source check: parsing, the single revision pass, and the email line."""

import asyncio
from types import SimpleNamespace

import pytest

from src.verify import (MODEL_CHECKER, MODEL_WRITER, Fidelity, fidelity_markdown,
                        fidelity_summary, parse_flags, verify_script)


class FakeClient:
    """Replies in order; records every call's model and messages.

    A reply may be a string, an exception, or ("length", "") to simulate a
    budget exhausted by hidden reasoning.
    """

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        self.calls.append(kw)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        finish, content = reply if isinstance(reply, tuple) else ("stop", reply)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
            usage=SimpleNamespace(completion_tokens=1))


CLEAN = '{"claims_total": 12, "flags": []}'
FLAGGED = ('```json\n{"claims_total": 12, "flags": [\n'
           ' {"verdict": "distorted", "severity": "high", "script_quote": "Zvi argues the agents were not capable",'
           '  "source_quote": "Dwarkesh: they had the access", "explanation": "Zvi quotes Dwarkesh approvingly saying the opposite"},\n'
           ' {"verdict": "unsupported", "severity": "low", "script_quote": "a fifth of global oil", "source_quote": "", "explanation": "background"}\n'
           ']}\n```')


def test_parse_flags_tolerates_fences_and_drops_malformed():
    total, flags = parse_flags(FLAGGED)
    assert total == 12 and len(flags) == 2
    assert flags[0]["verdict"] == "distorted" and flags[0]["severity"] == "high"
    _, bad = parse_flags('{"flags": [{"verdict": "omitted", "severity": "high"}, "junk", {"verdict": "unsupported", "severity": "silly"}]}')
    assert [f["verdict"] for f in bad] == ["unsupported"] and bad[0]["severity"] == "medium"
    with pytest.raises(ValueError):
        parse_flags("no json here")


def test_clean_script_is_returned_untouched():
    client = FakeClient([CLEAN])
    script, fid = asyncio.run(verify_script("The script.", "The source.", writer_system_prompt="sys", client=client))
    assert script == "The script." and fid.status == "clean" and fid.claims_total == 12
    assert len(client.calls) == 1 and client.calls[0]["model"] == MODEL_CHECKER
    assert "SOURCE:\nThe source." in client.calls[0]["messages"][1]["content"]


def test_material_flag_triggers_one_revision_then_a_recheck():
    revised_text = "Zvi quotes Dwarkesh saying the agents had the access but did not use it. " * 3
    client = FakeClient([FLAGGED, revised_text, CLEAN])
    script, fid = asyncio.run(verify_script("Zvi argues the agents were not capable. " * 3, "src",
                                            writer_system_prompt="Summarise for audio.", client=client))
    assert script == revised_text.strip()
    assert fid.status == "revised" and fid.revised and fid.remaining == []
    assert [c["model"] for c in client.calls] == [MODEL_CHECKER, MODEL_WRITER, MODEL_CHECKER]
    revise_call = client.calls[1]
    assert revise_call["messages"][0]["content"] == "Summarise for audio."
    # Only the material flag is handed to the writer; the low-severity one is not.
    assert "not capable" in revise_call["messages"][1]["content"]
    assert "fifth of global oil" not in revise_call["messages"][1]["content"]


def test_low_severity_only_does_not_revise():
    low = '{"claims_total": 5, "flags": [{"verdict": "unsupported", "severity": "low", "script_quote": "x", "source_quote": "", "explanation": "bg"}]}'
    client = FakeClient([low])
    script, fid = asyncio.run(verify_script("orig", "src", writer_system_prompt="s", client=client))
    assert script == "orig" and fid.status == "clean" and len(fid.flags) == 1 and len(client.calls) == 1


def test_suspiciously_short_revision_is_rejected():
    client = FakeClient([FLAGGED, "Sorry.", CLEAN])
    script, fid = asyncio.run(verify_script("A long original script " * 20, "src", writer_system_prompt="s", client=client))
    assert script.startswith("A long original") and fid.status == "flagged" and "rejected" in fid.note
    assert len(client.calls) == 2  # no recheck of a rejected revision


def test_checker_failure_never_raises():
    client = FakeClient([RuntimeError("openrouter down")])
    script, fid = asyncio.run(verify_script("orig", "src", writer_system_prompt="s", client=client))
    assert script == "orig" and fid.status == "skipped" and "openrouter down" in fid.note


def test_email_line():
    assert fidelity_summary(None) == ""
    assert fidelity_summary({"status": "skipped"}) == ""
    assert fidelity_summary({"status": "clean", "flags": []}) == "Checked against source: no issues"
    two = [{"severity": "high"}, {"severity": "medium"}, {"severity": "low"}]
    assert fidelity_summary({"status": "revised", "flags": two, "remaining": []}) == "Checked against source: 2 issues corrected"
    assert fidelity_summary({"status": "revised", "flags": two, "remaining": [{"severity": "high"}]}) == "Checked against source: 1 corrected, 1 still flagged"
    assert fidelity_summary({"status": "flagged", "flags": two[:1], "remaining": []}) == "Checked against source: 1 issue flagged, not corrected"


def test_bundle_section_keeps_the_draft_when_revised():
    fid = Fidelity(status="revised", claims_total=3, revised=True,
                   flags=[{"verdict": "distorted", "severity": "high", "script_quote": "q", "source_quote": "s", "explanation": "e"}])
    md = fidelity_markdown(fid, draft="the first draft")
    assert "Status: revised" in md and "[distorted, high]" in md
    assert "### Draft before revision\n\nthe first draft" in md
    assert fidelity_markdown(None) == ""


def test_empty_reply_from_exhausted_reasoning_retries_without_reasoning():
    client = FakeClient([("length", ""), CLEAN])
    script, fid = asyncio.run(verify_script("s", "src", writer_system_prompt="p", client=client))
    assert fid.status == "clean" and script == "s"
    assert client.calls[0]["extra_body"] == {"reasoning": {"max_tokens": 4000}}
    assert client.calls[1]["extra_body"] == {"reasoning": {"enabled": False}}


def test_unparseable_but_nonempty_reply_is_not_retried():
    client = FakeClient(["I refuse to answer in JSON."])
    _, fid = asyncio.run(verify_script("s", "src", writer_system_prompt="p", client=client))
    assert fid.status == "skipped" and "no JSON object" in fid.note and len(client.calls) == 1
