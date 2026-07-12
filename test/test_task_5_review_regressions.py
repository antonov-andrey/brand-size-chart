"""Regression coverage for Task 5 review findings."""

import asyncio
from pathlib import Path

import pytest
from workflow_container_runtime.codex import CodexExecutionError
from workflow_container_runtime.step import StepResultValidationError, WorkflowStepInvocation
from workflow_container_runtime.workflow import WorkflowExecutionContext, WorkflowRuntimeCapability

from brand_size_chart.model import (
    BrandInput,
    SourceDiscoveryInputSource,
    SourceDiscoveryResult,
    WorkflowStepSourceDiscoverConfig,
)
from brand_size_chart.step.source_discovery import SourceDiscoveryStep


def test_compose_launches_the_complete_input_document() -> None:
    """Mount and pass one complete workflow input instead of removed prompt fragments."""

    compose_text = Path("compose.yaml").read_text(encoding="utf-8")

    assert "--input /input/input.json" in compose_text
    assert "--brand-list" not in compose_text
    assert "--workflow-run-prompt" not in compose_text
    assert "WORKFLOW_RUN_PROMPT" not in compose_text
    assert "INPUT_JSON" in compose_text


def test_source_discovery_exposes_per_source_failure_preserving_batch_owner() -> None:
    """Keep source validation failures inside ordered source-type results."""

    assert hasattr(SourceDiscoveryStep, "source_type_result_list_get")


def test_source_discovery_keeps_validation_failure_with_successful_registry_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Convert only exhausted validation failures into their own source-type result."""

    step = SourceDiscoveryStep.__new__(SourceDiscoveryStep)

    async def run_step_async(*args: object) -> SourceDiscoveryResult:
        """Return one success and one exhausted validation failure."""

        source = args[3]
        assert isinstance(source, SourceDiscoveryInputSource)
        if source.source_type == "official_seller_size_guide":
            raise StepResultValidationError(feedback_list=["Incomplete current state."])
        return SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="no_table",
            source_discovery_database_path="workflow/brand/step/source_discover/state.sqlite3",
        )

    monkeypatch.setattr("brand_size_chart.step.source_discovery.DBOS.run_step_async", run_step_async)
    step._workflow_step_config_type_validate = lambda config: None

    result_list = asyncio.run(
        SourceDiscoveryStep.source_type_result_list_get(
            step,
            _invocation_list_get(tmp_path, ["official_brand_size_guide", "official_seller_size_guide"]),
            _config_get(),
        )
    )

    assert [result.source_type for result in result_list] == ["official_brand_size_guide", "official_seller_size_guide"]
    assert result_list[0].status == "success"
    assert result_list[0].source_discovery_result is not None
    assert result_list[1].status == "failed"
    assert result_list[1].source_discovery_result is None
    assert result_list[1].error_list == ["StepResultValidationError: Incomplete current state."]


def test_source_discovery_propagates_codex_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Leave low-level Codex failures visible to DBOS recovery."""

    step = SourceDiscoveryStep.__new__(SourceDiscoveryStep)

    async def run_step_async(*args: object) -> SourceDiscoveryResult:
        """Raise the infrastructure failure without conversion."""

        _ = args
        raise CodexExecutionError("Codex unavailable")

    monkeypatch.setattr("brand_size_chart.step.source_discovery.DBOS.run_step_async", run_step_async)
    step._workflow_step_config_type_validate = lambda config: None

    with pytest.raises(CodexExecutionError, match="Codex unavailable"):
        asyncio.run(
            SourceDiscoveryStep.source_type_result_list_get(
                step,
                _invocation_list_get(tmp_path, ["official_brand_size_guide"]),
                _config_get(),
            )
        )


def _config_get() -> WorkflowStepSourceDiscoverConfig:
    """Build one explicit bounded source-discovery config."""

    return WorkflowStepSourceDiscoverConfig(
        concurrency=2,
        correction_attempt_limit=1,
        instruction="",
        model="gpt-5.6-terra",
        reasoning_effort="high",
    )


def _invocation_list_get(
    tmp_path: Path, source_type_list: list[str]
) -> list[WorkflowStepInvocation[SourceDiscoveryInputSource]]:
    """Build independent source invocation contexts in registry order."""

    context = WorkflowExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        workflow_instance_dir=tmp_path / "workflow" / "brand",
    )
    brand_input = BrandInput(
        parsed_brand_key="brand", parsed_brand_name="Brand", raw_brand_name="Brand", source_line_number=1
    )
    return [
        WorkflowStepInvocation(
            execution_context=context.for_step(
                runtime_capability=WorkflowRuntimeCapability(browser=None),
                step_instance_key=f"source_discover_{source_type}",
            ),
            input_source=SourceDiscoveryInputSource(brand_input=brand_input, source_type=source_type),
        )
        for source_type in source_type_list
    ]
