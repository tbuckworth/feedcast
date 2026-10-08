"""Hand-dispatched runs are dev runs unless the operator opts the list in."""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "update-feed.yml"
PUBLISH = WORKFLOW.parent / "publish-pages.yml"


def _workflow():
    wf = yaml.safe_load(WORKFLOW.read_text())
    # PyYAML reads the bare key `on` as the boolean True.
    return wf, (wf.get("on") or wf.get(True))


def test_notify_list_replaces_the_opt_in_test_run():
    _, on = _workflow()
    inputs = on["workflow_dispatch"]["inputs"]
    assert "notify_list" in inputs and inputs["notify_list"]["default"] is False
    assert "test_run" not in inputs


def test_dev_mode_is_the_default_for_every_operator_input():
    wf, _ = _workflow()
    steps = wf["jobs"]["update"]["steps"]
    (run,) = [s for s in steps if s.get("name") == "Run pipeline"]
    expr = run["env"]["FEEDCAST_TEST_RUN"]
    for operator_input in ("inputs.entry_url != ''", "inputs.inject_url != ''",
                           "inputs.resend_report == true", "inputs.force == true"):
        assert operator_input in expr, operator_input
    assert "inputs.notify_list != true" in expr
    # notify_list must not make a bare dispatch skip the daily guard.
    guard = wf["jobs"]["guard"]["steps"][0]["env"]["ON_DEMAND"]
    assert "notify_list" not in guard and "test_run" not in guard


def test_deploy_pings_the_websub_hub_after_pages_is_live():
    """Pocket Casts polls a small feed only every few hours; the hub ping is
    what makes new episodes appear in the app minutes after the email."""
    wf, _ = _workflow()
    assert wf["jobs"]["deploy"]["uses"] == "./.github/workflows/publish-pages.yml"
    steps = yaml.safe_load(PUBLISH.read_text())["jobs"]["publish"]["steps"]
    names = [s.get("name") for s in steps]
    assert names.index("Notify the WebSub hub") > names.index("Deploy to GitHub Pages")
    (ping,) = [s for s in steps if s.get("name") == "Notify the WebSub hub"]
    assert ping["env"]["FEED_URL"] == "https://tbuckworth.github.io/feedcast/feed.xml"
    # Must wait for the CDN to serve this run's feed before the hub fetches it.
    assert "sha256sum output/feed.xml" in ping["run"]
    assert "hub.mode=publish" in ping["run"]


def test_llm_smoke_test_cannot_enter_the_publishing_jobs_or_send_mail():
    wf, on = _workflow()
    assert on["workflow_dispatch"]["inputs"]["llm_smoke_test"]["default"] is False
    assert wf["jobs"]["check-llm"]["if"] == "inputs.llm_smoke_test == true"
    assert wf["jobs"]["guard"]["if"] == "inputs.llm_smoke_test != true"
    assert wf["jobs"]["update"]["needs"] == "guard"
    assert wf["jobs"]["deploy"]["needs"] == "update"
    smoke = wf["jobs"]["check-llm"]
    assert smoke["permissions"] == {"contents": "read"}
    (check,) = [s for s in smoke["steps"] if s.get("name") == "Check live LLM routes"]
    (pipeline,) = [s for s in wf["jobs"]["update"]["steps"] if s.get("name") == "Run pipeline"]
    assert set(check["env"]) == {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
    assert all(value == pipeline["env"][key] for key, value in check["env"].items())
    assert check["run"] == "uv run python -m scripts.check_llm"


def test_verbatim_posts_are_narrated_and_published_after_the_first_deploy():
    """The briefing and summaries publish first; a long post read out in full
    can no longer hold them back or take them down (2026-09-26)."""
    wf, _ = _workflow()
    jobs = wf["jobs"]
    (first,) = [s for s in jobs["update"]["steps"] if s.get("name") == "Run pipeline"]
    assert first["env"]["FEEDCAST_PASS"] == "first" and first["id"] == "pipeline"
    assert jobs["update"]["outputs"]["deferred"] == "${{ steps.pipeline.outputs.deferred }}"

    narrate = jobs["narrate"]
    assert narrate["needs"] == "update" and "needs.update.outputs.deferred != '0'" in narrate["if"]
    names = [s.get("name") for s in narrate["steps"]]
    (step,) = [s for s in narrate["steps"] if s.get("name") == "Narrate deferred posts"]
    assert step["env"]["FEEDCAST_PASS"] == "narrate"
    # A failed or timed-out narration must still commit its attempt count.
    assert step["continue-on-error"] is True
    assert names.index("Commit and push") > names.index("Narrate deferred posts")
    assert step["timeout-minutes"] < narrate["timeout-minutes"]

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
    (first,) = [s for s in wf["jobs"]["update"]["steps"] if s.get("name") == "Run pipeline"]
    (step,) = [s for s in wf["jobs"]["narrate"]["steps"] if s.get("name") == "Narrate deferred posts"]
    for key in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FEEDCAST_EMAIL_TO", "SMTP_USER",
                "GMAIL_APP_PASSWORD", "FEEDCAST_TEST_RUN", "VOICE_UPLOAD_DELAY_SECONDS"):
        assert step["env"][key] == first["env"][key], key
    # Failure mail goes to the operator only: no BCC list in this job.
    assert "FEEDCAST_EMAIL_BCC" not in step["env"]
