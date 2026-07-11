"""Source-type workflow cutover tests."""

from pathlib import Path

import pytest
from workflow_container_runtime.codex import CodexExecutionError
from workflow_container_runtime.step import StepResultValidationError
from workflow_container_runtime.workflow import WorkflowExecutionContext, WorkflowRuntimeCapability

from brand_size_chart.model import (
    BrandInput,
    BrandOutputResult,
    BrandWorkflowInput,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    PromptScope,
    SourceDiscoveryResult,
    SourceTypeResult,
    SourceTypeSkip,
    SourceTypeWorkflowInput,
)
from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow
from brand_size_chart.workflow.source_type import BrandSizeChartSourceTypeWorkflow


def _context_get(tmp_path: Path) -> WorkflowExecutionContext:
    """Build one isolated source-type workflow context.

    Args:
        tmp_path: Isolated result root.

    Returns:
        Workflow execution context.
    """

    return WorkflowExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        workflow_instance_dir=tmp_path / "workflow" / "source_type",
    )


def _input_get() -> SourceTypeWorkflowInput:
    """Build one source-type workflow input.

    Returns:
        Typed workflow input.
    """

    return SourceTypeWorkflowInput(
        brand_input=BrandInput(
            parsed_brand_key="brand", parsed_brand_name="Brand", raw_brand_name="Brand", source_line_number=1
        ),
        prompt_scope=PromptScope(),
        source_type="official_brand_size_guide",
    )


@pytest.mark.parametrize(
    ("outcome", "status", "error_list"),
    [
        ("table_available", "success", []),
        ("no_table", "success", []),
        ("market_conflict", "failed", ["Source discovery market conflict."]),
    ],
)
def test_source_type_maps_verified_discovery_outcome_without_extraction(
    tmp_path: Path, outcome: str, status: str, error_list: list[str]
) -> None:
    """Use one discovery DBOS step and preserve its complete result.

    Args:
        tmp_path: Isolated result root.
        outcome: Verified discovery outcome.
        status: Expected workflow status.
        error_list: Expected stable workflow errors.
    """

    workflow = BrandSizeChartSourceTypeWorkflow.__new__(BrandSizeChartSourceTypeWorkflow)
    discovery_result = SourceDiscoveryResult(
        browsing_error_list=[],
        outcome=outcome,
        source_discovery_database_path="workflow/source_type/step/source_discover/state.sqlite3",
    )
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow.source_discover_write_step = lambda execution_context, workflow_input: discovery_result

    result = BrandSizeChartSourceTypeWorkflow.run.__wrapped__(workflow, _context_get(tmp_path), _input_get())

    assert result.status == status
    assert result.error_list == error_list
    assert result.source_discovery_result == discovery_result
    assert set(type(result).model_fields) == {
        "error_list",
        "source_discovery_result",
        "source_type",
        "status",
        "warning_list",
    }


def test_source_type_returns_owned_failure_only_for_exhausted_validation(tmp_path: Path) -> None:
    """Convert only exhausted mechanical correction into the source-type result.

    Args:
        tmp_path: Isolated result root.
    """

    workflow = BrandSizeChartSourceTypeWorkflow.__new__(BrandSizeChartSourceTypeWorkflow)
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow.source_discover_write_step = lambda execution_context, workflow_input: (_ for _ in ()).throw(
        StepResultValidationError(feedback_list=["Incomplete current state."])
    )

    result = BrandSizeChartSourceTypeWorkflow.run.__wrapped__(workflow, _context_get(tmp_path), _input_get())

    assert result.status == "failed"
    assert result.source_discovery_result is None
    assert result.error_list == ["StepResultValidationError: Incomplete current state."]


def test_source_type_propagates_codex_infrastructure_errors(tmp_path: Path) -> None:
    """Leave Codex infrastructure errors to DBOS recovery.

    Args:
        tmp_path: Isolated result root.
    """

    workflow = BrandSizeChartSourceTypeWorkflow.__new__(BrandSizeChartSourceTypeWorkflow)
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow.source_discover_write_step = lambda execution_context, workflow_input: (_ for _ in ()).throw(
        CodexExecutionError("Codex unavailable")
    )

    with pytest.raises(CodexExecutionError, match="Codex unavailable"):
        BrandSizeChartSourceTypeWorkflow.run.__wrapped__(workflow, _context_get(tmp_path), _input_get())


def test_brand_workflow_skips_remaining_product_sources_after_complete_coverage(tmp_path: Path) -> None:
    """Keep the complete started result and explicit coverage-complete skip partition.

    Args:
        tmp_path: Isolated result root.
    """

    source_type_list = [
        "official_brand_size_guide",
        "official_brand_product_page",
        "official_marketplace_product_page",
    ]
    started_result = SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="table_available",
            source_discovery_database_path="workflow/brand/official_brand_size_guide/source_discover/state.sqlite3",
        ),
        source_type="official_brand_size_guide",
        status="success",
        warning_list=[],
    )
    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    started_input_list: list[SourceTypeWorkflowInput] = []
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow.source_type_list_get = lambda prompt_scope: source_type_list
    workflow._source_type_workflow = type(
        "SourceTypeWorkflow",
        (),
        {
            "run": lambda self, execution_context, workflow_input: (
                started_input_list.append(workflow_input) or started_result
            )
        },
    )()
    workflow.coverage_decide_write_step = lambda execution_context, input_source: CoverageDecisionResult(
        covered_product_type_list=[],
        uncovered_product_type_gap_list=[],
    )
    workflow.canonical_select_write_step = lambda execution_context, input_source: CanonicalSelectionResult(
        canonical_selection_list=[],
        unresolved_size_group_gap_list=[],
    )
    workflow.brand_output_write_step = lambda execution_context, input_source: BrandOutputResult(
        size_chart_path_list=[]
    )
    workflow_input = BrandWorkflowInput(
        brand_input=_input_get().brand_input,
        prompt_scope=PromptScope(product_type_request_list=["dress"]),
    )

    result = BrandSizeChartBrandWorkflow.run.__wrapped__(workflow, _context_get(tmp_path), workflow_input)

    assert started_input_list == [
        SourceTypeWorkflowInput(
            brand_input=workflow_input.brand_input,
            prompt_scope=PromptScope(product_type_request_list=[]),
            source_type="official_brand_size_guide",
        )
    ]
    assert result.source_type_result_list == [started_result]
    assert result.source_type_skip_list == [
        SourceTypeSkip(
            reason="requested_product_type_coverage_complete",
            source_type="official_brand_product_page",
        ),
        SourceTypeSkip(
            reason="requested_product_type_coverage_complete",
            source_type="official_marketplace_product_page",
        ),
    ]
    assert result.error_list == []
    assert result.status == "success"


def test_brand_workflow_marks_remaining_sources_skipped_after_coverage_failure(tmp_path: Path) -> None:
    """Keep the started child and parent-owned coverage failure separate.

    Args:
        tmp_path: Isolated result root.
    """

    source_type_list = [
        "official_brand_size_guide",
        "official_brand_product_page",
        "official_marketplace_product_page",
    ]
    started_result = SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="table_available",
            source_discovery_database_path="workflow/brand/official_brand_size_guide/source_discover/state.sqlite3",
        ),
        source_type="official_brand_size_guide",
        status="success",
        warning_list=[],
    )
    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    started_input_list: list[SourceTypeWorkflowInput] = []
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow.source_type_list_get = lambda prompt_scope: source_type_list
    workflow._source_type_workflow = type(
        "SourceTypeWorkflow",
        (),
        {
            "run": lambda self, execution_context, workflow_input: (
                started_input_list.append(workflow_input) or started_result
            )
        },
    )()
    workflow.coverage_decide_write_step = lambda execution_context, input_source: (_ for _ in ()).throw(
        StepResultValidationError(feedback_list=["Coverage result is incomplete."])
    )
    workflow_input = BrandWorkflowInput(
        brand_input=_input_get().brand_input,
        prompt_scope=PromptScope(product_type_request_list=["dress"]),
    )

    result = BrandSizeChartBrandWorkflow.run.__wrapped__(workflow, _context_get(tmp_path), workflow_input)

    assert started_input_list == [
        SourceTypeWorkflowInput(
            brand_input=workflow_input.brand_input,
            prompt_scope=PromptScope(product_type_request_list=[]),
            source_type="official_brand_size_guide",
        )
    ]
    assert result.source_type_result_list == [started_result]
    assert result.source_type_skip_list == [
        SourceTypeSkip(
            reason="coverage_decision_failed",
            source_type="official_brand_product_page",
        ),
        SourceTypeSkip(
            reason="coverage_decision_failed",
            source_type="official_marketplace_product_page",
        ),
    ]
    assert result.error_list == ["StepResultValidationError: Coverage result is incomplete."]
    assert result.status == "failed"
