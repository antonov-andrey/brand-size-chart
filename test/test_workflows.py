"""Behavior tests for typed DBOS workflow wrappers."""

import asyncio
import inspect

from pathlib import Path

import pytest
from workflow_container_runtime.codex import CodexExecutionError
from workflow_container_runtime.step import WorkflowStepInvocation, WorkflowStepInvocationOutcome
from workflow_container_runtime.workflow import WorkflowExecutionContext, WorkflowRuntimeCapability

import brand_size_chart.model as brand_size_chart_model
from brand_size_chart.model import (
    BrandInput,
    BrandOutputResult,
    BrandResult,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    SourceDiscoveryInputSource,
    SourceDiscoveryResult,
    WorkflowBrandSizeChartConfig,
    WorkflowBrandSizeChartInput,
    WorkflowBrandSizeChartRequest,
    WorkflowBrandSizeChartStepMap,
    WorkflowStepCanonicalSelectConfig,
    WorkflowStepCoverageDecideConfig,
    WorkflowStepSourceDiscoverConfig,
)
from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow
from brand_size_chart.workflow.root import BrandSizeChartRunWorkflow


def _brand_input_get() -> BrandInput:
    """Build one stable brand selected by the parent workflow.

    Returns:
        Brand input used by every source-discovery invocation.
    """

    return BrandInput(
        parsed_brand_key="brand",
        parsed_brand_name="Brand",
    )


def test_root_workflow_builds_minimal_brand_input_in_request_order(tmp_path: Path) -> None:
    """Construct one minimal brand handoff per strict request value in order."""

    received_brand_input_list: list[BrandInput] = []
    workflow = BrandSizeChartRunWorkflow.__new__(BrandSizeChartRunWorkflow)

    class BrandWorkflow:
        """Record each root-to-brand handoff."""

        async def run(self, execution_context: object, workflow_input: object, brand_input: BrandInput) -> BrandResult:
            """Record the brand and return one minimal successful result."""

            _ = execution_context
            _ = workflow_input
            received_brand_input_list.append(brand_input)
            return BrandResult(
                brand_input=brand_input,
                brand_output_result=None,
                canonical_selection_result=None,
                coverage_decision_result=None,
                error_list=[],
                source_type_result_list=[],
                status="success",
                warning_list=[],
            )

    async def artifact_write(*args: object) -> None:
        """Accept one workflow publication boundary."""

    async def result_write(*args: object) -> object:
        """Return the candidate root result."""

        return args[-1]

    workflow._brand_workflow = BrandWorkflow()
    workflow.input_write_step = artifact_write
    workflow.result_write_step = result_write
    workflow_input = _workflow_input_get(concurrency=1).model_copy(
        update={
            "request": WorkflowBrandSizeChartRequest(
                brand_list=["LC Waikiki", "Mavi"],
                priority_country_code="TR",
                product_type_request_list=[],
                source_type_allow_list=[],
            )
        }
    )

    workflow_result = asyncio.run(
        inspect.unwrap(BrandSizeChartRunWorkflow.run)(
            workflow,
            WorkflowExecutionContext(
                result_dir=tmp_path,
                runtime_capability=WorkflowRuntimeCapability(browser=None),
                workflow_instance_dir=tmp_path / "workflow" / "run",
            ),
            workflow_input,
        )
    )

    assert received_brand_input_list == [
        BrandInput(parsed_brand_key="lc_waikiki", parsed_brand_name="LC Waikiki"),
        BrandInput(parsed_brand_key="mavi", parsed_brand_name="Mavi"),
    ]
    assert [result.brand_input for result in workflow_result.brand_result_list] == received_brand_input_list


def _workflow_input_get(concurrency: int) -> WorkflowBrandSizeChartInput:
    """Build the complete typed workflow input for a concurrent source-discovery run.

    Args:
        concurrency: Maximum number of source-discovery invocations owned by runtime.

    Returns:
        Complete workflow input with exact step configurations.
    """

    return WorkflowBrandSizeChartInput(
        config=WorkflowBrandSizeChartConfig(
            instruction="",
            mcp_playwright_profile_writeback_policy={
                "mcp_playwright_profile_name_prefix": "",
                "workflow_run_status_list": ("done",),
            },
            step_map=WorkflowBrandSizeChartStepMap(
                canonical_select=WorkflowStepCanonicalSelectConfig(
                    correction_attempt_limit=1,
                    instruction="",
                    mcp_playwright_profile=None,
                    mcp_playwright_profile_source=None,
                    model="gpt-5.6-terra",
                    reasoning_effort="high",
                ),
                coverage_decide=WorkflowStepCoverageDecideConfig(
                    correction_attempt_limit=1,
                    instruction="",
                    mcp_playwright_profile=None,
                    mcp_playwright_profile_source=None,
                    model="gpt-5.6-terra",
                    reasoning_effort="high",
                ),
                source_discover=WorkflowStepSourceDiscoverConfig(
                    concurrency=concurrency,
                    correction_attempt_limit=1,
                    instruction="",
                    mcp_playwright_profile="source-discover",
                    mcp_playwright_profile_source=None,
                    model="gpt-5.6-terra",
                    reasoning_effort="high",
                ),
            ),
        ),
        request=WorkflowBrandSizeChartRequest(
            brand_list=["Brand"],
            priority_country_code="TR",
            product_type_request_list=[],
            source_type_allow_list=[],
        ),
    )


def _workflow_get(
    outcome_list: list[WorkflowStepInvocationOutcome[SourceDiscoveryResult]],
    received: dict[str, object],
) -> BrandSizeChartBrandWorkflow:
    """Build one workflow that executes source discovery through the real workflow method.

    Args:
        outcome_list: Ordered runtime outcomes returned by the concurrent step fake.
        received: Mutable recording target for the runtime call arguments.

    Returns:
        Workflow whose unrelated downstream steps return minimal typed results.
    """

    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)

    class SourceDiscoveryStep:
        """Record the runtime request without a DBOS source-discovery execution."""

        async def run_outcome_list(
            self,
            invocation_list: list[WorkflowStepInvocation[SourceDiscoveryInputSource]],
            workflow_step_config: WorkflowStepSourceDiscoverConfig,
        ) -> list[WorkflowStepInvocationOutcome[SourceDiscoveryResult]]:
            """Return scripted outcomes through the inherited scheduler public boundary."""

            received.update(invocation_list=invocation_list, workflow_step_config=workflow_step_config)
            return outcome_list

    workflow._source_discovery_step = SourceDiscoveryStep()
    workflow.brand_output_write_step = lambda execution_context, input_source: BrandOutputResult(
        size_chart_path_list=[]
    )
    workflow.canonical_select_write_step = (
        lambda execution_context, input_source, workflow_step_config: CanonicalSelectionResult(
            canonical_selection_list=[], unresolved_size_group_gap_list=[]
        )
    )
    workflow.coverage_decide_write_step = (
        lambda execution_context, input_source, workflow_step_config: CoverageDecisionResult(
            covered_product_type_list=[]
        )
    )

    async def input_write_step(execution_context: object, workflow_input: object) -> None:
        """Accept the publication call at the async runtime boundary."""

        _ = execution_context
        _ = workflow_input

    async def result_write_step(
        execution_context: object,
        workflow_input: object,
        workflow_result: object,
    ) -> object:
        """Return the candidate result at the async runtime boundary."""

        _ = execution_context
        _ = workflow_input
        return workflow_result

    workflow.input_write_step = input_write_step
    workflow.result_write_step = result_write_step
    workflow.source_type_list_get = lambda request: ["official_brand_size_guide", "official_seller_size_guide"]
    return workflow


def test_brand_workflow_runs_source_discovery_directly_with_exact_config_and_result_order(tmp_path: Path) -> None:
    """Run the workflow path without an aggregate DBOS source-discovery step boundary."""

    received: dict[str, object] = {}
    workflow = _workflow_get(
        [WorkflowStepInvocationOutcome(result=result, validation_feedback_tuple=()) for result in _result_list_get()],
        received,
    )
    workflow_input = _workflow_input_get(concurrency=2)
    brand_input = _brand_input_get()
    context = WorkflowExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        workflow_instance_dir=tmp_path / "workflow" / "brand",
    )

    workflow_result = asyncio.run(
        inspect.unwrap(BrandSizeChartBrandWorkflow.run)(workflow, context, workflow_input, brand_input)
    )

    assert received["workflow_step_config"] == workflow_input.config.step_map.source_discover
    assert [invocation.input_source.source_type for invocation in received["invocation_list"]] == [
        "official_brand_size_guide",
        "official_seller_size_guide",
    ]
    assert [result.source_discovery_result for result in workflow_result.source_type_result_list] == _result_list_get()
    assert "source_type_skip_list" not in type(workflow_result).model_fields


def test_brand_model_excludes_sequential_source_skip_contract() -> None:
    """Expose only results for source types started by the concurrent runtime plan."""

    assert "SourceTypeSkip" not in brand_size_chart_model.__all__
    assert not hasattr(brand_size_chart_model, "SourceTypeSkip")


def test_brand_workflow_preserves_exhausted_validation_feedback(tmp_path: Path) -> None:
    """Expose runtime correction exhaustion as the existing failed source-type result."""

    workflow = _workflow_get(
        [
            WorkflowStepInvocationOutcome(
                result=None,
                validation_feedback_tuple=("Use one accepted source table.",),
            ),
            WorkflowStepInvocationOutcome(result=_result_list_get()[1], validation_feedback_tuple=()),
        ],
        {},
    )
    context = WorkflowExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        workflow_instance_dir=tmp_path / "workflow" / "brand",
    )

    workflow_result = asyncio.run(
        inspect.unwrap(BrandSizeChartBrandWorkflow.run)(
            workflow, context, _workflow_input_get(concurrency=2), _brand_input_get()
        )
    )

    assert workflow_result.source_type_result_list[0].error_list == [
        "StepResultValidationError: Use one accepted source table."
    ]
    assert workflow_result.source_type_result_list[0].source_discovery_result is None
    assert workflow_result.source_type_result_list[0].status == "failed"


@pytest.mark.parametrize(
    ("outcome", "status", "error_list"),
    [
        ("table_available", "success", []),
        ("no_table", "success", []),
        ("market_conflict", "failed", ["Source discovery market conflict."]),
    ],
)
def test_brand_workflow_maps_verified_discovery_terminal_outcomes(
    tmp_path: Path, outcome: str, status: str, error_list: list[str]
) -> None:
    """Map each verified terminal discovery result into its source-type handoff."""

    result = SourceDiscoveryResult(
        browsing_error_list=[], outcome=outcome, source_discovery_database_path="workflow/brand/source/state.sqlite3"
    )
    workflow = _workflow_get([WorkflowStepInvocationOutcome(result=result, validation_feedback_tuple=())], {})
    workflow.source_type_list_get = lambda request: ["official_brand_size_guide"]
    workflow_result = asyncio.run(
        inspect.unwrap(BrandSizeChartBrandWorkflow.run)(
            workflow,
            WorkflowExecutionContext(
                result_dir=tmp_path,
                runtime_capability=WorkflowRuntimeCapability(browser=None),
                workflow_instance_dir=tmp_path / "workflow" / "brand",
            ),
            _workflow_input_get(concurrency=1),
            _brand_input_get(),
        )
    )

    assert workflow_result.source_type_result_list[0].status == status
    assert workflow_result.source_type_result_list[0].error_list == error_list


def test_brand_workflow_propagates_codex_infrastructure_errors(tmp_path: Path) -> None:
    """Leave Codex transport failures to DBOS recovery instead of converting them to domain results."""

    workflow = _workflow_get([], {})

    class FailingSourceDiscoveryStep:
        """Raise one infrastructure failure from the concurrent runtime boundary."""

        async def run_outcome_list(self, invocation_list: object, workflow_step_config: object) -> object:
            """Raise the transport failure without domain translation."""

            _ = invocation_list
            _ = workflow_step_config
            raise CodexExecutionError("Codex unavailable")

    workflow._source_discovery_step = FailingSourceDiscoveryStep()
    with pytest.raises(CodexExecutionError, match="Codex unavailable"):
        asyncio.run(
            inspect.unwrap(BrandSizeChartBrandWorkflow.run)(
                workflow,
                WorkflowExecutionContext(
                    result_dir=tmp_path,
                    runtime_capability=WorkflowRuntimeCapability(browser=None),
                    workflow_instance_dir=tmp_path / "workflow" / "brand",
                ),
                _workflow_input_get(concurrency=1),
                _brand_input_get(),
            )
        )


def _result_list_get() -> list[SourceDiscoveryResult]:
    """Build distinct discovery results in input registry order.

    Returns:
        Source-discovery results for two independent source types.
    """

    return [
        SourceDiscoveryResult(
            browsing_error_list=[], outcome="no_table", source_discovery_database_path="first.sqlite3"
        ),
        SourceDiscoveryResult(
            browsing_error_list=[], outcome="table_available", source_discovery_database_path="second.sqlite3"
        ),
    ]
