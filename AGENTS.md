# Agent instructions

The instructions every coding agent in this repository follows. Codex reads this file directly; Claude Code reads it through the `@AGENTS.md` line in `CLAUDE.md`. Write rules that apply to both here, and keep Claude-only material in `CLAUDE.md`.

[README.md](README.md) says what Feedcast does and how to use it: setup, commands, environment variables, configuration and CI.

## Rules

- Before running the pipeline locally, run `scripts/state.sh pull`. The database (`data/posts.db`) and the MP3s (`data/audio/`) are gitignored on `main` and live on the orphan `state` branch; without them a run starts from an empty database. Run `scripts/state.sh push` only to publish a run's results, since it replaces that branch. CI does both.
- Nothing loads a `.env` file: the code reads its API keys from the environment. On the desktop, run anything that calls a model or DeepInfra under `bwsrun`, which supplies the keys `.bws-profile` names (`bwsrun uv run python -m scripts.check_llm`).
- Run the tests with `uv run --extra dev python -m pytest -q tests`. Some tests read `config.yaml` and the workflows.
- Refer to a model by its role (writer, checker, bullets, normalizer). `ROLES` in `src/llm.py` assigns the models, and that module's docstring says why each was chosen.
- List author feeds before aggregate feeds in `config.yaml`: deduplication keeps the copy from the first feed, and with it the author.
- When `_PATTERNS` in `src/mathiness.py` changes, recalibrate `maths_filter.threshold_per_1k` in `config.yaml`; the two are coupled.
- Measure a new `pronunciations` entry with `scripts/pronunciation_check.py` before adding it to `config.yaml`.
- The daily email goes out before the audio is published, and must stay that way: getting the email out is the priority, and narration and publishing take longer. Until the publish lands, the email's audio links may 404; that is accepted. When a publish fails, recover it, but do not propose holding the email until the site is live (Titus decided this on 2026-10-31).

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

The `src/__init__.py` docstring describes a run's phases and its two publishes. README's CI section describes the schedule and the guard, and the comments in `.github/workflows/update-feed.yml` describe its jobs.

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
