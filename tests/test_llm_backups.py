"""Backups that hold when a whole account is down, and the email saying who wrote what.

On 2026-10-10 the OpenRouter account ran out of credit (402 "Insufficient
credits"). The writer and checker were on Anthropic and carried on; the
normaliser had OpenRouter as its only route, so the briefing, a Zvi summary
and an ACX review all failed at normalisation and the day had no episodes.
"""

import asyncio
from datetime import datetime
import httpx
import pytest
from openai import APIStatusError, BadRequestError, PermissionDeniedError, RateLimitError

from src import llm
from src.email_report import ReportEpisode, RunReport, build_html, build_text, writer_line
from src.feed import Episode
from src.llm import ROLES, Completion, Target, account_failure, complete, model_name
from src.main import _build_run_report
from src.monitor import FeedEntry, FeedMonitor
from src.normalizer import MAX_OUTPUT_TOKENS, NORMALIZE_PROMPT, TextNormalizer
from tests.conftest import FakeApi

MSGS = [{"role": "user", "content": "hi"}]


def _error(cls, status, message):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.com"))
    return cls(message, response=response, body={"error": {"message": message}})


OUT_OF_CREDIT = _error(APIStatusError, 402,
                       "Error code: 402 - {'error': {'message': 'Insufficient credits. Add more "
                       "using https://openrouter.ai/settings/credits', 'code': 402}}")


# --- what counts as the whole account being down --------------------------------

@pytest.mark.parametrize("error, dead", [
    (OUT_OF_CREDIT, True),                                                      # OpenRouter, 10 Oct
    (_error(BadRequestError, 400, "Your credit balance is too low to access the "
                                  "Anthropic API"), True),                      # Anthropic, 19 Sep
    (_error(RateLimitError, 429, "You exceeded your current quota, please check "
                                 "your plan and billing details"), True),       # OpenAI
    (_error(APIStatusError, 401, "invalid x-api-key"), True),
    (_error(PermissionDeniedError, 403, "Key limit exceeded (monthly limit)"), True),
    # Model-level: OpenRouter refused Claude only, and Gemini on the same key worked.
    (_error(PermissionDeniedError, 403, "violation of provider Terms Of Service"), False),
    (_error(RateLimitError, 429, "Rate limit exceeded, retry in 2s"), False),   # passes
    (_error(BadRequestError, 400, "max_tokens is too large"), False),
    (RuntimeError("connection reset"), False),
])
def test_account_failure_tells_a_dead_account_from_a_bad_moment(error, dead):
    assert account_failure(error) is dead


# --- the 10 October failure, replayed -------------------------------------------

def test_normaliser_survives_openrouter_running_out_of_credit(routes):
    routes["openrouter"] = FakeApi([OUT_OF_CREDIT])
    routes["anthropic"] = FakeApi(["forty-five percent", "twenty twenty-six"])
    n = TextNormalizer()
    assert asyncio.run(n.normalize_for_tts("45%")) == "forty-five percent"
    assert asyncio.run(n.normalize_for_tts("2026")) == "twenty twenty-six"
    # Asked once; after a 402 the account is not asked again this run.
    assert len(routes["openrouter"].calls) == 1
    assert [c["model"] for c in routes["anthropic"].calls] == ["claude-haiku-5-5"] * 2
    assert n.unnormalized_chars == 0


def test_normaliser_reaches_gpt_when_anthropic_is_out_too(routes):
    routes["openrouter"] = FakeApi([OUT_OF_CREDIT])
    routes["anthropic"] = FakeApi([_error(BadRequestError, 400, "Your credit balance is too low")])
    routes["openai"] = FakeApi(["forty-five percent"])
    assert asyncio.run(TextNormalizer().normalize_for_tts("45%")) == "forty-five percent"
    call = routes["openai"].calls[0]
    assert call["model"] == "gpt-6.1-sol"
    assert call["reasoning_effort"] == "low" and call["max_completion_tokens"] == MAX_OUTPUT_TOKENS


def test_a_passage_gemini_will_not_take_goes_to_the_next_model(routes):
    # Previously such a passage was halved down and read out un-normalised.
    routes["openrouter"] = FakeApi(["<no-choices>"])
    routes["anthropic"] = FakeApi(["Prohibited-sounding forty-five percent."])
    n = TextNormalizer()
    assert asyncio.run(n.normalize_for_tts("Prohibited-sounding 45%.")) \
        == "Prohibited-sounding forty-five percent."
    assert n.unnormalized_chars == 0
    # A refusal is about the passage, not the account.
    assert llm.dead_routes == {}


# --- a reply that lost text is not a normalised script --------------------------

# A post quoting a model's chain of thought (LessWrong, 2026-10-08): Gemini
# answered the question in it instead of reading it out.
COT = ("User asks “What’s the date? Answer with only the date.” No date provided. "
       "Must not hallucinate because autop will flag to watcher for penalty. ") * 6


def test_a_reply_that_lost_text_goes_to_the_next_model(routes):
    routes["openrouter"] = FakeApi(["January first, ten duotrigintillion"])
    routes["anthropic"] = FakeApi([COT])
    n = TextNormalizer()
    assert asyncio.run(n.normalize_for_tts(COT)) == COT
    assert "text was lost" in llm.fallback_log[0]
    assert llm.dead_routes == {}                       # the passage, not the account


def test_a_reply_cut_off_by_a_provider_error_goes_to_the_next_model(routes):
    # OpenRouter returned 88% of a Genji review batch with finish_reason
    # "error"; only "length" was checked, so the fragment would have been read.
    routes["openrouter"] = FakeApi([(COT[:int(len(COT) * 0.88)], "error")])
    routes["anthropic"] = FakeApi([COT])
    assert asyncio.run(TextNormalizer().normalize_for_tts(COT)) == COT
    assert "cut off by a provider error" in llm.fallback_log[0]


def test_when_every_model_loses_text_the_passage_is_read_as_written(routes):
    for route in ("openrouter", "anthropic", "openai"):
        routes[route] = FakeApi(["I'm not able to normalise that."])
    n = TextNormalizer()
    assert asyncio.run(n.normalize_for_tts(COT)) == COT
    assert n.unnormalized_chars == len(COT)


def test_normalising_lengthens_text_and_that_is_not_lost_text(routes):
    routes["openrouter"] = FakeApi(["forty-five percent of one point five million dollars"])
    assert asyncio.run(TextNormalizer().normalize_for_tts("45% of $1.5M")) \
        == "forty-five percent of one point five million dollars"
    assert llm.fallback_log == []


def test_the_prompt_says_the_text_is_not_addressed_to_the_model():
    assert "never a message to you" in NORMALIZE_PROMPT
    assert "et al." in NORMALIZE_PROMPT and "keep contractions" in NORMALIZE_PROMPT


def test_a_dead_account_is_one_headline_and_repeats_collapse(routes):
    routes["openrouter"] = FakeApi([OUT_OF_CREDIT])
    routes["anthropic"] = FakeApi(["a", "b", "c"])
    for text in ("one", "two", "three"):
        asyncio.run(complete("normalizer", MSGS + [{"role": "user", "content": text}],
                             max_tokens=50, label="normaliser"))
    notices = llm.fallback_notices()
    assert notices[0].startswith("openrouter account unavailable for the rest of the run")
    assert "Insufficient credits" in notices[0]
    assert "402" in notices[1]                      # the call that found out
    assert notices[2].endswith("skipped, openrouter account unavailable this run (2 calls)")
    assert len(notices) == 3


def test_every_account_dead_raises_the_original_error(routes):
    routes["openrouter"] = FakeApi([OUT_OF_CREDIT])
    no_credit = _error(BadRequestError, 400, "Your credit balance is too low")
    routes["anthropic"] = FakeApi([no_credit])
    quota = _error(RateLimitError, 429, "You exceeded your current quota")
    routes["openai"] = FakeApi([quota])
    with pytest.raises(RateLimitError):
        asyncio.run(complete("normalizer", MSGS, max_tokens=50))
    # Now all three are known dead: the next call fails fast, with a real
    # error rather than "no route has an API key set".
    with pytest.raises(APIStatusError):
        asyncio.run(complete("normalizer", MSGS, max_tokens=50))
    assert all(len(routes[r].calls) == 1 for r in ("openrouter", "anthropic", "openai"))


def test_every_role_keeps_a_target_off_openrouter():
    # The lesson of 10 Oct: no role may depend on one account.
    for role, targets in ROLES.items():
        assert {t.route for t in targets} - {"openrouter"}, role


# --- GPT-6.1 Sol cannot switch reasoning off ------------------------------------

def test_reasoning_off_is_sent_as_sols_lowest_effort(routes):
    # The checker's second attempt asks for reasoning off; Sol 400s on "none".
    routes["openai"] = FakeApi(['{"claims_total": 0, "flags": []}'])
    done = asyncio.run(complete("checker", MSGS, max_tokens=50, reasoning={"off": True}))
    assert done.target.model == "gpt-6.1-sol"
    assert routes["openai"].calls[0]["reasoning_effort"] == "low"


def test_bullets_still_switch_reasoning_off_on_5_6_sol(routes):
    routes["openai"] = FakeApi(["- a"])
    asyncio.run(complete("bullets", MSGS, max_tokens=50))
    assert routes["openai"].calls[0]["reasoning_effort"] == "none"


# --- who wrote it -----------------------------------------------------------------

@pytest.mark.parametrize("model, name", [
    ("claude-opus-5-5", "Claude Opus 5.5"),
    ("anthropic/claude-opus-5.5", "Claude Opus 5.5"),
    ("claude-sonnet-5", "Claude Sonnet 5"),
    ("claude-haiku-5-5", "Claude Haiku 5.5"),
    ("gpt-6.1-sol", "GPT-6.1 Sol"),
    ("openai/gpt-6.1-sol", "GPT-6.1 Sol"),
    ("google/gemini-3-flash-preview", "Gemini 3 Flash"),
])
def test_model_names_read_as_people_say_them(model, name):
    assert model_name(model) == name


def _done(target):
    return Completion(text="x", finish_reason="stop", target=target)


def test_credit_flags_a_different_model_not_a_different_account():
    assert _done(ROLES["writer"][0]).credit()["backup"] is False
    assert _done(Target("openrouter", "anthropic/claude-opus-5.5")).credit()["backup"] is False
    sol = _done(Target("openai", "gpt-6.1-sol")).credit()
    assert sol == {"model": "gpt-6.1-sol", "route": "openai",
                   "primary": "claude-opus-5-5", "backup": True}


def _ep(**kw):
    base = dict(title="Daily News Briefing - 2026-10-10", author="", feed_name="Daily News Briefing",
                link="", audio_url="https://f/a.mp3", duration_seconds=300, is_briefing=True,
                bullets=["Something happened"])
    return ReportEpisode(**(base | kw))


def test_email_says_quietly_who_wrote_the_briefing():
    writer = {"model": "claude-opus-5-5", "route": "anthropic",
              "primary": "claude-opus-5-5", "backup": False}
    report = RunReport(episodes=[_ep(writer=writer)])
    html = build_html(report, datetime(2026, 10, 10))
    assert "Written by Claude Opus 5.5" in html and "backup" not in html
    assert "(Written by Claude Opus 5.5)" in build_text(report, datetime(2026, 10, 10))


def test_email_flags_a_backup_writer():
    writer = {"model": "gpt-6.1-sol", "route": "openai",
              "primary": "claude-opus-5-5", "backup": True}
    line, backup = writer_line(writer)
    assert line == "Written by GPT-6.1 Sol (backup: Claude Opus 5.5 was unavailable)"
    assert backup
    html = build_html(RunReport(episodes=[_ep(writer=writer)]), datetime(2026, 10, 10))
    assert line in html and "#9a5b00" in html


def test_no_line_when_no_model_wrote_it():
    assert writer_line(None) == ("", False)
    assert "Written by" not in build_html(RunReport(episodes=[_ep()]), datetime(2026, 10, 10))


def test_the_writer_survives_the_database_into_the_report(tmp_path):
    monitor = FeedMonitor(tmp_path / "posts.db")
    writer = {"model": "gpt-6.1-sol", "route": "openai",
              "primary": "claude-opus-5-5", "backup": True}
    entry = FeedEntry(id="news-briefing-2026-10-10", title="Daily News Briefing - 2026-10-10",
                      link="", content="Today.", published=datetime(2026, 10, 10, 5),
                      author="Feedcast Bot", feed_name="Daily News Briefing", writer=writer)
    monitor.mark_processed(entry, "b.mp3", content="Today.")
    episode = Episode(id=entry.id, title=entry.title, description="", audio_file="b.mp3",
                      published=entry.published, duration_seconds=300)
    report = _build_run_report([episode], monitor.get_processed_entries(), {entry.id}, [],
                               "https://f")
    assert report.episodes[0].writer == writer


def test_summary_and_briefing_record_their_writer(routes):
    from src.news import NewsAggregator
    from src.processor import ContentProcessor

    routes["openai"] = FakeApi(["A summary.", "A briefing."])  # Claude accounts unset
    entry = FeedEntry(id="p", title="Post", link="https://e.com/p", content="<p>Body text.</p>",
                      published=datetime(2026, 10, 10), author="Zvi", feed_name="Zvi")
    asyncio.run(ContentProcessor("Summarise.", verify=False).summarize(entry))
    assert entry.writer["model"] == "gpt-6.1-sol" and entry.writer["backup"] is True

    agg = NewsAggregator(sources=[], prompt="Brief.", verify=False)
    asyncio.run(agg.synthesize_briefing("articles"))
    assert agg.last_writer["model"] == "gpt-6.1-sol"
