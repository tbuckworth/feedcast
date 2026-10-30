"""Hand-dispatched runs are dev runs unless the operator opts the list in."""

import os
import re
import subprocess
from itertools import product
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "update-feed.yml"
PUBLISH = WORKFLOW.parent / "publish-pages.yml"
SETUP_ACTION = WORKFLOW.parent.parent / "actions" / "setup-pipeline" / "action.yml"

OPERATOR_INPUTS = ("inputs.entry_url != ''", "inputs.inject_url != ''",
                   "inputs.resend_report == true", "inputs.force == true",
                   "inputs.preview_briefing == true")


def _workflow():
    wf = yaml.safe_load(WORKFLOW.read_text())
    # PyYAML reads the bare key `on` as the boolean True.
    return wf, (wf.get("on") or wf.get(True))


def _step(job: dict, name: str) -> dict:
    (step,) = [s for s in job["steps"] if s.get("name") == name]
    return step


_TOKEN = re.compile(r"\s*(!cancelled\(\)|'[^']*'|==|!=|&&|\|\||[()]|[\w.-]+)")


def _decide(condition: str, values: dict, cancelled: bool = False) -> bool:
    """Evaluate a job's `if:` the way GitHub would, for the contexts in `values`.

    Covers what these conditions use: quoted strings, true/false, ==, !=, &&,
    ||, brackets and !cancelled(). Anything else fails the test rather than
    being guessed at.
    """
    body = condition.strip()
    assert body.startswith("${{") and body.endswith("}}"), condition
    body = body[3:-2].strip()
    # Without a status function GitHub silently adds success(), which would
    # skip the job whenever a job it needs failed.
    assert "!cancelled()" in body, condition
    words = {"&&": "and", "||": "or", "==": "==", "!=": "!=", "(": "(", ")": ")",
             "true": "True", "false": "False", "!cancelled()": str(not cancelled)}
    python, pos = [], 0
    while pos < len(body):
        match = _TOKEN.match(body, pos)
        assert match, f"cannot read {body[pos:]!r}"
        token, pos = match.group(1), match.end()
        python.append(words.get(token) or (token if token.startswith("'")
                                           else repr(values[token])))
    return eval(" ".join(python), {"__builtins__": {}})


def test_notify_list_replaces_the_opt_in_test_run():
    _, on = _workflow()
    inputs = on["workflow_dispatch"]["inputs"]
    assert "notify_list" in inputs and inputs["notify_list"]["default"] is False
    assert "test_run" not in inputs


def test_dev_mode_is_the_default_for_every_operator_input():
    wf, _ = _workflow()
    on_demand = wf["env"]["ON_DEMAND"]
    text = WORKFLOW.read_text()
    for operator_input in OPERATOR_INPUTS:
        assert operator_input in on_demand, operator_input
        # Written once: the guard and both pipeline passes read ON_DEMAND.
        assert text.count(operator_input) == 1, operator_input
    # notify_list must not make a bare dispatch skip the daily guard.
    assert "notify_list" not in on_demand and "test_run" not in on_demand
    guard = wf["jobs"]["guard"]["steps"][0]
    assert "ON_DEMAND" not in guard.get("env", {}) and '"$ON_DEMAND"' in guard["run"]
    for job, name in (("update", "Run pipeline"), ("narrate", "Narrate deferred posts")):
        assert _step(wf["jobs"][job], name)["env"]["FEEDCAST_TEST_RUN"] == \
            "${{ env.ON_DEMAND == 'true' && inputs.notify_list != true }}", job


def test_deploy_pings_the_websub_hub_after_pages_is_live():
    """Pocket Casts polls a small feed only every few hours; the hub ping is
    what makes new episodes appear in the app minutes after the email."""
    wf, _ = _workflow()
    assert wf["jobs"]["deploy"]["uses"] == "./.github/workflows/publish-pages.yml"
    publish = yaml.safe_load(PUBLISH.read_text())["jobs"]["publish"]
    names = [s.get("name") for s in publish["steps"]]
    assert names.index("Notify the WebSub hub") > names.index("Deploy to GitHub Pages")
    ping = _step(publish, "Notify the WebSub hub")
    # The feed's address comes from feed.xml itself, not a second copy here.
    assert "FEED_URL" not in ping.get("env", {})
    # Must wait for the CDN to serve this run's feed before the hub fetches it.
    assert "sha256sum output/feed.xml" in ping["run"]
    assert "hub.mode=publish" in ping["run"]


def _ping_hub(tmp_path, channel_links: str):
    """Run the WebSub step against a feed.xml with these <atom:link>s, with a
    stand-in curl that serves that feed back and answers the hub with 204."""
    ping = _step(yaml.safe_load(PUBLISH.read_text())["jobs"]["publish"], "Notify the WebSub hub")
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "feed.xml").write_text(
        '<?xml version="1.0"?><rss xmlns:atom="http://www.w3.org/2005/Atom">'
        f"<channel>{channel_links}</channel></rss>")
    bin_dir, log = tmp_path / "bin", tmp_path / "curl.log"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{log}'\n"
        'if [[ " $* " == *" POST "* ]]; then printf 204; else cat output/feed.xml; fi\n')
    curl.chmod(0o755)
    env = {**os.environ, **ping.get("env", {}), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    # GitHub runs a `run:` with no `shell:` as `bash -e`.
    run = subprocess.run(["bash", "-e", "-c", ping["run"]], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=60)
    return run, (log.read_text() if log.exists() else "")


def test_hub_is_told_the_url_the_feed_names_itself_by(tmp_path):
    run, calls = _ping_hub(
        tmp_path, '<atom:link href="https://example.org/pod/feed.xml" rel="self" '
                  'type="application/rss+xml" /><atom:link href="https://hub.example/" rel="hub" />')
    assert run.returncode == 0, run.stdout + run.stderr
    fetch, post = calls.splitlines()
    assert "https://example.org/pod/feed.xml" in fetch
    assert "https://hub.example/" in post and "hub.url=https://example.org/pod/feed.xml" in post


def test_hub_step_has_nothing_to_do_for_a_feed_without_a_hub(tmp_path):
    """podcast.hub_url is optional; with none, feed.xml names no hub."""
    run, calls = _ping_hub(tmp_path, '<atom:link href="https://example.org/pod/feed.xml" '
                                     'rel="self" type="application/rss+xml" />')
    assert run.returncode == 0, run.stdout + run.stderr
    assert "nothing to notify" in run.stdout and calls == ""


def test_hub_step_fails_when_the_feed_has_no_self_link(tmp_path):
    run, calls = _ping_hub(tmp_path, '<atom:link href="https://hub.example/" rel="hub" />')
    assert run.returncode != 0
    assert "::error::" in run.stdout and 'rel="self"' in run.stdout
    assert "POST" not in calls


def test_llm_smoke_test_cannot_enter_the_publishing_jobs_or_send_mail():
    wf, on = _workflow()
    assert on["workflow_dispatch"]["inputs"]["llm_smoke_test"]["default"] is False
    assert wf["jobs"]["check-llm"]["if"] == "inputs.llm_smoke_test == true"
    assert wf["jobs"]["guard"]["if"] == "inputs.llm_smoke_test != true"
    assert wf["jobs"]["update"]["needs"] == "guard"
    assert wf["jobs"]["deploy"]["needs"] == "update"
    smoke = wf["jobs"]["check-llm"]
    assert smoke["permissions"] == {"contents": "read"}
    check = _step(smoke, "Check live LLM routes")
    pipeline = _step(wf["jobs"]["update"], "Run pipeline")
    assert set(check["env"]) == {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
    assert all(value == pipeline["env"][key] for key, value in check["env"].items())
    assert check["run"] == "uv run python -m scripts.check_llm"


def test_verbatim_posts_are_narrated_and_published_after_the_first_deploy():
    """The briefing and summaries publish first; a long post read out in full
    can no longer hold them back or take them down (2026-09-26)."""
    wf, _ = _workflow()
    jobs = wf["jobs"]
    first = _step(jobs["update"], "Run pipeline")
    assert first["env"]["FEEDCAST_PASS"] == "first" and first["id"] == "pipeline"
    assert jobs["update"]["outputs"]["deferred"] == "${{ steps.pipeline.outputs.deferred }}"

    narrate = jobs["narrate"]
    assert narrate["needs"] == "update" and "needs.update.outputs.deferred != '0'" in narrate["if"]
    names = [s.get("name") for s in narrate["steps"]]
    step = _step(narrate, "Narrate deferred posts")
    assert step["env"]["FEEDCAST_PASS"] == "narrate"
    # A failed or timed-out narration must still commit its attempt count...
    assert step["continue-on-error"] is True
    assert names.index("Commit and push") > names.index("Narrate deferred posts")
    assert step["timeout-minutes"] < narrate["timeout-minutes"]
    # ...and then fail the job, which continue-on-error alone would leave green.
    failed = _step(narrate, "Fail the job if the narration failed")
    assert failed["if"] == f"steps.{step['id']}.outcome != 'success'"
    assert "exit 1" in failed["run"]
    assert names.index("Fail the job if the narration failed") > names.index("Commit and push")

    second = jobs["deploy-narrated"]
    assert set(second["needs"]) == {"deploy", "narrate"}
    assert second["uses"] == jobs["deploy"]["uses"]
    # One run cannot hold two artifacts of the same name.
    assert second["with"]["artifact_name"] != jobs["deploy"]["with"]["artifact_name"]
    publish = yaml.safe_load(PUBLISH.read_text())
    on = publish.get("on") or publish.get(True)
    assert "workflow_call" in on
    uses = {s.get("uses", "").split("@")[0]: s for s in publish["jobs"]["publish"]["steps"]}
    assert uses["actions/upload-pages-artifact"]["with"]["name"] == "${{ inputs.artifact_name }}"
    assert uses["actions/deploy-pages"]["with"]["artifact_name"] == "${{ inputs.artifact_name }}"


def test_narrate_job_gets_the_same_secrets_the_pipeline_needs_to_narrate():
    wf, _ = _workflow()
    first = _step(wf["jobs"]["update"], "Run pipeline")
    step = _step(wf["jobs"]["narrate"], "Narrate deferred posts")
    for key in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FEEDCAST_EMAIL_TO", "SMTP_USER",
                "GMAIL_APP_PASSWORD", "FEEDCAST_TEST_RUN", "VOICE_UPLOAD_DELAY_SECONDS"):
        assert step["env"][key] == first["env"][key], key
    # Failure mail goes to the operator only: no BCC list in this job.
    assert "FEEDCAST_EMAIL_BCC" not in step["env"]


RESULTS = ("success", "failure", "cancelled", "skipped")


def test_narrated_posts_are_deployed_even_when_narration_failed():
    """A failed narration still committed its attempt count and episode pages,
    so they are published; deploy-narrated waits only for the first deploy."""
    condition = _workflow()[0]["jobs"]["deploy-narrated"]["if"]
    for deploy, narrate in product(RESULTS, RESULTS):
        values = {"needs.deploy.result": deploy, "needs.narrate.result": narrate}
        want = deploy == "success" and narrate in ("success", "failure")
        assert _decide(condition, values) is want, (deploy, narrate)
        assert _decide(condition, values, cancelled=True) is False


def test_a_run_that_pushed_is_deployed_and_narrated_even_if_its_job_then_failed():
    """The update job fails after pushing when the report email failed; the
    publish must still go ahead, and the deferred posts be narrated."""
    jobs = _workflow()[0]["jobs"]
    update = jobs["update"]
    commit = _step(update, "Commit and push")
    assert update["outputs"]["pushed"] == f"${{{{ steps.{commit['id']}.outcome == 'success' }}}}"
    for pushed, preview in product(("true", "false", ""), (True, False)):
        values = {"needs.update.outputs.pushed": pushed, "inputs.preview_briefing": preview}
        assert _decide(jobs["deploy"]["if"], values) is (pushed == "true" and not preview)
        assert _decide(jobs["deploy"]["if"], values, cancelled=True) is False
    for pushed, deferred in product(("true", "false", ""), ("2", "0", "")):
        values = {"needs.update.outputs.pushed": pushed,
                  "needs.update.outputs.deferred": deferred}
        want = pushed == "true" and deferred not in ("0", "")
        assert _decide(jobs["narrate"]["if"], values) is want, (pushed, deferred)


@pytest.mark.parametrize("job,pipeline_step", [("update", "Run pipeline"),
                                                ("narrate", "Narrate deferred posts")])
def test_a_report_email_that_was_not_sent_fails_the_job_after_publishing(job, pipeline_step):
    """src.main records a failed send as the step output report_failed."""
    steps_of = _workflow()[0]["jobs"][job]
    names = [s.get("name") for s in steps_of["steps"]]
    pipeline = _step(steps_of, pipeline_step)
    failed = _step(steps_of, "Fail the job if the report email was not sent")
    assert failed["if"] == f"steps.{pipeline['id']}.outputs.report_failed == 'true'"
    assert "exit 1" in failed["run"]
    assert names.index("Fail the job if the report email was not sent") > names.index("Commit and push")


def test_every_job_that_runs_python_shares_one_setup():
    """Checkout, then the composite action; the setup steps live only there."""
    wf, _ = _workflow()
    action = yaml.safe_load(SETUP_ACTION.read_text())
    assert action["runs"]["using"] == "composite"
    for step in action["runs"]["steps"]:
        if "run" in step:
            assert step["shell"] == "bash", step
            # Composite steps take no timeout-minutes: each command bounds itself.
            assert "timeout-minutes" not in step and step["run"].startswith("timeout "), step
    for name in ("update", "narrate", "check-llm"):
        steps = wf["jobs"][name]["steps"]
        assert steps[0]["uses"].startswith("actions/checkout@"), name
        assert steps[1]["uses"] == "./.github/actions/setup-pipeline", name
        rest = yaml.safe_dump(steps[2:])
        for setup in ("git pull", "state.sh pull", "setup-uv", "ci-install-ffmpeg", "uv sync"):
            assert setup not in rest, (name, setup)
    # The LLM smoke test needs neither the published state nor ffmpeg.
    assert wf["jobs"]["check-llm"]["steps"][1]["with"] == {"pipeline": False}
    assert "with" not in wf["jobs"]["update"]["steps"][1]
    assert "with" not in wf["jobs"]["narrate"]["steps"][1]


def _guard(tmp_path, runs: dict) -> str:
    """Run the guard step with a stand-in gh that knows today's other runs
    (`runs`: run id -> its jobs, as the Actions API returns them), and return
    the should_run it decides. The real jq applies the step's --jq filters."""
    wf, _ = _workflow()
    check = _step(wf["jobs"]["guard"], "Has today's daily run already published?")
    bin_dir, outputs = tmp_path / "bin", tmp_path / "github_output"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, subprocess, sys\n"
        f"runs = {runs!r}\n"
        "args = sys.argv[1:]\n"
        "data = ([{'databaseId': int(i)} for i in runs] if args[:2] == ['run', 'list']\n"
        "        else runs[args[1].split('/')[-2]])\n"
        "jq = args[args.index('--jq') + 1]\n"
        "sys.stdout.write(subprocess.run(['jq', '-r', jq], input=json.dumps(data),\n"
        "                                capture_output=True, text=True, check=True).stdout)\n")
    gh.chmod(0o755)
    env = {**os.environ, **check["env"], "ON_DEMAND": "false", "RUN_ID": "999",
           "GITHUB_OUTPUT": str(outputs), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    run = subprocess.run(["bash", "-e", "-c", check["run"]], env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    return outputs.read_text().strip()


def _update_job(conclusion: str, pushed: str | None) -> dict:
    steps = [] if pushed is None else [{"name": "Commit and push", "conclusion": pushed}]
    return {"jobs": [{"name": "guard", "conclusion": "success", "steps": []},
                     {"name": "update", "conclusion": conclusion, "steps": steps}]}


def test_a_run_that_pushed_then_failed_on_its_email_still_counts_as_published(tmp_path):
    """The second daily trigger must not run the pipeline again just because
    the first went red after publishing."""
    assert _guard(tmp_path, {"101": _update_job("failure", "success")}) == "should_run=false"


def test_a_run_that_failed_before_pushing_lets_the_next_trigger_run(tmp_path):
    assert _guard(tmp_path, {"101": _update_job("failure", "failure")}) == "should_run=true"


def test_a_guarded_run_does_not_count_as_published(tmp_path):
    guarded = {"jobs": [{"name": "guard", "conclusion": "success", "steps": []},
                        {"name": "update", "conclusion": "skipped", "steps": []}]}
    assert _guard(tmp_path, {"101": guarded}) == "should_run=true"
