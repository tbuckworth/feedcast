"""One text published twice: Scott Alexander's LessWrong crossposts of ACX posts.

A crosspost carries a new guid, a new link and sometimes a new title, so only
its text shows it is the post already narrated from Astral Codex Ten.
"""

import random
from datetime import datetime, timedelta, timezone

from src.config import load_config
from src.duplicates import same_text, word_runs
from src.main import Run, RunOptions, _take_newest
from src.monitor import FeedEntry, FeedMonitor

_WORDS = ("alignment pause labs incentives forecast treaty model safety compute evidence "
          "argument policy world probability research risk plan awareness strategy "
          "governance capability timeline humans critics people isn't scott's").split()


def _prose(seed: int, paragraphs: int) -> list[str]:
    """Paragraphs of distinct pseudo-sentences, reproducible from `seed`."""
    rng = random.Random(seed)
    return [" ".join(" ".join(rng.choice(_WORDS) for _ in range(14)).capitalize() + "."
                     for _ in range(5)) for _ in range(paragraphs)]


ORIGINAL = _prose(1, 30)
ACX_HTML = "".join(f"<p>{p}</p>" for p in ORIGINAL)
# LessWrong's copy: a preface, other markup, curly apostrophes for straight ones.
LW_HTML = ("<p><i>This post originally posted on Astral Codex Ten.</i></p>"
           + "".join(f"<div><span>{p.replace(chr(39), chr(0x2019))}</span></div>"
                     for p in ORIGINAL))


def _xml(guid: str, title: str, link: str, html: str, when: datetime) -> str:
    return ("<?xml version='1.0'?><rss version='2.0'><channel><title>f</title>"
            f"<item><title>{title}</title><link>{link}</link><guid>{guid}</guid>"
            f"<description><![CDATA[{html}]]></description>"
            f"<pubDate>{when.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>"
            "</item></channel></rss>")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TestSameText:

    def test_a_crosspost_with_a_preface_and_other_markup_is_the_same_text(self):
        assert same_text(word_runs(ACX_HTML), word_runs(LW_HTML))

    def test_curly_and_straight_apostrophes_match(self):
        assert "'" in ACX_HTML
        assert word_runs(ACX_HTML) == word_runs(ACX_HTML.replace("'", "’"))

    def test_a_reply_quoting_a_third_of_the_post_is_not_the_same_text(self):
        reply = "".join(f"<blockquote>{p}</blockquote>" for p in ORIGINAL[:10]) + \
            "".join(f"<p>{p}</p>" for p in _prose(2, 20))
        assert not same_text(word_runs(reply), word_runs(ACX_HTML))

    def test_a_short_post_quoted_whole_in_a_long_one_is_not_the_same_text(self):
        short = "".join(f"<p>{p}</p>" for p in ORIGINAL[:3])
        assert not same_text(word_runs(short), word_runs(ACX_HTML))
        assert not same_text(word_runs(ACX_HTML), word_runs(short))

    def test_different_posts_are_not_the_same_text(self):
        other = "".join(f"<p>{p}</p>" for p in _prose(3, 30))
        assert not same_text(word_runs(other), word_runs(ACX_HTML))

    def test_text_too_short_to_compare_matches_nothing(self):
        assert word_runs("<p>Open thread.</p>") == frozenset()
        assert not same_text(frozenset(), frozenset())


class TestFetchSkipsCopies:

    def _narrate_acx(self, m: FeedMonitor) -> None:
        acx = m.fetch_feed(_xml("acx-1", "Against Something",
                                "https://www.astralcodexten.com/p/against-something",
                                ACX_HTML, _now() - timedelta(hours=30)),
                           "Scott Alexander", max_age_hours=48)
        assert len(acx) == 1
        m.mark_processed(acx[0], audio_file="a.mp3", content=acx[0].content)

    def _fetch_lw(self, m: FeedMonitor, html: str) -> list[FeedEntry]:
        return m.fetch_feed(_xml("Sfkv6JF2ozmAkggKu", "[Crosspost] Against Something",
                                 "https://www.lesswrong.com/posts/Sfkv6JF2ozmAkggKu/x",
                                 html, _now() - timedelta(hours=2)),
                            "Scott Alexander (LessWrong)", max_age_hours=48)

    def test_a_crosspost_of_a_narrated_post_is_skipped(self, tmp_path, capsys):
        m = FeedMonitor(tmp_path / "posts.db")
        self._narrate_acx(m)
        assert self._fetch_lw(m, LW_HTML) == []
        assert "the same text as Against Something" in capsys.readouterr().out

    def test_a_new_post_on_the_same_feed_is_kept(self, tmp_path):
        m = FeedMonitor(tmp_path / "posts.db")
        self._narrate_acx(m)
        assert len(self._fetch_lw(m, "".join(f"<p>{p}</p>" for p in _prose(4, 30)))) == 1

    def test_a_crosspost_of_a_post_waiting_for_narration_is_skipped(self, tmp_path):
        m = FeedMonitor(tmp_path / "posts.db")
        acx = m.fetch_feed(_xml("acx-1", "Against Something",
                                "https://www.astralcodexten.com/p/against-something",
                                ACX_HTML, _now() - timedelta(hours=30)),
                           "Scott Alexander", max_age_hours=48)
        m.defer_entry(acx[0], "verbatim", "script", None, [])
        assert self._fetch_lw(m, LW_HTML) == []


class TestOneRunTakesOneCopy:

    def test_the_first_feed_keeps_a_post_that_two_feeds_carry_on_the_same_day(self, tmp_path):
        config = load_config()
        acx_feed, lw_feed = (next(f for f in config.feeds if f.name == name)
                             for name in ("Scott Alexander", "Scott Alexander (LessWrong)"))
        run = Run(options=RunOptions.from_env(), config=config, root=tmp_path,
                  monitor=FeedMonitor(tmp_path / "posts.db"))

        def entry(guid: str, link: str, html: str, feed: str) -> FeedEntry:
            return FeedEntry(id=guid, title="Against Something", link=link, content=html,
                             published=_now(), author="Scott Alexander", feed_name=feed)

        _take_newest(run, [
            (acx_feed, [entry("acx-1", "https://www.astralcodexten.com/p/a", ACX_HTML,
                              acx_feed.name)]),
            (lw_feed, [entry("lw-1", "https://www.lesswrong.com/posts/lw-1/a", LW_HTML,
                             lw_feed.name)]),
        ])
        assert [e.id for e, _mode, _prompt in run.entries] == ["acx-1"]
