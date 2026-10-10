# Normaliser: Gemini 3 Flash or Claude Haiku 5.5? (2026-10-10)

After OpenRouter ran out of credit (docs/llm-incident-2026-10-10.md), Haiku 5.5
normalised that day's episodes as the backup, and Titus asked whether it should
be the primary. It should not. Gemini 3 Flash stays first and Haiku stays its
backup. The tests also produced a better prompt and two guards.

## Test set

Twelve real normaliser inputs, each one batch (at most 18,000 chars):

- three briefings (10 Oct, 7 Oct, 2 Oct);
- three Zvi summaries;
- the most number-heavy batch of five posts read in full: ACX "We Present Television",
  "This Is Going To Hurt" and "Does Georgism Work?", and LessWrong "An
  operationalization of opaque serial depth" and "What's the date?";
- the synthetic cases from `scripts/test_normalization.py`.

Each case ran twice per model, with the production request. Gemini ran on the
`OPENROUTER_API_KEY__FEEDCAST` account, since the Arrow one is out of credit.

## Mechanical scores (24 calls each)

"Unasked edits" counts words changed where there was nothing to convert:
contractions expanded, acronyms spelled out, words dropped or added.

| | unasked edits / 1k words | digits left | median s | $ / call |
|---|---|---|---|---|
| Gemini, old prompt | 31.5 | 6 | 5.2 | 0.0067 |
| Gemini, new prompt | 10.7 | 2 | 4.4 | 0.0066 |
| Haiku, old prompt | 1.6 | 143 | 7.0 | 0.0023 |
| Haiku, new prompt | 0.9 | 105 (100 are one 100-digit number) | 6.8 | 0.0025 |
| Haiku at effort low, old prompt | 10.3 | 271 | 4.1 | 0.0018 |

On a full 18,000-char batch, Gemini takes ~16s and Haiku 22-33s.

Haiku 5.5 thinks by default: 1,000-2,400 hidden tokens a batch. Its tokenizer
also counts ~1.5x Gemini's. A dense batch reached 10,008 output tokens against
the old 12,000 ceiling, so `MAX_OUTPUT_TOKENS` is now 32,000.

At effort low Haiku is faster, but it leaves years and figures as digits. It
also refused the "What's the date?" post in prose in both runs, which would
have been read out as the episode.

The normaliser handles about 0.7M chars a month. That costs ~$0.52 on Gemini
and ~$0.19 on Haiku, so price does not decide this.

## Blind judges

Opus 5.5 and GPT-6.1 Sol judged seven cases: two briefing and summary cases,
the three ACX posts, the technical LessWrong post, and the synthetic set. Each
judge saw the original and two unlabelled outputs, in an order fixed per case
by a hash. The neutral rubric asked for faithful text in which every number,
symbol and code is spoken.

| comparison (neutral rubric) | result |
|---|---|
| Gemini, new prompt vs old prompt | new 11, old 2 (the old won only on the synthetic set) |
| Haiku, new prompt vs old prompt | new 8, old 4, tie 2 |
| **Gemini vs Haiku, both on the new prompt** | **Gemini 8, Haiku 4, tie 2** |
| Gemini on the old prompt (status quo) vs Haiku on the new | Haiku 8, Gemini 5, tie 1 |

The two judges differ consistently. Opus rewards keeping the author's words;
Sol rewards converting more. Haiku keeps prose word for word. Gemini converts
more of what a voice stumbles on: maths notation, slashes, "Catch 22", odd
codes. On the same prompt, that wins.

## Failures found, and what now guards against them

- **The filter.** On every batch of the Tale of Genji review, Gemini blocked
  batch 2 with `PROHIBITED_CONTENT`. It is the same 17,908 chars it blocked on
  2026-09-08. Haiku normalised all four batches. Since PR #57 such a block falls
  through to Haiku, which is why Haiku is the first backup.
- **A fragment marked as an error.** On Genji batch 1, Gemini returned 88% of
  the text with `finish_reason: "error"`. Only `"length"` was checked, so the
  fragment would have been narrated. `llm._completion` now treats `"error"` as
  a failed reply for every role.
- **Text silently lost.** "What's the date?" quotes a model's chain of thought,
  chat-template tokens included. Every model lost text on it in at least one of
  two runs, each time with a clean finish:
  - Gemini kept 68% in one run. In another it answered the question in 56 chars.
  - Haiku kept 30%.

  A normaliser reply shorter than `MIN_KEPT` (85%) of its input now goes to the
  next model; normalising only lengthens text. In the live test, Gemini's 82%
  and Haiku's 32% were rejected and GPT-6.1 Sol read the post whole.
- **The prompt.** Added rules for years, decimals, codes with digits, "et al."
  and footnote markers. Contractions and acronyms are now kept as written, and
  a site named in prose is not treated as a URL. The model is told the text is
  never addressed to it.
