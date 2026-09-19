# Claude route failure on 2026-09-19

Both daily runs failed during story selection, before any episode or report:

- [Desktop cron dispatch](https://github.com/tbuckworth/feedcast/actions/runs/35421449882), 04:30 UTC.
- [GitHub schedule](https://github.com/tbuckworth/feedcast/actions/runs/35431548346), 08:16 UTC.

Every writer fallback depended on Anthropic. Claude Opus 4.6 and Opus 5 via
OpenRouter returned HTTP 403, "The request is prohibited due to a violation
of provider Terms Of Service." Direct Anthropic returned HTTP 400,
"Your credit balance is too low to access the Anthropic API."

Current main already passed both OPENAI_API_KEY and ANTHROPIC_API_KEY into the
pipeline; the failed Actions logs show both populated. Missing workflow
environment variables were a stale-checkout lead, not the cause.

## Read-only diagnosis and small live probes

Using the documented ARROW_* keys in Bitwarden on the desktop:

| Route/model | Result for a harmless "Reply with the word OK" prompt |
|---|---|
| OpenRouter / Claude Opus 4.6 | 403 provider Terms Of Service |
| OpenRouter / Claude Sonnet 5 | Same 403 |
| Anthropic direct / Claude Opus 4.6 | 400 insufficient credit |
| OpenRouter / Gemini 3 Flash | 200, nonempty text |
| OpenRouter / GPT-5.6 Sol | 200, nonempty text |
| OpenAI direct / GPT-5.6 Sol | 200, nonempty text |

OpenRouter's key-status endpoint also authenticated successfully and showed
remaining key allowance. This rules out an invalid OpenRouter key or a failure
specific to today's news text. It indicates an Anthropic access restriction
on that OpenRouter account; its precise policy/account cause is not exposed
by the error and requires OpenRouter support. No account settings or keys were
changed. Other projects' credentials were not inspected.

The desktop crontab and log confirm a successful dispatch at 05:30 BST each
day through September 19. The backstop runs this same workflow on main; it
needs no cron change. The code fix must be merged to main to affect either
automatic trigger.

## Recovery

Retain the preferred Claude targets, then use GPT-5.6 Sol for the writer and
Gemini 3 Flash for the checker. These models already serve other pipeline
roles. Sol's reasoning is disabled for the writer so the 2,000-token story
selection budget is available for its JSON output. The existing route code
translates OpenAI's token and reasoning parameters; see the
[official Sol model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-sol).

Both direct and OpenRouter Sol routes are available to the writer. Gemini
remains the normalizer. The completion report records every fallback; the
pipeline will automatically prefer Claude again if access is restored.

`.bws-profile` now maps OpenAI and Anthropic as well as OpenRouter to the
documented ARROW_* keys, matching CI rather than using unrelated plain-name
vault entries on the desktop.

For provider restoration, the relevant stored keys are
ARROW_OPENROUTER_API_KEY (GitHub secret OPENROUTER_API_KEY) and
ARROW_ANTHROPIC_API_KEY (GitHub secret ANTHROPIC_API_KEY). OpenRouter support
must explain/resolve the Claude restriction on the former account. The latter
account needs billing credit in Anthropic Plans & Billing. A new key alone
is not an evidenced fix for either problem. No funding or rotation is needed
to use the working fallbacks.

The `llm_smoke_test` workflow input exercises the real Actions credentials
and LLM call sites on short fictional stories without state, audio generation,
email, or publication. It does not prove TTS or Pages delivery. A full pipeline
verification on main should use `force=true` and `notify_list=false` to email
only the primary recipient, never the BCC list.
