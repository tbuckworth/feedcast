"""The second-model source check: parsing, the single revision pass, and the email line."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from openai import InternalServerError

from src.email_report import ReportEpisode, RunReport, build_html, build_text
from src.llm import MODEL_CHECKER, pinned_target
from src.verify import (Fidelity, fidelity_markdown,
                        fidelity_summary, parse_flags, verify_script)
from tests.conftest import FakeApi, provider_error

# A pinned client is OpenRouter's, so it is sent each role's OpenRouter spelling.
PINNED_CHECKER = pinned_target("checker").model
PINNED_WRITER = pinned_target("writer").model


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


def test_parse_flags_reads_the_object_out_of_prose():
    reply = f"Here is my audit.\n{FLAGGED.strip('`').removeprefix('json')}\nThat is all."
    total, flags = parse_flags(reply)
    assert total == 12 and [f["verdict"] for f in flags] == ["distorted", "unsupported"]


@pytest.mark.parametrize("reply, error", [
    ("no json here", "no JSON object in the reply"),
    ('{"claims_total": 2, "flags": [}',
     r"the object is not valid JSON \(Expecting value: line 1 column 31 \(char 30\)\)"),
])
def test_parse_flags_raises_saying_why_a_reply_has_no_flags(reply, error):
    with pytest.raises(ValueError, match=error):
        parse_flags(reply)


def test_clean_script_is_returned_untouched():
    client = FakeClient([CLEAN])
    script, fid = asyncio.run(verify_script("The script.", "The source.", writer_system_prompt="sys", client=client))
    assert script == "The script." and fid.status == "clean" and fid.claims_total == 12
    assert len(client.calls) == 1 and client.calls[0]["model"] == PINNED_CHECKER
    assert fid.checker["model"] == PINNED_CHECKER
    assert "SOURCE:\nThe source." in client.calls[0]["messages"][1]["content"]


def test_material_flag_triggers_one_revision_then_a_recheck():
    revised_text = "Zvi quotes Dwarkesh saying the agents had the access but did not use it. " * 3
    client = FakeClient([FLAGGED, revised_text, CLEAN])
    script, fid = asyncio.run(verify_script("Zvi argues the agents were not capable. " * 3, "src",
                                            writer_system_prompt="Summarise for audio.", client=client))
    assert script == revised_text.strip()
    assert fid.status == "revised" and fid.revised and fid.remaining == []
    assert [c["model"] for c in client.calls] == [PINNED_CHECKER, PINNED_WRITER, PINNED_CHECKER]
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


def test_suspiciously_short_revision_is_rejected(capsys):
    client = FakeClient([FLAGGED, "Sorry.", CLEAN])
    script, fid = asyncio.run(verify_script("A long original script " * 20, "src", writer_system_prompt="s", client=client))
    assert script.startswith("A long original") and fid.status == "flagged" and "rejected" in fid.note
    assert len(client.calls) == 2  # no recheck of a rejected revision
    assert fid.note in capsys.readouterr().out


def test_a_failed_revision_keeps_the_flags_already_found():
    # The draft ships as written, so the email must still say what is wrong with it.
    client = FakeClient([FLAGGED, RuntimeError("writer down")])
    original = "Zvi argues the agents were not capable. " * 3
    script, fid = asyncio.run(verify_script(original, "src", writer_system_prompt="s", client=client))
    assert script == original and fid.status == "flagged" and not fid.revised
    assert [f["verdict"] for f in fid.material] == ["distorted"]
    assert "revision failed" in fid.note and "writer down" in fid.note
    assert fidelity_summary(fid.to_dict()) == "Checked against source: 1 issue flagged, not corrected"


def test_a_failed_recheck_keeps_the_flags_and_ships_the_draft():
    revised_text = "Zvi quotes Dwarkesh saying the agents had the access but did not use it. " * 3
    client = FakeClient([FLAGGED, revised_text, RuntimeError("checker down")])
    original = "Zvi argues the agents were not capable. " * 3
    script, fid = asyncio.run(verify_script(original, "src", writer_system_prompt="s", client=client))
    assert script == original and fid.status == "flagged" and not fid.revised
    assert len(fid.material) == 1
    assert "re-check of the revision failed" in fid.note and "checker down" in fid.note


def test_checker_failure_never_raises():
    client = FakeClient([RuntimeError("openrouter down")])
    script, fid = asyncio.run(verify_script("orig", "src", writer_system_prompt="s", client=client))
    assert script == "orig" and fid.status == "skipped" and "openrouter down" in fid.note


def test_an_empty_first_check_retries_with_reasoning_off_not_a_sibling_model(monkeypatch):
    # Route-level: the first attempt's empty reply must not fall through to
    # Sonnet 4.6 and be reported as a model fallback.
    from src import llm, notices
    from types import SimpleNamespace as NS

    class Api:
        def __init__(self, replies):
            self.replies, self.calls = list(replies), []
            self.chat = NS(completions=NS(create=self._create))

        async def _create(self, **kw):
            self.calls.append(kw)
            r = self.replies.pop(0)
            return NS(choices=[NS(message=NS(content=r), finish_reason="length" if r is None else "stop")],
                      usage=NS(completion_tokens=1))

    api = Api([None, CLEAN])
    monkeypatch.setattr(llm, "client_for", lambda route: api if route.name == "anthropic" else None)
    script, fid = asyncio.run(verify_script("s", "src", writer_system_prompt="p"))
    assert fid.status == "clean"
    # The same primary twice (the compat endpoint takes no reasoning setting,
    # so "off" sends nothing extra), never a sibling model.
    assert [c["model"] for c in api.calls] == [MODEL_CHECKER, MODEL_CHECKER]
    assert notices.report() == []


def test_email_line():
    assert fidelity_summary(None) == ""
    assert fidelity_summary({"status": "skipped", "note": "RuntimeError('openrouter down')"}) == (
        "Fidelity check failed: RuntimeError('openrouter down')")
    assert fidelity_summary({"status": "clean", "flags": []}) == "Checked against source: no issues"
    two = [{"severity": "high"}, {"severity": "medium"}, {"severity": "low"}]
    assert fidelity_summary({"status": "revised", "flags": two, "remaining": []}) == "Checked against source: 2 issues corrected"
    # No subtraction: the re-check is a fresh read and can raise flags the
    # first pass did not, which once printed "-1 corrected".
    assert fidelity_summary({"status": "revised", "flags": two, "remaining": [{"severity": "high"}]}) == (
        "Checked against source: 3 issues flagged in the draft (2 material), revised once; 1 still flagged")
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


def test_a_failed_check_is_in_the_email():
    client = FakeClient([RuntimeError("openrouter down")])
    _, fid = asyncio.run(verify_script("orig", "src", writer_system_prompt="s", client=client))
    ep = ReportEpisode(title="AI #182", author="Zvi", feed_name="Zvi", link="", audio_url="a.mp3",
                       duration_seconds=60, fidelity=fid.to_dict())
    report = RunReport(episodes=[ep])
    assert "Fidelity check failed: RuntimeError(&#x27;openrouter down&#x27;)" in build_html(
        report, datetime(2026, 10, 30))
    assert "(Fidelity check failed: RuntimeError('openrouter down'))" in build_text(
        report, datetime(2026, 10, 30))


def test_the_email_names_the_checker_that_read_the_script(routes):
    # Sonnet 5.5 was down for the re-check, so Sonnet 5 read the revision. The
    # email named the role's primary all the same until 2026-10-30.
    original = "Zvi argues the agents were not capable. " * 3
    revised = "Zvi quotes Dwarkesh saying the agents had the access but did not use it. " * 3
    routes["anthropic"] = FakeApi([FLAGGED, revised,
                                   provider_error(InternalServerError, 500, "overloaded"), FLAGGED])
    _, fid = asyncio.run(verify_script(original, "src", writer_system_prompt="s"))
    assert fid.status == "revised" and fid.remaining
    assert fid.checker["model"] == "claude-sonnet-5" and fid.checker["backup"]
    ep = ReportEpisode(title="AI #182", author="Zvi", feed_name="Zvi", link="", audio_url="a.mp3",
                       duration_seconds=60, fidelity=fid.to_dict())
    report, when = RunReport(episodes=[ep]), datetime(2026, 10, 30)
    assert "Claude Sonnet 5 read each script against its source" in build_html(report, when)
    assert "Claude Sonnet 5 read each script against its source" in build_text(report, when)


def test_a_row_from_before_the_checker_was_recorded_says_the_checker():
    _, flags = parse_flags(FLAGGED)
    ep = ReportEpisode(title="AI #182", author="Zvi", feed_name="Zvi", link="", audio_url="a.mp3",
                       duration_seconds=60, fidelity={"status": "flagged", "flags": flags})
    html = build_html(RunReport(episodes=[ep]), datetime(2026, 10, 30))
    assert "The checker read each script against its source" in html
