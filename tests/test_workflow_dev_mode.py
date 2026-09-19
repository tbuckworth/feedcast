"""Hand-dispatched runs are dev runs unless the operator opts the list in."""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "update-feed.yml"


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
    names = [s.get("name") for s in wf["jobs"]["deploy"]["steps"]]
    assert names.index("Notify the WebSub hub") > names.index("Deploy to GitHub Pages")
    (ping,) = [s for s in wf["jobs"]["deploy"]["steps"] if s.get("name") == "Notify the WebSub hub"]
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
