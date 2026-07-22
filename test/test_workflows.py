"""Behavior tests for typed DBOS workflow wrappers."""

import asyncio
from datetime import UTC, datetime
import inspect
import json
from pathlib import Path

import pytest
from workflow_container_contract import WorkflowControlFinalRequest, WorkflowControlSafepointRequest, WorkflowDefinition
from workflow_container_contract import WorkflowRunContext
from workflow_container_runtime import WorkflowControlRequestBuilder
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.capability import BrowserRuntimeCapability
from workflow_container_runtime.codex import CodexExecutionError
from workflow_container_runtime.step import WorkflowStepInvocation, WorkflowStepInvocationOutcome
from workflow_container_runtime.workflow import (
    NetworkProxyRuntimeCapability,
    WorkflowDataPath,
    WorkflowExecutionContext,
    WorkflowRuntimeCapability,
)

import brand_size_chart.model as brand_size_chart_model
from brand_size_chart.model import (
    BrandInput,
    BrandOutputResult,
    BrandResult,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    RunResult,
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


class WorkflowControlClientStub:
    """Record exact safepoint and final requests from the root workflow."""

    final_request_list: list[WorkflowControlFinalRequest]
    safepoint_request_list: list[WorkflowControlSafepointRequest]

    def __init__(self) -> None:
        """Initialize empty request history."""

        self.final_request_list = []
        self.safepoint_request_list = []

    def safepoint_send(self, *, request: WorkflowControlSafepointRequest) -> None:
        """Record one safepoint request.

        Args:
            request: Canonical safepoint request.
        """

        self.safepoint_request_list.append(request)

    def final_send(self, *, request: WorkflowControlFinalRequest) -> None:
        """Record one final request.

        Args:
            request: Canonical final request.
        """

        self.final_request_list.append(request)


def _control_request_builder_get() -> WorkflowControlRequestBuilder:
    """Build the exact source declaration used by root control tests.

    Returns:
        Source-validating control request builder.
    """

    return WorkflowControlRequestBuilder(
        workflow_definition=WorkflowDefinition.model_validate(
            {
                "build": {"dockerfile_path": "Dockerfile"},
                "command": ["run"],
                "data": {"run": {"result": "result/{brand_key}", "workspace": "workspace/{brand_key}"}},
                "input_schema_path": "input.schema.json",
                "name": "brand_size_chart",
                "step": {"brand_complete": {}},
            }
        )
    )


def _data_path_get(tmp_path: Path) -> WorkflowDataPath:
    """Return isolated standard result and workspace roots.

    Args:
        tmp_path: Test-owned root.

    Returns:
        Standard Data paths for one test run.
    """

    return WorkflowDataPath(
        result_path=(tmp_path / "result").resolve(),
        workspace_path=(tmp_path / "workspace").resolve(),
    )


def _run_context_get() -> WorkflowRunContext:
    """Return one immutable exact platform provenance context.

    Returns:
        Stable test run context.
    """

    return WorkflowRunContext(
        interface_major_version=2,
        version=1,
        workflow_id="workflow-id",
        workflow_name="brand_size_chart",
        workflow_run_id="20260719123456789",
        workflow_run_timestamp=datetime(2026, 7, 19, 12, 34, 56, 789000, tzinfo=UTC),
        workflow_source_id="source-id",
        workflow_source_version_id="source-version-id",
    )


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

    def safepoint_write(*args: object) -> None:
        """Accept one brand safepoint boundary."""

    def final_write(*args: object) -> None:
        """Accept the root final boundary."""

    workflow._brand_workflow = BrandWorkflow()
    workflow.input_write_step = artifact_write
    workflow.result_write_step = result_write
    workflow.brand_safepoint_step = safepoint_write
    workflow.final_request_step = final_write
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
                data_path=_data_path_get(tmp_path),
                result_dir=tmp_path,
                run_context=_run_context_get(),
                runtime_capability=WorkflowRuntimeCapability(
                    browser=None,
                    network_proxy=NetworkProxyRuntimeCapability(proxy_by_name_map={}),
                ),
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


def test_root_workflow_safepoint_publishes_result_and_workspace_atomically(tmp_path: Path) -> None:
    """Bind one stable brand transition to both exact declared Data subtrees."""

    control_client = WorkflowControlClientStub()
    workflow = BrandSizeChartRunWorkflow.__new__(BrandSizeChartRunWorkflow)
    workflow._artifact_writer = JsonArtifactWriter()
    workflow._control_client = control_client
    workflow._control_request_builder = _control_request_builder_get()
    brand_input = _brand_input_get()
    brand_result = BrandResult(
        brand_input=brand_input,
        brand_output_result=None,
        canonical_selection_result=None,
        coverage_decision_result=None,
        error_list=[],
        source_type_result_list=[],
        status="success",
        warning_list=[],
    )
    execution_context = WorkflowExecutionContext(
        data_path=_data_path_get(tmp_path),
        result_dir=tmp_path / "runtime-result",
        run_context=_run_context_get(),
        runtime_capability=WorkflowRuntimeCapability(
            browser=None,
            network_proxy=NetworkProxyRuntimeCapability(proxy_by_name_map={}),
        ),
        workflow_instance_dir=tmp_path / "runtime-result" / "workflow" / "run" / "workflow" / "brand_brand",
    )
    execution_context.workflow_instance_dir.mkdir(parents=True)

    inspect.unwrap(BrandSizeChartRunWorkflow.brand_safepoint_step)(
        workflow,
        execution_context,
        brand_input,
        brand_result,
    )

    assert json.loads((tmp_path / "workspace" / "brand" / "safepoint.json").read_text()) == {
        "parsed_brand_key": "brand",
        "parsed_brand_name": "Brand",
        "status": "success",
    }
    request = control_client.safepoint_request_list[0]
    assert request.step_identity == "brand/brand"
    assert request.step_key == "brand_complete"
    assert request.transition_identity == "brand/brand/completed"
    assert [item.model_dump() for item in request.manifest_request_list] == [
        {"manifest_key": "result", "path_parameter_by_name_map": {"brand_key": "brand"}},
        {"manifest_key": "workspace", "path_parameter_by_name_map": {"brand_key": "brand"}},
    ]


def test_root_workflow_final_intent_contains_exact_result_without_duplicate_manifests() -> None:
    """Send the final open result after brand manifests were accepted at safepoints."""

    control_client = WorkflowControlClientStub()
    workflow = BrandSizeChartRunWorkflow.__new__(BrandSizeChartRunWorkflow)
    workflow._control_client = control_client
    workflow._control_request_builder = _control_request_builder_get()
    workflow_result = RunResult(brand_result_list=[], error_list=[], status="success", warning_list=[])

    inspect.unwrap(BrandSizeChartRunWorkflow.final_request_step)(workflow, workflow_result)

    request = control_client.final_request_list[0]
    assert request.transition_identity == "run/completed"
    assert request.workflow_result == workflow_result
    assert request.manifest_request_list == []


def _workflow_input_get(
    concurrency: int,
    *,
    canonical_select_network_proxy_name: str | None = None,
    coverage_decide_network_proxy_name: str | None = None,
    source_discover_network_proxy_name: str | None = None,
) -> WorkflowBrandSizeChartInput:
    """Build the complete typed workflow input for a concurrent source-discovery run.

    Args:
        concurrency: Maximum number of source-discovery invocations owned by runtime.
        canonical_select_network_proxy_name: Exact proxy selected for canonical selection.
        coverage_decide_network_proxy_name: Exact proxy selected for coverage decisions.
        source_discover_network_proxy_name: Exact proxy selected for all source discovery invocations.

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
                    mcp_playwright_network_proxy_name=canonical_select_network_proxy_name,
                    mcp_playwright_profile=None,
                    mcp_playwright_profile_source=None,
                    model="gpt-5.6-terra",
                    reasoning_effort="high",
                ),
                coverage_decide=WorkflowStepCoverageDecideConfig(
                    correction_attempt_limit=1,
                    instruction="",
                    mcp_playwright_network_proxy_name=coverage_decide_network_proxy_name,
                    mcp_playwright_profile=None,
                    mcp_playwright_profile_source=None,
                    model="gpt-5.6-terra",
                    reasoning_effort="high",
                ),
                source_discover=WorkflowStepSourceDiscoverConfig(
                    concurrency=concurrency,
                    correction_attempt_limit=1,
                    instruction="",
                    mcp_playwright_network_proxy_name=source_discover_network_proxy_name,
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

    def brand_output_write_step(execution_context: object, input_source: object) -> BrandOutputResult:
        """Record deterministic output routing and return an empty dataset result."""

        received.update(
            brand_output_execution_context=execution_context,
            brand_output_input_source=input_source,
        )
        return BrandOutputResult(
            dataset_path="result/brand/dataset/brand_size_chart/part-00000.jsonl",
            size_chart_path_list=[],
        )

    def canonical_select_write_step(
        execution_context: object,
        input_source: object,
        workflow_step_config: WorkflowStepCanonicalSelectConfig,
    ) -> CanonicalSelectionResult:
        """Record exact canonical-selection routing and return an empty decision."""

        received.update(
            canonical_select_execution_context=execution_context,
            canonical_select_input_source=input_source,
            canonical_select_workflow_step_config=workflow_step_config,
        )
        return CanonicalSelectionResult(canonical_selection_list=[], unresolved_size_group_gap_list=[])

    def coverage_decide_write_step(
        execution_context: object,
        input_source: object,
        workflow_step_config: WorkflowStepCoverageDecideConfig,
    ) -> CoverageDecisionResult:
        """Record exact coverage-decision routing and return an empty decision."""

        received.update(
            coverage_decide_execution_context=execution_context,
            coverage_decide_input_source=input_source,
            coverage_decide_workflow_step_config=workflow_step_config,
        )
        return CoverageDecisionResult(covered_product_type_list=[])

    workflow.brand_output_write_step = brand_output_write_step
    workflow.canonical_select_write_step = canonical_select_write_step
    workflow.coverage_decide_write_step = coverage_decide_write_step

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
        data_path=_data_path_get(tmp_path),
        result_dir=tmp_path,
        run_context=_run_context_get(),
        runtime_capability=WorkflowRuntimeCapability(
            browser=None,
            network_proxy=NetworkProxyRuntimeCapability(proxy_by_name_map={}),
        ),
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


def test_brand_workflow_preserves_each_explicit_proxy_setting_without_distribution(tmp_path: Path) -> None:
    """Pass one full map while every browser-backed step keeps only its own exact input setting."""

    received: dict[str, object] = {}
    workflow = _workflow_get(
        [WorkflowStepInvocationOutcome(result=result, validation_feedback_tuple=()) for result in _result_list_get()],
        received,
    )
    workflow_input = _workflow_input_get(
        concurrency=2,
        canonical_select_network_proxy_name="owner/canonical",
        coverage_decide_network_proxy_name="owner/coverage",
        source_discover_network_proxy_name="owner/source",
    )
    runtime_capability = WorkflowRuntimeCapability(
        browser=BrowserRuntimeCapability(
            mcp_playwright_profile_source="/.secret/playwright_profile",
            mcp_playwright_profile_writeback_candidate_url="http://browser-runtime/profile-writeback",
            mcp_url="http://browser-runtime/mcp",
        ),
        network_proxy=NetworkProxyRuntimeCapability(
            proxy_by_name_map={
                "owner/canonical": "socks5://canonical-proxy:1080",
                "owner/coverage": "socks5://coverage-proxy:1080",
                "owner/source": "socks5://source-proxy:1080",
            }
        ),
    )

    asyncio.run(
        inspect.unwrap(BrandSizeChartBrandWorkflow.run)(
            workflow,
            WorkflowExecutionContext(
                data_path=_data_path_get(tmp_path),
                result_dir=tmp_path,
                run_context=_run_context_get(),
                runtime_capability=runtime_capability,
                workflow_instance_dir=tmp_path / "workflow" / "brand",
            ),
            workflow_input,
            _brand_input_get(),
        )
    )

    invocation_list = received["invocation_list"]
    assert isinstance(invocation_list, list)
    assert len(invocation_list) == 2
    assert all(invocation.execution_context.runtime_capability == runtime_capability for invocation in invocation_list)
    assert all(
        set(type(invocation.input_source).model_fields).isdisjoint(
            {"mcp_playwright_network_proxy_name", "network_proxy_index", "workflow_step_config"}
        )
        for invocation in invocation_list
    )
    assert received["workflow_step_config"] == workflow_input.config.step_map.source_discover
    assert received["canonical_select_workflow_step_config"] == workflow_input.config.step_map.canonical_select
    assert received["coverage_decide_workflow_step_config"] == workflow_input.config.step_map.coverage_decide
    assert received["canonical_select_execution_context"].runtime_capability == runtime_capability
    assert received["coverage_decide_execution_context"].runtime_capability == runtime_capability
    brand_output_runtime_capability = received["brand_output_execution_context"].runtime_capability
    assert brand_output_runtime_capability.browser is None
    assert brand_output_runtime_capability.network_proxy == runtime_capability.network_proxy


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
        data_path=_data_path_get(tmp_path),
        result_dir=tmp_path,
        run_context=_run_context_get(),
        runtime_capability=WorkflowRuntimeCapability(
            browser=None,
            network_proxy=NetworkProxyRuntimeCapability(proxy_by_name_map={}),
        ),
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
def test_brand_workflow_maps_verified_discovery_final_outcomes(
    tmp_path: Path, outcome: str, status: str, error_list: list[str]
) -> None:
    """Map each verified final discovery result into its source-type handoff."""

    result = SourceDiscoveryResult(
        browsing_error_list=[], outcome=outcome, source_discovery_database_path="workflow/brand/source/state.sqlite3"
    )
    workflow = _workflow_get([WorkflowStepInvocationOutcome(result=result, validation_feedback_tuple=())], {})
    workflow.source_type_list_get = lambda request: ["official_brand_size_guide"]
    workflow_result = asyncio.run(
        inspect.unwrap(BrandSizeChartBrandWorkflow.run)(
            workflow,
            WorkflowExecutionContext(
                data_path=_data_path_get(tmp_path),
                result_dir=tmp_path,
                run_context=_run_context_get(),
                runtime_capability=WorkflowRuntimeCapability(
                    browser=None,
                    network_proxy=NetworkProxyRuntimeCapability(proxy_by_name_map={}),
                ),
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
                    data_path=_data_path_get(tmp_path),
                    result_dir=tmp_path,
                    run_context=_run_context_get(),
                    runtime_capability=WorkflowRuntimeCapability(
                        browser=None,
                        network_proxy=NetworkProxyRuntimeCapability(proxy_by_name_map={}),
                    ),
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
