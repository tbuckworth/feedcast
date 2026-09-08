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
