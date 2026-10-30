# Agent instructions

The instructions every coding agent in this repository follows. Codex reads this file directly; Claude Code reads it through the `@AGENTS.md` line in `CLAUDE.md`. Write rules that apply to both here, and keep Claude-only material in `CLAUDE.md`.

Feedcast turns RSS feeds and a daily news briefing into a narrated podcast, published on GitHub Pages, and emails a report of each run. GitHub Actions runs it daily from `main`. [README.md](README.md) is the usage guide: setup, commands, environment variables, configuration and CI dispatch inputs.

## Rules

- Before running the pipeline locally, run `scripts/state.sh pull`. The database (`data/posts.db`) and the MP3s (`data/audio/`) are gitignored on `main` and live on the orphan `state` branch; without them a run starts from an empty database. Run `scripts/state.sh push` only to publish a run's results, since it replaces that branch. CI does both.
- Nothing loads a `.env` file: the code reads its API keys from the environment. On the desktop, run anything that calls a model or DeepInfra under `bwsrun`, which supplies the keys `.bws-profile` names (`bwsrun uv run python -m scripts.check_llm`).
- Run the tests with `uv run --extra dev python -m pytest -q tests`. Some tests read `config.yaml` and the workflows.
- Refer to a model by its role (writer, checker, bullets, normalizer). `ROLES` in `src/llm.py` assigns the models, and that module's docstring says why each was chosen.
- List author feeds before aggregate feeds in `config.yaml`: deduplication keeps the copy from the first feed, and with it the author.
- When `_PATTERNS` in `src/mathiness.py` changes, recalibrate `maths_filter.threshold_per_1k` in `config.yaml`; the two are coupled.
- Measure a new `pronunciations` entry with `scripts/pronunciation_check.py` before adding it to `config.yaml`.

## Repo map

- `src/`: the pipeline package; its `__init__.py` docstring lists the modules.
- `tests/`: the pytest suite.
- `scripts/`: developer tools and CI steps (entry points below).
- `.github/`: the daily workflow, the Pages publish workflow and the setup action the Python jobs share.
- `config.yaml`: every pipeline setting; the schema is `src/config.py`.
- `data/`: `posts.db` and `audio/` (from the `state` branch), and `sources/`, one Markdown file per written episode recording what the writer model saw and wrote (`src/bundle.py`).
- `output/`: the GitHub Pages site. The pipeline writes `feed.xml`, `index.html`, `episodes/` and `transcripts/`; `app/` is the Android share-target web app.
- `docs/`: dated incident and model-test reports.
- `voice_samples/`: the recording the narrating voice is cloned from.
- `worker/`: the Cloudflare Worker that turns an authenticated "send this URL" request into a workflow dispatch.
- `chrome-extension/`: the browser extension that sends the current page to the Worker.
- `.claude/`, `.codex/`: the checklist review gate's configuration and reviewer definitions.

Entry points:

- `uv run python -m src.main` (`src/main.py`): one run of the pipeline; environment variables choose the kind of run.
- `.github/workflows/update-feed.yml`: the daily run and every manual dispatch.
- `.github/workflows/publish-pages.yml`: deploys `output/` to GitHub Pages; called by `update-feed.yml`.
- `scripts/state.sh pull|push`: restore or replace the database and MP3s on the `state` branch.
- `scripts/check_llm.py` (`python -m scripts.check_llm`): a short live call through each LLM role.
- `scripts/model_upgrade_test.py`: replays a saved writer bundle through candidate model setups and meters each call.
- `scripts/pronunciation_check.py`: measures how the cloned voice says a word.
- `scripts/cron-backstop.sh`: run by the desktop crontab; dispatches the daily run when no run exists for the UTC day.
- `scripts/ci-commit-and-push.sh`: commits a pass's results to `main` and the database and MP3s to `state`.
- `scripts/ci-install-ffmpeg.sh`: installs ffmpeg on a runner, with timeouts and retries.
- `scripts/publish-audio.sh`: copies the MP3s into the site and fails if `feed.xml` lists one that is missing.
- `worker/src/index.ts`: the Worker, deployed with `npx wrangler deploy`.

## How a run works

`src/main.py` runs the pipeline in three phases:

1. **Collect.** Fetch every feed in `config.yaml` in parallel and take each feed's newest unseen entry within `max_age_hours`, deduplicating by id and by link in config order. Add the entries that failed on earlier runs (table `failed_entries`, found again with the age cutoff off, up to `FeedMonitor.MAX_ATTEMPTS` attempts) and write the day's news briefing (`src/news.py`). Then link rather than narrate posts too mathematical to follow by ear (`src/mathiness.py`), and replace excerpt-only feed bodies with the full post (`src/fulltext.py`). An injected URL (`INJECT_URL`) replaces this phase with one page extracted from the web.
2. **Make episodes,** concurrently. The writer role summarises a post and the checker role reads the summary against its source (`src/verify.py`), or the post is cleaned to be read in full. The normalizer role then rewrites the script for speech, and DeepInfra's Chatterbox text-to-speech model narrates it in chunks that ffmpeg joins into an MP3. Meanwhile the bullets role digests the script for the email. An entry that fails is retried once, serially, from the stage that failed; if it fails again, a feed entry is queued in `failed_entries`.
3. **Publish.** Record the episodes in `data/posts.db`, delete episodes older than `retention_days` with their audio, transcripts and source records, write `output/`, push an injection's outcome to ntfy.sh, and email the run report.

`FEEDCAST_PASS` splits a run into two publishes, so that a long reading cannot delay the briefing and the summaries. `first` publishes the briefing and the summaries and sends the email; posts read out in full (`ContentProcessor.reads_verbatim`) are only cleaned and digested, listed in the email with a link to their episode page, and parked in table `deferred_entries`. `narrate` narrates the parked posts and publishes again, emailing only `FEEDCAST_EMAIL_TO` and only on failure. Unset, everything runs in one pass; inject and reprocess runs always do.

In CI, `update-feed.yml` runs daily at 03:43 UTC. `guard` stops the run if another run that UTC day has already published, unless the workflow's `ON_DEMAND` expression marks it as requested by hand. `update` runs the first pass and commits (`scripts/ci-commit-and-push.sh`), `deploy` publishes `output/` to GitHub Pages, `narrate` runs the narration pass when the first pass parked anything, and `deploy-narrated` publishes again. Both deploys call `publish-pages.yml`, which waits for the live feed to match the commit and then pings the feed's WebSub hub. The jobs that run Python (`update`, `narrate`, `check-llm`) set up through `.github/actions/setup-pipeline`. A report email that was not sent, or a failed narration, fails its job after the commit, so the run publishes but does not end green.

<!-- claude-tooling: codex checklist review -->
## Checklist review (Codex)

This repository runs one checklist review gate for Claude Code and Codex. The configuration
and the review chain live under `.claude/`; the Codex wiring is `.codex/hooks.json`, and the
reviewer is the `checklist-reviewer` subagent role in `.codex/agents/checklist-reviewer.toml`,
which pins its model. Claude Code reads this section too, through `CLAUDE.md`, but runs its
reviewer as the gate's block message says; the steps below are for Codex sessions.

- Codex runs only trusted project hooks and skips an untrusted one without a word, so until
  `.codex/hooks.json` is trusted in `/hooks` (again after any change to it) there is no gate.
  A commit that goes through with no review is the sign; check `/hooks`.
- When the gate blocks a command, spawn the reviewer it asks for: `spawn_agent` with
  `agent_type="checklist-reviewer"`, `fork_turns="none"` and no model override, with the
  gate's prompt as the message. The reviewer must not see the conversation that wrote the
  diff, and a hook refuses any other spawn of it. On a retry, send the new prompt to the same
  reviewer with `followup_task`, or spawn a fresh one if it is gone.
- To review before a gate asks, run `.venv/bin/claude-tooling review-prompt` (or use
  `$checklist-review`) and pass its output to a fresh reviewer the same way.
- Never write `.claude/reviews/` yourself: only the reviewer writes `verdict.json`, with
  `apply_patch`, and hooks refuse every other write there, from `apply_patch` or the shell.
  Reading it is allowed.
- A verdict is valid for exactly one diff hash. After fixing findings, re-stage (commit
  trigger) or commit (PR trigger) and run one new review; then retry the gated command. A
  commit that fails after the gate allowed it is retried with the same verdict.
- Under the commit trigger the review covers exactly the staged diff, so stage with
  `git add <paths>` in its own command and run a plain `git commit -m "…"`. The gate refuses
  `-a`, paths on the command line, `--only`, `--include`, `--pathspec-from-file`, `--patch`
  and `--interactive`, and any commit whose options it cannot parse.
- Run the commit as a command of its own, after any staging: the gate reads the staged diff
  before the command runs, so it refuses a commit that shares the command with anything that
  might change the index before or alongside it. Only navigation and read-only checks (`cd`,
  `git status`) may come first, and only a filter such as `tail` may take its output; the
  refusal lists what is allowed.
- Write a plain `git commit`, not one behind `eval`, `sh -c` text built from variables,
  `xargs` or a wrapper such as `timeout`: the gate refuses a commit it cannot read.
- Do not bypass the gate or treat a failing item as advisory.
<!-- /claude-tooling: codex checklist review -->
