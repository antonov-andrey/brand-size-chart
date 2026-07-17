"""Regression coverage for Task 5 review findings."""

from pathlib import Path

from workflow_container_runtime.step import WorkflowStepCodexConcurrentBase

from brand_size_chart.step.source_discovery import SourceDiscoveryStep


def test_compose_launches_the_complete_input_document() -> None:
    """Mount and pass one complete workflow input instead of removed prompt fragments."""

    compose_text = Path("compose.yaml").read_text(encoding="utf-8")
    assert "WORKFLOW_INPUT_PATH: /input/input.json" in compose_text
    assert "--brand-list" not in compose_text
    assert "--workflow-run-prompt" not in compose_text
    assert "WORKFLOW_RUN_PROMPT" not in compose_text
    assert "INPUT_JSON" in compose_text


def test_source_discovery_uses_runtime_outcome_scheduler() -> None:
    """Keep concurrent scheduling and group validation owned by the runtime."""

    assert issubclass(SourceDiscoveryStep, WorkflowStepCodexConcurrentBase)
    assert hasattr(SourceDiscoveryStep, "run_outcome_list")
