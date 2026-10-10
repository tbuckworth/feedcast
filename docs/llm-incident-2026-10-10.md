# OpenRouter out of credit on 2026-10-10

[Run 38024278561](https://github.com/tbuckworth/feedcast/actions/runs/38024278561)
(desktop cron dispatch, 04:30 UTC) was green, but nothing was published. All
three entries failed at TTS normalisation, on both passes:

- Daily News Briefing - 2026-10-10 (first pass)
- "New Math from OpenAI" by Zvi (first pass; queued in `failed_entries`)
- Your Book Review: We Present Television (narrate pass; still in `deferred_entries`)

Every failure was the same error from OpenRouter:

```
APIStatusError: Error code: 402 - Insufficient credits. Add more using
https://openrouter.ai/settings/credits  (limit_source: openrouter_credits)
```

OpenRouter's `/credits` endpoint showed the Arrow account at 68,611 used of
68,600 credits. The key's own monthly limit was not the problem.

The writer (Opus 5.5) and checker (Sonnet 5) run on Anthropic direct and
worked. The bullets (GPT-5.6 Sol) run on OpenAI direct and worked. Only the
normaliser (Gemini 3 Flash) had OpenRouter as its sole route. It also called
OpenRouter directly instead of going through `llm.complete()`, so it had no
fallback at all. Branch `fix-llm-fallback-403-credit` had already been merged
as PR #49 (writer and checker backups). It never touched the normaliser.
TTS (DeepInfra, PR #52) was never reached and was not involved.

## Fix

- The normaliser goes through `complete("normalizer")`: Gemini 3 Flash via
  OpenRouter, then Claude Haiku 5.5 direct, then GPT-6.1 Sol direct.
- An account-level refusal (out of credit, quota, a bad key) marks the route
  dead for the run, so later calls skip it without failing first.
- The writer's non-Claude backup is now GPT-6.1 Sol at effort low. It rejects
  `reasoning_effort: none`, hence `Target.min_effort`.
- The email says which model wrote each script and flags a backup.

Live check on 2026-10-10 with the real keys (`scripts/check_llm.py`): with
OpenRouter at 402, Haiku 5.5 normalised. With Anthropic also withheld, GPT-6.1
Sol selected stories, wrote the briefing, checked it and normalised it.
