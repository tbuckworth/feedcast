"""Where long text is cut: TTS chunks, and the normaliser's pieces and batches.

The pins below were taken from the code as it stood before the sentence
splitting in audio.py and normalizer.py was merged into one helper
(2026-10-30). A chunk boundary decides where the voice pauses, so a refactor
that moves one changes the episode.
"""

import asyncio
from types import SimpleNamespace as NS

from src.audio import split_into_chunks
from src.normalizer import MAX_BATCH_CHARS, TextNormalizer

# A narrated script as it reaches TTS: normalised, so numbers are words. It has
# what real posts have: short and long paragraphs, questions, quotations, an
# abbreviation that ends a "sentence" early, and sentences longer than a chunk,
# with commas to break them at.
SCRIPT = """\
Book Review: The Housing Theory of Everything. By Scott Alexander. Published October fourth, twenty twenty-six.

Everyone agrees that housing is expensive. Fewer people agree on why, and fewer still agree on what to do about it. The book under review makes the strongest claim I have seen: that expensive housing is not one problem among many, but the root of most of the others, from low fertility to political polarisation to the slow decline of the high street.

Is that plausible? Let me start with the part I find convincing. When rents in a city rise faster than wages, people who would have moved there for a better job stay where they are, and the economy as a whole loses the output they would have produced. Economists have tried to estimate this loss, e.g. Hsieh and Moretti, who put it at something like a third of all growth between nineteen sixty-four and two thousand nine, a number large enough that even if it is wrong by half it would still be one of the most important facts about the modern economy.

The authors go further. They argue that because so much household wealth is tied up in a single asset, homeowners become a voting bloc whose interests run directly against those of renters, the young, and anyone who has not yet bought, and that this bloc, organised through local planning committees, objections to new developments, heritage listings, height limits, parking minimums, and a hundred other small vetoes that no one of them seems important on its own, has quietly decided the shape of every city in the country for the last fifty years.

"The planning system," they write, "is a machine for turning the preferences of people who already live somewhere into a tax on everyone who might want to." I like this line. I am less sure it is true.

Here is my worry. If housing explains everything, it should explain things that happened before housing got expensive, and it should fail to explain things in places where housing is cheap. The authors mostly do not check. Japan, for instance, built a great deal of housing in Tokyo and kept prices flat, yet its fertility rate is lower than ours! A theory of everything that cannot survive one counterexample is a theory of something.

Still, the policy recommendations hold up even if the grand theory does not. Build more homes where people want to live. Let landowners build upwards. Replace discretionary planning decisions with clear rules that say what may be built, so that a developer who follows them knows the answer in advance, the neighbours know what to expect, and the council cannot be lobbied into saying no to a project it would have approved anywhere else.

Would that work? Probably, at least partly. Auckland upzoned most of its residential land in twenty sixteen, and building consents roughly doubled over the following five years, while rents rose more slowly than in the rest of New Zealand. That is one city, and cities differ, but it is the kind of evidence the book could have leaned on far more than it does.

So: a good book with a bad title. Read it for the chapters on planning, skim the chapters on everything else, and do not let anyone tell you that one policy will fix fertility, loneliness and the price of coffee all at once.
"""

# (length, last 30 characters) of each chunk, from the code before the merge.
PINNED_TTS_CHUNKS = [
    (482, "igh street. Is that plausible?"),
    (282, "ed to estimate this loss, e.g."),
    (275, "onomy. The authors go further."),
    # The one sentence over 500 characters starts a chunk and is broken at a comma.
    (441, "em seems important on its own,"),
    (476, "places where housing is cheap."),
    (396, " Let landowners build upwards."),
    (331, "rk? Probably, at least partly."),
    (350, " a good book with a bad title."),
    (190, "e price of coffee all at once."),
]
PINNED_NORMALISER_PIECES = [
    (17948, " it is true. Here is my worry."),
    (17830, " agree on what to do about it."),
    (3003, "e price of coffee all at once."),
]
PINNED_NORMALISER_BATCHES = [17979, 17781, 3126]


def test_tts_chunk_boundaries_are_pinned():
    chunks = split_into_chunks(SCRIPT)
    assert [(len(c), c[-30:]) for c in chunks] == PINNED_TTS_CHUNKS
    assert " ".join(chunks).split() == SCRIPT.split()


def test_a_clause_too_long_for_a_chunk_keeps_its_place():
    # A sentence over the limit is broken at its commas, and a clause still
    # over it is cut where it stands. Such a clause used to come out ahead of
    # the clauses before it, so the voice read the sentence out of order.
    clause = " ".join(["word"] * 130)          # 649 characters, no comma
    text = f"First, {clause}, last."
    chunks = split_into_chunks(text)
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def _echoing_normaliser():
    """A normaliser whose model hands back what it was sent, recording each request.

    The model API is the boundary faked here: a pinned client.
    """
    n = TextNormalizer()
    sent: list[str] = []

    async def create(**kw):
        text = kw["messages"][1]["content"]
        sent.append(text)
        return NS(choices=[NS(message=NS(content=text, refusal=None), finish_reason="stop")])

    n.client = NS(chat=NS(completions=NS(create=create)))
    return n, sent


def test_normaliser_pieces_of_one_long_paragraph_are_pinned():
    # ACX's single-newline prose reaches the normaliser as one paragraph.
    paragraph = (SCRIPT.replace("\n\n", "\n").strip() + "\n") * 12
    assert len(paragraph) > 2 * MAX_BATCH_CHARS
    pieces = TextNormalizer._split_oversized(paragraph)
    assert [(len(p), p[-30:]) for p in pieces] == PINNED_NORMALISER_PIECES


def test_normaliser_batches_are_pinned():
    text = "\n\n".join([SCRIPT.strip()] * 12)
    n, sent = _echoing_normaliser()
    assert asyncio.run(n.normalize_for_tts(text, label="ep")) == text
    assert [len(batch) for batch in sent] == PINNED_NORMALISER_BATCHES
