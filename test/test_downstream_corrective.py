"""Direct behavior coverage for SQLite-backed downstream Task 4 decisions."""

import inspect
from pathlib import Path

import pytest
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext
from workflow_container_runtime.workflow import WorkflowExecutionContext, WorkflowRuntimeCapability

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    BrandOutputInput,
    BrandOutputInputSource,
    BrandOutputItem,
    BrandOutputResult,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    BrandSourceTypeResultInputSource,
    BrandSourceTypeResultStepInput,
    BrandWorkflowInput,
    CanonicalSelection,
    CanonicalSelectionActionOutput,
    CanonicalSelectionResult,
    canonical_selection_unresolved_size_group_gap_list_get,
    CoverageDecisionProductTypeGap,
    CoverageDecisionResult,
    CoveredProductType,
    PromptScope,
    SourceDiscoveryResult,
    SourceDiscoveryAcceptedTable,
    SourceDiscoveryTable,
    SourceTypeResult,
)
from brand_size_chart.source.discovery_database import (
    SOURCE_DISCOVERY_TABLE,
    SOURCE_DISCOVERY_TABLE_BY_NAME_MAP,
    SourceDiscoveryDatabaseReader,
)
from brand_size_chart.step.brand_output import BrandOutputStep
from brand_size_chart.step.canonical_selection import CanonicalSelectionStep
from brand_size_chart.step.coverage_decision import CoverageDecisionDefaultStep
from brand_size_chart.validator import BrandOutputValidator, CanonicalSelectionValidator, CoverageDecisionValidator
from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow


def _chart_get(description: str = "Chart.") -> BrandSizeChart:
    """Build one valid source chart.

    Args:
        description: Chart applicability description.

    Returns:
        Valid chart fixture.
    """

    return BrandSizeChart(
        description=description,
        row_list=[
            BrandSizeChartRow(
                measurement_list=[BrandSizeChartMeasurement(max_value="M", min_value="M", name="Size", unit="size")],
                size_label="M",
            )
        ],
    )


def _context_get(tmp_path: Path) -> WorkflowStepExecutionContext:
    """Build one isolated downstream step context.

    Args:
        tmp_path: Isolated result root.

    Returns:
        Current step context.
    """

    return WorkflowStepExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "run" / "downstream",
    )


def _workflow_input_get(product_type_request_list: list[str] | None = None) -> BrandWorkflowInput:
    """Build one stable brand workflow input.

    Args:
        product_type_request_list: Optional requested products.

    Returns:
        Typed brand workflow input.
    """

    return BrandWorkflowInput(
        brand_input=BrandInput(
            parsed_brand_key="brand",
            parsed_brand_name="Brand",
            raw_brand_name="Brand",
            source_line_number=1,
        ),
        prompt_scope=PromptScope(product_type_request_list=product_type_request_list or []),
    )


def _canonical_selection_result_get(
    action_output: CanonicalSelectionActionOutput,
    accepted_table_list: list[SourceDiscoveryAcceptedTable],
) -> CanonicalSelectionResult:
    """Build one public canonical result through the reusable gap operation.

    Args:
        action_output: Codex-owned selected chart handles.
        accepted_table_list: Accepted source-table query results.

    Returns:
        Public canonical result with Python-derived unresolved gaps.
    """

    return CanonicalSelectionResult(
        canonical_selection_list=action_output.canonical_selection_list,
        unresolved_size_group_gap_list=canonical_selection_unresolved_size_group_gap_list_get(
            canonical_selection_list=action_output.canonical_selection_list,
            accepted_table_list=accepted_table_list,
        ),
    )


def _source_type_result_write(
    *,
    chart: BrandSizeChart,
    market_scope_key: str,
    result_dir: Path,
    size_group_key: str,
    source_type: str,
) -> SourceTypeResult:
    """Write one accepted source table and return its complete successful handoff.

    Args:
        chart: Valid source chart content.
        market_scope_key: Physical source-table market identity.
        result_dir: Shared result root.
        size_group_key: Physical source-table group identity.
        source_type: Registry source type owning the database.

    Returns:
        Complete successful source-type handoff.
    """

    step_dir = result_dir / "workflow" / "run" / source_type / "source_discover"
    database_path = state_database_path_get(step_dir)
    store = SqliteStateStore()
    store.initialize(database_path, list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))
    source_table = SourceDiscoveryTable(
        evidence_path_list=["workflow/run/evidence/table.json"],
        market_scope_key=market_scope_key,
        reason="Visible table.",
        size_group_key=size_group_key,
        source_title="Size chart",
        source_url="https://brand.example/size",
        state="accepted",
    )
    store.upsert(database_path, SOURCE_DISCOVERY_TABLE, source_table)
    JsonArtifactWriter().write(
        ArtifactLayout(result_dir).source_discovery_chart_path(
            step_dir,
            source_table.size_group_key,
            source_table.market_scope_key,
        ),
        chart,
    )
    return SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="table_available",
            source_discovery_database_path=ArtifactLayout(result_dir).artifact_path(database_path),
        ),
        source_type=source_type,
        status="success",
        warning_list=[],
    )


def _step_input_get(
    result_list: list[SourceTypeResult], workflow_input: BrandWorkflowInput
) -> BrandSourceTypeResultStepInput:
    """Build one persisted downstream decision input.

    Args:
        result_list: Complete unique source-type handoffs.
        workflow_input: Stable brand workflow input.

    Returns:
        Persisted downstream input.
    """

    return BrandSourceTypeResultStepInput(source_type_result_list=result_list, workflow_input=workflow_input)


def test_coverage_validator_accepts_partition_and_rejects_overlap_unknown_and_missing(tmp_path: Path) -> None:
    """Validate coverage positive/gap partitioning against one accepted chart.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    workflow_input = _workflow_input_get(["dress", "shirt"])
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    step_input = _step_input_get([source_type_result], workflow_input)
    chart_path = (
        SourceDiscoveryDatabaseReader()
        .accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=source_type_result,
        )[0]
        .chart_path
    )
    validator = CoverageDecisionValidator(source_discovery_database_reader=SourceDiscoveryDatabaseReader())
    result = CoverageDecisionResult(
        covered_product_type_list=[
            CoveredProductType(chart_path=chart_path, product_type="dress", reason="Chart supports dress.")
        ],
        uncovered_product_type_gap_list=[
            CoverageDecisionProductTypeGap(product_type="shirt", reason="No shirt chart.")
        ],
    )

    validator.validate(context, step_input, result)

    for invalid_result in (
        result.model_copy(
            update={
                "uncovered_product_type_gap_list": [
                    CoverageDecisionProductTypeGap(product_type="dress", reason="Conflicting.")
                ]
            }
        ),
        result.model_copy(
            update={
                "covered_product_type_list": [
                    CoveredProductType(chart_path="workflow/unknown.json", product_type="dress", reason="Unknown.")
                ]
            }
        ),
        CoverageDecisionResult(covered_product_type_list=[], uncovered_product_type_gap_list=[]),
    ):
        with pytest.raises(StepResultValidationError):
            validator.validate(context, step_input, invalid_result)


def test_coverage_validator_rejects_duplicate_decisions_and_empty_reasons(tmp_path: Path) -> None:
    """Reject duplicate coverage decisions and blank positive or gap evidence reasons.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    chart_path = (
        SourceDiscoveryDatabaseReader()
        .accepted_table_list_get(result_dir=tmp_path, source_type_result=source_type_result)[0]
        .chart_path
    )
    step_input = _step_input_get([source_type_result], _workflow_input_get(["dress", "shirt"]))
    validator = CoverageDecisionValidator(source_discovery_database_reader=SourceDiscoveryDatabaseReader())
    invalid_result_list = [
        CoverageDecisionResult(
            covered_product_type_list=[
                CoveredProductType(chart_path=chart_path, product_type="dress", reason="First."),
                CoveredProductType(chart_path=chart_path, product_type="dress", reason="Second."),
            ],
            uncovered_product_type_gap_list=[CoverageDecisionProductTypeGap(product_type="shirt", reason="No chart.")],
        ),
        CoverageDecisionResult(
            covered_product_type_list=[CoveredProductType(chart_path=chart_path, product_type="dress", reason="")],
            uncovered_product_type_gap_list=[CoverageDecisionProductTypeGap(product_type="shirt", reason="No chart.")],
        ),
        CoverageDecisionResult(
            covered_product_type_list=[
                CoveredProductType(chart_path=chart_path, product_type="dress", reason="Chart.")
            ],
            uncovered_product_type_gap_list=[
                CoverageDecisionProductTypeGap(product_type="shirt", reason="First gap."),
                CoverageDecisionProductTypeGap(product_type="shirt", reason="Second gap."),
            ],
        ),
        CoverageDecisionResult(
            covered_product_type_list=[
                CoveredProductType(chart_path=chart_path, product_type="dress", reason="Chart.")
            ],
            uncovered_product_type_gap_list=[CoverageDecisionProductTypeGap(product_type="shirt", reason="")],
        ),
    ]

    for invalid_result in invalid_result_list:
        with pytest.raises(StepResultValidationError):
            validator.validate(context, step_input, invalid_result)


def test_coverage_default_step_returns_requested_gaps_when_no_table_is_available(tmp_path: Path) -> None:
    """Produce normal non-error gaps when no source result provides accepted charts.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    workflow_input = _workflow_input_get(["dress"])
    no_table_result = SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="no_table",
            source_discovery_database_path="workflow/run/source/source_discover/state.sqlite3",
        ),
        source_type="official_brand_size_guide",
        status="success",
        warning_list=[],
    )
    validator = CoverageDecisionValidator(source_discovery_database_reader=SourceDiscoveryDatabaseReader())
    step = CoverageDecisionDefaultStep(artifact_writer=JsonArtifactWriter(), validator=validator)
    step_input = _step_input_get([no_table_result], workflow_input)

    result = step.result_build(context, step_input)

    assert result.covered_product_type_list == []
    assert [gap.product_type for gap in result.uncovered_product_type_gap_list] == ["dress"]
    step.result_validate(context, step_input, result)


def test_canonical_validator_enforces_priority_tie_order_and_unresolved_gap(tmp_path: Path) -> None:
    """Validate sole winner, lower-priority rejection, deterministic tie, and unresolved tie.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    high_result = _source_type_result_write(
        chart=_chart_get("High."),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    low_result = _source_type_result_write(
        chart=_chart_get("Low."),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_seller_size_guide",
    )
    validator = CanonicalSelectionValidator(source_discovery_database_reader=SourceDiscoveryDatabaseReader())
    step_input = _step_input_get([high_result, low_result], _workflow_input_get())
    accepted_table_list = [
        accepted_table
        for source_type_result in step_input.source_type_result_list
        for accepted_table in SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=source_type_result,
        )
    ]
    high_chart_path = max(accepted_table_list, key=lambda accepted_table: accepted_table.source_priority).chart_path
    low_chart_path = min(accepted_table_list, key=lambda accepted_table: accepted_table.source_priority).chart_path
    selected_result = _canonical_selection_result_get(
        CanonicalSelectionActionOutput(
            canonical_selection_list=[CanonicalSelection(selected_chart_path=high_chart_path)]
        ),
        accepted_table_list,
    )

    validator.validate(context, step_input, selected_result)
    with pytest.raises(StepResultValidationError, match="highest source priority"):
        validator.validate(
            context,
            step_input,
            _canonical_selection_result_get(
                CanonicalSelectionActionOutput(
                    canonical_selection_list=[CanonicalSelection(selected_chart_path=low_chart_path)]
                ),
                accepted_table_list,
            ),
        )

    tie_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="eu",
        result_dir=tmp_path,
        size_group_key="women_shirt",
        source_type="official_brand_product_page",
    )
    tie_step_dir = tmp_path / "workflow" / "run" / "official_brand_product_page" / "source_discover"
    second_tie_chart = _chart_get()
    store = SqliteStateStore()
    store.upsert(
        state_database_path_get(tie_step_dir),
        SOURCE_DISCOVERY_TABLE,
        SourceDiscoveryTable(
            evidence_path_list=["workflow/run/evidence/table.json"],
            market_scope_key="tr",
            reason="Visible table.",
            size_group_key="women_shirt",
            source_title="Size chart",
            source_url="https://brand.example/size",
            state="accepted",
        ),
    )
    JsonArtifactWriter().write(
        ArtifactLayout(tmp_path).source_discovery_chart_path(tie_step_dir, "women_shirt", "tr"),
        second_tie_chart,
    )
    tie_input = _step_input_get([tie_result], _workflow_input_get())
    tie_accepted_table_list = SourceDiscoveryDatabaseReader().accepted_table_list_get(
        result_dir=tmp_path,
        source_type_result=tie_result,
    )
    deterministic_chart_path = min(
        tie_accepted_table_list,
        key=lambda accepted_table: (
            accepted_table.source_table.market_scope_key,
            accepted_table.source_table.source_url,
            accepted_table.source_table.source_title,
        ),
    ).chart_path
    deterministic_result = _canonical_selection_result_get(
        CanonicalSelectionActionOutput(
            canonical_selection_list=[CanonicalSelection(selected_chart_path=deterministic_chart_path)]
        ),
        tie_accepted_table_list,
    )
    validator.validate(context, tie_input, deterministic_result)
    unresolved_result = _canonical_selection_result_get(
        CanonicalSelectionActionOutput(canonical_selection_list=[]), tie_accepted_table_list
    )
    validator.validate(context, tie_input, unresolved_result)


def test_canonical_gap_candidates_follow_domain_order_when_chart_paths_disagree() -> None:
    """Order unresolved tied candidates by source identity rather than chart path."""

    accepted_table_list = [
        SourceDiscoveryAcceptedTable(
            chart_path="workflow/z-chart.json",
            source_priority=600,
            source_table=SourceDiscoveryTable(
                evidence_path_list=["workflow/evidence/de.json"],
                market_scope_key="de",
                reason="German source.",
                size_group_key="women_dress",
                source_title="German chart",
                source_url="https://brand.example/de",
                state="accepted",
            ),
            source_type="official_brand_size_guide",
        ),
        SourceDiscoveryAcceptedTable(
            chart_path="workflow/a-chart.json",
            source_priority=600,
            source_table=SourceDiscoveryTable(
                evidence_path_list=["workflow/evidence/tr.json"],
                market_scope_key="tr",
                reason="Turkish source.",
                size_group_key="women_dress",
                source_title="Turkish chart",
                source_url="https://brand.example/tr",
                state="accepted",
            ),
            source_type="official_brand_size_guide",
        ),
    ]

    gap_list = canonical_selection_unresolved_size_group_gap_list_get(
        canonical_selection_list=[],
        accepted_table_list=accepted_table_list,
    )

    assert gap_list[0].candidate_chart_path_list == ["workflow/z-chart.json", "workflow/a-chart.json"]


def test_canonical_validator_rejects_unknown_and_duplicate_selection(tmp_path: Path) -> None:
    """Reject selections that are absent from accepted rows or repeat one chart.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    chart_path = (
        SourceDiscoveryDatabaseReader()
        .accepted_table_list_get(result_dir=tmp_path, source_type_result=source_type_result)[0]
        .chart_path
    )
    step_input = _step_input_get([source_type_result], _workflow_input_get())
    validator = CanonicalSelectionValidator(source_discovery_database_reader=SourceDiscoveryDatabaseReader())
    for selection_list in (
        [CanonicalSelection(selected_chart_path="workflow/unknown.json")],
        [CanonicalSelection(selected_chart_path=chart_path), CanonicalSelection(selected_chart_path=chart_path)],
    ):
        with pytest.raises(StepResultValidationError):
            validator.validate(
                context,
                step_input,
                CanonicalSelectionResult(canonical_selection_list=selection_list, unresolved_size_group_gap_list=[]),
            )


def test_canonical_step_builds_result_directly_from_injected_reader(tmp_path: Path) -> None:
    """Build a public selection and gap from real accepted rows without validator query methods.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    step_input = _step_input_get([source_type_result], _workflow_input_get())
    chart_path = (
        SourceDiscoveryDatabaseReader()
        .accepted_table_list_get(result_dir=tmp_path, source_type_result=source_type_result)[0]
        .chart_path
    )
    step = CanonicalSelectionStep.__new__(CanonicalSelectionStep)
    step._source_discovery_database_reader = SourceDiscoveryDatabaseReader()

    result = CanonicalSelectionStep.result_from_action_build(
        step,
        context,
        step_input,
        CanonicalSelectionActionOutput(canonical_selection_list=[CanonicalSelection(selected_chart_path=chart_path)]),
    )

    assert result.canonical_selection_list == [CanonicalSelection(selected_chart_path=chart_path)]
    assert result.unresolved_size_group_gap_list == []


def test_canonical_validator_exposes_validate_as_its_only_public_boundary() -> None:
    """Keep accepted-row querying outside the canonical mechanical validator."""

    assert tuple(
        name
        for name, member in inspect.getmembers(CanonicalSelectionValidator, inspect.isfunction)
        if not name.startswith("_")
    ) == ("validate",)


def test_brand_output_preflights_containment_and_preserves_source_content(tmp_path: Path) -> None:
    """Publish a two-component final path and reject source escapes before writes.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    reader = SourceDiscoveryDatabaseReader()
    source_chart_path = reader.accepted_table_list_get(result_dir=tmp_path, source_type_result=source_type_result)[
        0
    ].chart_path
    step = BrandOutputStep.__new__(BrandOutputStep)
    step._artifact_writer = JsonArtifactWriter()
    step._source_discovery_database_reader = reader
    step._validator = BrandOutputValidator()
    input_source = BrandOutputInputSource(
        canonical_selection_result=CanonicalSelectionResult(
            canonical_selection_list=[CanonicalSelection(selected_chart_path=source_chart_path)],
            unresolved_size_group_gap_list=[],
        ),
        source_type_result_list=[source_type_result],
        workflow_input=_workflow_input_get(),
    )
    step_input = BrandOutputStep.input_build(step, context, input_source)
    result = BrandOutputStep.result_build(step, context, step_input)

    assert result.size_chart_path_list == ["brand_size_chart/brand/brand/size_chart/women_dress__tr.json"]
    BrandOutputStep.result_validate(step, context, step_input, result)
    final_path = tmp_path / result.size_chart_path_list[0]
    final_path.write_text(_chart_get("Changed.").model_dump_json(), encoding="utf-8")
    with pytest.raises(StepResultValidationError, match="exactly equal"):
        BrandOutputStep.result_validate(step, context, step_input, result)

    external_chart_path = tmp_path.parent / "external-chart.json"
    external_chart_path.write_text(_chart_get().model_dump_json(), encoding="utf-8")
    escape_path = tmp_path / "source-chart-escape.json"
    escape_path.symlink_to(external_chart_path)
    escaped_input = BrandOutputInput(
        output_item_list=[
            BrandOutputItem(
                output_write_target=ArtifactWriteTarget(
                    artifact_path="brand_size_chart/brand/brand/size_chart/women_dress__tr.json",
                    filesystem_path=final_path.as_posix(),
                ),
                source_chart_path=escape_path.relative_to(tmp_path).as_posix(),
            )
        ]
    )
    with pytest.raises(RuntimeError, match="escapes result_dir"):
        BrandOutputStep.result_build(step, context, escaped_input)

    external_target_path = tmp_path.parent / "external-target.json"
    target_escape_path = tmp_path / "target-escape.json"
    target_escape_path.symlink_to(external_target_path)
    target_escaped_input = BrandOutputInput(
        output_item_list=[
            BrandOutputItem(
                output_write_target=ArtifactWriteTarget(
                    artifact_path="target-escape.json",
                    filesystem_path=target_escape_path.as_posix(),
                ),
                source_chart_path=source_chart_path,
            )
        ]
    )
    with pytest.raises(RuntimeError, match="target escapes result_dir"):
        BrandOutputStep.result_build(step, context, target_escaped_input)


def test_brand_output_rejects_unknown_selection_and_invalid_source_chart(tmp_path: Path) -> None:
    """Reject unknown canonical sources and malformed selected source charts before publication.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    reader = SourceDiscoveryDatabaseReader()
    step = BrandOutputStep.__new__(BrandOutputStep)
    step._artifact_writer = JsonArtifactWriter()
    step._source_discovery_database_reader = reader
    step._validator = BrandOutputValidator()
    with pytest.raises(RuntimeError, match="unknown accepted chart"):
        BrandOutputStep.input_build(
            step,
            context,
            BrandOutputInputSource(
                canonical_selection_result=CanonicalSelectionResult(
                    canonical_selection_list=[CanonicalSelection(selected_chart_path="workflow/unknown.json")],
                    unresolved_size_group_gap_list=[],
                ),
                source_type_result_list=[source_type_result],
                workflow_input=_workflow_input_get(),
            ),
        )

    source_chart_path = reader.accepted_table_list_get(result_dir=tmp_path, source_type_result=source_type_result)[
        0
    ].chart_path
    source_chart = tmp_path / source_chart_path
    source_chart.write_text("{}", encoding="utf-8")
    invalid_source_input = BrandOutputInput(
        output_item_list=[
            BrandOutputItem(
                output_write_target=ArtifactWriteTarget(
                    artifact_path="brand_size_chart/brand/brand/size_chart/women_dress__tr.json",
                    filesystem_path=(
                        tmp_path / "brand_size_chart" / "brand" / "brand" / "size_chart" / "women_dress__tr.json"
                    ).as_posix(),
                ),
                source_chart_path=source_chart_path,
            )
        ]
    )
    with pytest.raises(RuntimeError, match="missing or invalid"):
        BrandOutputStep.result_build(step, context, invalid_source_input)


def test_brand_workflow_keeps_coverage_gaps_out_of_error_list(tmp_path: Path) -> None:
    """Treat normal coverage gaps as a successful brand workflow decision.

    Args:
        tmp_path: Isolated result root.
    """

    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    source_type_result = SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="table_available",
            source_discovery_database_path="workflow/run/source/source_discover/state.sqlite3",
        ),
        source_type="official_brand_size_guide",
        status="success",
        warning_list=[],
    )
    workflow.input_write_step = lambda execution_context, workflow_input: None
    workflow.result_write_step = lambda execution_context, workflow_input, workflow_result: workflow_result
    workflow.source_type_list_get = lambda prompt_scope: ["official_brand_size_guide"]
    workflow._source_type_workflow = type(
        "SourceTypeWorkflow",
        (),
        {"run": lambda self, execution_context, workflow_input: source_type_result},
    )()
    workflow.coverage_decide_write_step = lambda execution_context, input_source: CoverageDecisionResult(
        covered_product_type_list=[],
        uncovered_product_type_gap_list=[CoverageDecisionProductTypeGap(product_type="dress", reason="No chart.")],
    )
    workflow.canonical_select_write_step = lambda execution_context, input_source: CanonicalSelectionResult(
        canonical_selection_list=[],
        unresolved_size_group_gap_list=[],
    )
    workflow.brand_output_write_step = lambda execution_context, input_source: BrandOutputResult(
        size_chart_path_list=[]
    )
    context = WorkflowExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        workflow_instance_dir=tmp_path / "workflow" / "run" / "brand",
    )

    result = BrandSizeChartBrandWorkflow.run.__wrapped__(workflow, context, _workflow_input_get(["dress"]))

    assert result.error_list == []
    assert result.status == "success"
    assert result.coverage_decision_result.uncovered_product_type_gap_list[0].product_type == "dress"


def test_brand_workflow_routes_complete_results_through_real_downstream_step_methods(tmp_path: Path) -> None:
    """Route complete source results to default and semantic downstream step owners.

    Args:
        tmp_path: Isolated result root.
    """

    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    context = _context_get(tmp_path)
    no_table_result = SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="no_table",
            source_discovery_database_path="workflow/run/source/source_discover/state.sqlite3",
        ),
        source_type="official_brand_size_guide",
        status="success",
        warning_list=[],
    )
    table_result = no_table_result.model_copy(
        update={
            "source_discovery_result": no_table_result.source_discovery_result.model_copy(
                update={"outcome": "table_available"}
            )
        }
    )
    record_list: list[tuple[str, BrandSourceTypeResultStepInput]] = []

    class RecordingStep:
        """Record one workflow-selected downstream input and return its declared result."""

        def __init__(self, *, result: CanonicalSelectionResult | CoverageDecisionResult, have_candidate: bool) -> None:
            """Store the selected branch result.

            Args:
                result: Result returned when the workflow invokes this step.
                have_candidate: Canonical candidate availability for this branch.
            """

            self._have_candidate = have_candidate
            self._result = result

        def have_candidate(self, input_source: BrandSourceTypeResultInputSource) -> bool:
            """Return the configured canonical branch condition.

            Args:
                input_source: Complete downstream source-result handoff.

            Returns:
                Whether the semantic canonical branch should run.
            """

            record_list.append(
                ("candidate", _step_input_get(input_source.source_type_result_list, input_source.workflow_input))
            )
            return self._have_candidate

        def run(
            self,
            execution_context: WorkflowStepExecutionContext,
            input_source: BrandSourceTypeResultInputSource,
        ) -> CanonicalSelectionResult | CoverageDecisionResult:
            """Record the exact source-result handoff and return the configured result.

            Args:
                execution_context: Current workflow-created downstream step context.
                input_source: Complete downstream source-result handoff.

            Returns:
                Configured direct step result.
            """

            _ = execution_context
            record_list.append(
                ("run", _step_input_get(input_source.source_type_result_list, input_source.workflow_input))
            )
            return self._result

    coverage_result = CoverageDecisionResult(
        covered_product_type_list=[],
        uncovered_product_type_gap_list=[CoverageDecisionProductTypeGap(product_type="dress", reason="No chart.")],
    )
    canonical_result = CanonicalSelectionResult(canonical_selection_list=[], unresolved_size_group_gap_list=[])
    workflow._coverage_decision_default_step = RecordingStep(result=coverage_result, have_candidate=False)
    workflow._coverage_decision_step = RecordingStep(result=coverage_result, have_candidate=False)
    workflow._canonical_selection_default_step = RecordingStep(result=canonical_result, have_candidate=False)
    workflow._canonical_selection_step = RecordingStep(result=canonical_result, have_candidate=True)
    workflow_input = _workflow_input_get(["dress"])

    assert (
        BrandSizeChartBrandWorkflow.coverage_decide_write_step.__wrapped__(
            workflow,
            context,
            BrandSourceTypeResultInputSource(source_type_result_list=[no_table_result], workflow_input=workflow_input),
        )
        == coverage_result
    )
    assert (
        BrandSizeChartBrandWorkflow.coverage_decide_write_step.__wrapped__(
            workflow,
            context,
            BrandSourceTypeResultInputSource(source_type_result_list=[table_result], workflow_input=workflow_input),
        )
        == coverage_result
    )
    assert (
        BrandSizeChartBrandWorkflow.canonical_select_write_step.__wrapped__(
            workflow,
            context,
            BrandSourceTypeResultInputSource(source_type_result_list=[no_table_result], workflow_input=workflow_input),
        )
        == canonical_result
    )
    assert (
        BrandSizeChartBrandWorkflow.canonical_select_write_step.__wrapped__(
            workflow,
            context,
            BrandSourceTypeResultInputSource(source_type_result_list=[table_result], workflow_input=workflow_input),
        )
        == canonical_result
    )
    assert all(record[1].source_type_result_list[0] in [no_table_result, table_result] for record in record_list)
