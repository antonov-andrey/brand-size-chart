"""Behavior tests for the typed workflow result tree."""

from pathlib import Path
from types import SimpleNamespace

from workflow_container_runtime.step import StepResultValidationError
from workflow_container_runtime.workflow import WorkflowExecutionContext, WorkflowRuntimeCapability

from brand_size_chart.model import (
    BrandInput,
    BrandOutputResult,
    BrandResult,
    BrandWorkflowInput,
    CanonicalSelectionResult,
    CoverageDecisionProductTypeGap,
    CoverageDecisionResult,
    CoveredProductType,
    PromptScope,
    RunInput,
    SourceDiscovery,
    SourceDiscoveryResult,
    SourceTypeSkip,
    SourceTypeResult,
    SourceTypeWorkflowInput,
    TableExtractionArtifact,
    TableExtractionResult,
)
from brand_size_chart.workflow import BrandSizeChartBrandWorkflow, BrandSizeChartRunWorkflow
from brand_size_chart.workflow.source_type import BrandSizeChartSourceTypeWorkflow


def _execution_context_get(tmp_path: Path, workflow_key: str) -> WorkflowExecutionContext:
    """Build one isolated workflow execution context.

    Args:
        tmp_path: Pytest temporary directory.
        workflow_key: Workflow instance key.

    Returns:
        Isolated workflow execution context.
    """

    result_dir = (tmp_path / "result").resolve()
    return WorkflowExecutionContext(
        result_dir=result_dir,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        workflow_instance_dir=result_dir / "workflow" / workflow_key,
    )


def _brand_input_get() -> BrandInput:
    """Build one stable brand identity for workflow tests.

    Returns:
        Brand input fixture.
    """

    return BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )


def _brand_result_get(*, status: str, error_list: list[str]) -> BrandResult:
    """Build one nested brand result.

    Args:
        status: Workflow result status.
        error_list: Brand-owned errors.

    Returns:
        Brand result fixture.
    """

    return BrandResult(
        brand_output_result=BrandOutputResult(size_chart_path_list=[]),
        canonical_selection_result=CanonicalSelectionResult(
            canonical_selection_list=[],
            unresolved_size_group_gap_list=[],
        ),
        coverage_decision_result=CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[],
        ),
        error_list=error_list,
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        source_type_result_list=[],
        source_type_skip_list=[],
        status=status,
        warning_list=[],
    )


def test_source_type_no_table_is_successful_structured_result(tmp_path: Path) -> None:
    """Keep a verified no-table conclusion as a successful source-type result."""

    workflow = BrandSizeChartSourceTypeWorkflow.__new__(BrandSizeChartSourceTypeWorkflow)
    source_discovery_result = SourceDiscoveryResult(
        browsing_error_list=[],
        source_discovery_list=[],
        warning_list=["The selected official source contains no applicable size table."],
    )
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow.source_discover_write_step = lambda execution_context, input_source: source_discovery_result
    workflow.table_extract_write_step = lambda execution_context, input_source: (_ for _ in ()).throw(
        AssertionError("table extraction must not run without discovered tables")
    )

    result = BrandSizeChartSourceTypeWorkflow.run.__wrapped__(
        workflow,
        _execution_context_get(tmp_path, "source_type"),
        SourceTypeWorkflowInput(
            brand_input=_brand_input_get(),
            prompt_scope=PromptScope(),
            source_type="official_brand_size_guide",
        ),
    )

    assert result == SourceTypeResult(
        error_list=[],
        source_discovery_result=source_discovery_result,
        source_type="official_brand_size_guide",
        status="success",
        table_extraction_result=None,
        warning_list=[],
    )


def test_brand_partial_coverage_and_child_failure_are_not_brand_errors(tmp_path: Path) -> None:
    """Preserve child failure and coverage gaps without failing the brand workflow."""

    child_failure = SourceTypeResult(
        error_list=["CodexExecutionError: target source was unreachable"],
        source_discovery_result=None,
        source_type="official_brand_size_guide",
        status="failed",
        table_extraction_result=None,
        warning_list=[],
    )
    coverage_result = CoverageDecisionResult(
        covered_product_type_list=[],
        uncovered_product_type_gap_list=[
            CoverageDecisionProductTypeGap(
                product_type="dress",
                reason="No verified table applies to this product type.",
            )
        ],
    )
    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow._source_type_workflow = SimpleNamespace(
        run=lambda execution_context, workflow_input: child_failure,
    )
    workflow.coverage_decide_write_step = lambda execution_context, input_source: coverage_result
    workflow.canonical_select_write_step = lambda execution_context, input_source: CanonicalSelectionResult(
        canonical_selection_list=[],
        unresolved_size_group_gap_list=[],
    )
    workflow.brand_output_write_step = lambda execution_context, input_source: BrandOutputResult(
        size_chart_path_list=[]
    )

    result = BrandSizeChartBrandWorkflow.run.__wrapped__(
        workflow,
        _execution_context_get(tmp_path, "brand"),
        BrandWorkflowInput(
            brand_input=_brand_input_get(),
            prompt_scope=PromptScope(
                product_type_request_list=["dress"],
                source_type_allow_list=["official_brand_size_guide"],
            ),
        ),
    )

    assert result.status == "success"
    assert result.error_list == []
    assert result.coverage_decision_result == coverage_result
    assert result.source_type_result_list == [child_failure]
    assert result.source_type_skip_list == []


def test_brand_owned_step_failure_produces_failed_brand_result(tmp_path: Path) -> None:
    """Fail only the brand owner when one of its own steps exhausts correction."""

    table_extraction_result = TableExtractionResult(
        browsing_error_list=[],
        table_extraction_list=[
            TableExtractionArtifact(
                applicability_description="Applies to dresses.",
                chart_path="workflow/brand_failed/step/table_extract/chart/women_dresses.json",
                evidence_path_list=["workflow/brand_failed/step/table_extract/evidence/women_dresses.json"],
                source_discovery=SourceDiscovery(
                    country_code_list=["TR"],
                    size_group_key="women_dresses",
                    source_title="Kadin Elbise Beden Tablosu",
                    source_url="https://www.defacto.com.tr/size-guide",
                ),
                source_type="official_brand_size_guide",
            )
        ],
    )
    source_type_result = SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            source_discovery_list=[],
            warning_list=["No applicable table was found."],
        ),
        source_type="official_brand_size_guide",
        status="success",
        table_extraction_result=table_extraction_result,
        warning_list=[],
    )
    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow._source_type_workflow = SimpleNamespace(
        run=lambda execution_context, workflow_input: source_type_result,
    )
    workflow.coverage_decide_write_step = lambda execution_context, input_source: (_ for _ in ()).throw(
        StepResultValidationError(feedback_list=["Coverage evidence is incomplete."])
    )

    result = BrandSizeChartBrandWorkflow.run.__wrapped__(
        workflow,
        _execution_context_get(tmp_path, "brand_failed"),
        BrandWorkflowInput(
            brand_input=_brand_input_get(),
            prompt_scope=PromptScope(
                product_type_request_list=["dress"],
                source_type_allow_list=[
                    "official_brand_size_guide",
                    "official_brand_product_page",
                ],
            ),
        ),
    )

    assert result.status == "failed"
    assert result.error_list == ["StepResultValidationError: Coverage evidence is incomplete."]
    assert result.coverage_decision_result is None
    assert result.canonical_selection_result is None
    assert result.brand_output_result is None
    assert result.source_type_result_list == [source_type_result]
    assert result.source_type_skip_list == [
        SourceTypeSkip(
            reason="coverage_decision_failed",
            source_type="official_brand_product_page",
        )
    ]


def test_brand_recomputes_coverage_only_when_current_source_adds_tables(tmp_path: Path) -> None:
    """Avoid repeated semantic coverage over an unchanged verified-table set."""

    source_type_call_list: list[str] = []
    coverage_call_count = 0
    table_extraction_result = TableExtractionResult(
        browsing_error_list=[],
        table_extraction_list=[
            TableExtractionArtifact(
                applicability_description="Applies to women's dresses.",
                chart_path="workflow/brand/step/table_extract/chart/women_dresses.json",
                evidence_path_list=["workflow/brand/step/table_extract/evidence/women_dresses.json"],
                source_discovery=SourceDiscovery(
                    country_code_list=["TR"],
                    size_group_key="women_dresses",
                    source_title="Kadin Elbise Beden Tablosu",
                    source_url="https://www.defacto.com.tr/size-guide",
                ),
                source_type="official_brand_size_guide",
            )
        ],
    )

    def source_type_run(
        execution_context: WorkflowExecutionContext, workflow_input: SourceTypeWorkflowInput
    ) -> SourceTypeResult:
        """Return one table only from the first general source.

        Args:
            execution_context: Child workflow context.
            workflow_input: Source-type workflow input.

        Returns:
            Source-type result fixture.
        """

        _ = execution_context
        source_type_call_list.append(workflow_input.source_type)
        return SourceTypeResult(
            error_list=[],
            source_discovery_result=SourceDiscoveryResult(
                browsing_error_list=[],
                source_discovery_list=[],
                warning_list=[],
            ),
            source_type=workflow_input.source_type,
            status="success",
            table_extraction_result=(
                table_extraction_result if workflow_input.source_type == "official_brand_size_guide" else None
            ),
            warning_list=[],
        )

    def coverage_decide(
        execution_context: object,
        input_source: object,
    ) -> CoverageDecisionResult:
        """Return complete coverage and count semantic calls.

        Args:
            execution_context: Coverage step context.
            input_source: Coverage dependency set.

        Returns:
            Complete coverage result.
        """

        nonlocal coverage_call_count
        _ = execution_context
        _ = input_source
        coverage_call_count += 1
        return CoverageDecisionResult(
            covered_product_type_list=[
                CoveredProductType(
                    chart_path=table_extraction_result.table_extraction_list[0].chart_path,
                    product_type="dress",
                    reason="The verified dress table explicitly applies to dresses.",
                )
            ],
            uncovered_product_type_gap_list=[],
        )

    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow._source_type_workflow = SimpleNamespace(run=source_type_run)
    workflow.coverage_decide_write_step = coverage_decide
    workflow.canonical_select_write_step = lambda execution_context, input_source: CanonicalSelectionResult(
        canonical_selection_list=[],
        unresolved_size_group_gap_list=[],
    )
    workflow.brand_output_write_step = lambda execution_context, input_source: BrandOutputResult(
        size_chart_path_list=[]
    )

    result = BrandSizeChartBrandWorkflow.run.__wrapped__(
        workflow,
        _execution_context_get(tmp_path, "brand_coverage"),
        BrandWorkflowInput(
            brand_input=_brand_input_get(),
            prompt_scope=PromptScope(
                product_type_request_list=["dress"],
                source_type_allow_list=[
                    "official_brand_size_guide",
                    "official_seller_size_guide",
                    "official_brand_product_page",
                ],
            ),
        ),
    )

    assert source_type_call_list == [
        "official_brand_size_guide",
        "official_seller_size_guide",
    ]
    assert coverage_call_count == 1
    assert result.source_type_skip_list == [
        SourceTypeSkip(
            reason="requested_product_type_coverage_complete",
            source_type="official_brand_product_page",
        )
    ]


def test_root_keeps_failed_brand_as_nested_result_without_failing_run(tmp_path: Path) -> None:
    """Keep one failed child brand in a successful root orchestration result."""

    failed_brand_result = _brand_result_get(status="failed", error_list=["brand output validation failed"])
    workflow = BrandSizeChartRunWorkflow.__new__(BrandSizeChartRunWorkflow)
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow.prompt_scope_write_step = lambda execution_context, input_source: PromptScope()
    workflow._brand_workflow = SimpleNamespace(
        run=lambda execution_context, workflow_input: failed_brand_result,
    )

    result = BrandSizeChartRunWorkflow.run.__wrapped__(
        workflow,
        _execution_context_get(tmp_path, "run"),
        RunInput(brand_list_text="Defacto\nDefacto\n", workflow_run_prompt=""),
    )

    assert result.status == "success"
    assert result.error_list == []
    assert result.brand_result_list == [failed_brand_result]
    assert len(result.brand_list_parse_warning_list) == 1
    assert result.brand_list_parse_warning_list[0].warning_type == "duplicate_brand"
