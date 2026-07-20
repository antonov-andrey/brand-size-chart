"""Downstream decision behavior over current runtime-owned workflow input."""

import asyncio
from datetime import UTC, datetime
import inspect
from pathlib import Path

import pytest
from workflow_container_contract import WorkflowRunContext
from workflow_container_runtime.artifact import JsonArtifactWriter, JsonLinesArtifactWriter
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
from workflow_container_runtime.step import (
    StepResultValidationError,
    WorkflowStepExecutionContext,
    WorkflowStepInvocationOutcome,
)
from workflow_container_runtime.workflow import WorkflowDataPath, WorkflowExecutionContext, WorkflowRuntimeCapability

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    BrandOutputInput,
    BrandOutputInputSource,
    BrandOutputItem,
    BrandOutputResult,
    BrandResult,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    BrandSourceTypeResultInputSource,
    BrandSourceTypeResultStepInput,
    CanonicalSelection,
    CanonicalSelectionActionOutput,
    CanonicalSelectionResult,
    CoverageDecisionProductTypeGap,
    CoverageDecisionResult,
    CoveredProductType,
    SourceDiscoveryResult,
    SourceDiscoveryAcceptedTable,
    SourceDiscoveryTable,
    SourceTypeResult,
    WorkflowBrandSizeChartConfig,
    WorkflowBrandSizeChartInput,
    WorkflowBrandSizeChartRequest,
    WorkflowBrandSizeChartStepMap,
    WorkflowStepCanonicalSelectConfig,
    WorkflowStepCoverageDecideConfig,
    WorkflowStepSourceDiscoverConfig,
    canonical_selection_unresolved_size_group_gap_list_get,
)
from brand_size_chart.source.discovery_database import (
    SOURCE_DISCOVERY_TABLE,
    SOURCE_DISCOVERY_TABLE_BY_NAME_MAP,
    SourceDiscoveryDatabaseReader,
)
from brand_size_chart.step import BrandOutputStep, CanonicalSelectionStep, CoverageDecisionDefaultStep
from brand_size_chart.validator import BrandOutputValidator, CanonicalSelectionValidator, CoverageDecisionValidator
from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow


def test_coverage_validator_accepts_partition_and_rejects_overlap_unknown_and_missing(tmp_path: Path) -> None:
    """Validate complete requested coverage through persisted workflow input."""

    context = _context_get(tmp_path)
    _workflow_input_write(context, _workflow_input_get(["dress", "shirt"]))
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    step_input = _step_input_get(context, [source_type_result])
    chart_path = _accepted_table_list_get(tmp_path, [source_type_result])[0].chart_path
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
    """Reject duplicate decisions and empty evidence reasons from a persisted input path."""

    context = _context_get(tmp_path)
    _workflow_input_write(context, _workflow_input_get(["dress", "shirt"]))
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    chart_path = _accepted_table_list_get(tmp_path, [source_type_result])[0].chart_path
    step_input = _step_input_get(context, [source_type_result])
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
    """Produce structured normal gaps through the workflow-input artifact path."""

    context = _context_get(tmp_path)
    _workflow_input_write(context, _workflow_input_get(["dress"]))
    no_table_result = _source_type_result_get(
        database_path="workflow/run/source/source_discover/state.sqlite3",
        outcome="no_table",
        source_type="official_brand_size_guide",
    )
    validator = CoverageDecisionValidator(source_discovery_database_reader=SourceDiscoveryDatabaseReader())
    step = CoverageDecisionDefaultStep(artifact_writer=JsonArtifactWriter(), validator=validator)
    step_input = _step_input_get(context, [no_table_result])

    result = step.result_build(context, step_input)

    assert result.covered_product_type_list == []
    assert result.uncovered_product_type_gap_list == [
        CoverageDecisionProductTypeGap(
            product_type="dress",
            reason="No accepted source table is available for this requested product type.",
        )
    ]
    step.result_validate(context, step_input, result)


def test_canonical_validator_enforces_priority_tie_order_and_unresolved_gap(tmp_path: Path) -> None:
    """Validate priority selection and deterministic unresolved same-priority groups."""

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
    step_input = _step_input_get(context, [high_result, low_result])
    accepted_table_list = _accepted_table_list_get(tmp_path, [high_result, low_result])
    high_chart_path = max(accepted_table_list, key=lambda accepted_table: accepted_table.source_priority).chart_path
    low_chart_path = min(accepted_table_list, key=lambda accepted_table: accepted_table.source_priority).chart_path
    selected_result = _canonical_selection_result_get(
        [CanonicalSelection(selected_chart_path=high_chart_path)], accepted_table_list
    )

    validator.validate(context, step_input, selected_result)
    with pytest.raises(StepResultValidationError, match="highest source priority"):
        validator.validate(
            context,
            step_input,
            _canonical_selection_result_get(
                [CanonicalSelection(selected_chart_path=low_chart_path)], accepted_table_list
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
    _source_table_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_shirt",
        step_dir=tie_step_dir,
    )
    tie_step_input = _step_input_get(context, [tie_result])
    tie_accepted_table_list = _accepted_table_list_get(tmp_path, [tie_result])
    deterministic_chart_path = min(
        tie_accepted_table_list,
        key=lambda accepted_table: (
            accepted_table.source_table.market_scope_key,
            accepted_table.source_table.source_url,
            accepted_table.source_table.source_title,
        ),
    ).chart_path
    deterministic_result = _canonical_selection_result_get(
        [CanonicalSelection(selected_chart_path=deterministic_chart_path)], tie_accepted_table_list
    )

    validator.validate(context, tie_step_input, deterministic_result)
    unresolved_result = _canonical_selection_result_get([], tie_accepted_table_list)
    validator.validate(context, tie_step_input, unresolved_result)


def test_canonical_gap_candidates_follow_domain_order_when_chart_paths_disagree() -> None:
    """Order unresolved candidates by source identity instead of their artifact handles."""

    accepted_table_list = [
        _accepted_table_get(
            chart_path="workflow/z-chart.json", market_scope_key="de", source_url="https://brand.example/de"
        ),
        _accepted_table_get(
            chart_path="workflow/a-chart.json", market_scope_key="tr", source_url="https://brand.example/tr"
        ),
    ]

    assert [
        gap.model_dump(mode="json")
        for gap in canonical_selection_unresolved_size_group_gap_list_get(
            canonical_selection_list=[], accepted_table_list=accepted_table_list
        )
    ] == [
        {
            "candidate_chart_path_list": ["workflow/z-chart.json", "workflow/a-chart.json"],
            "size_group_key": "women_dress",
        }
    ]


def test_canonical_validator_rejects_unknown_and_duplicate_selection(tmp_path: Path) -> None:
    """Reject canonical selections outside accepted SQLite rows or repeated selections."""

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    chart_path = _accepted_table_list_get(tmp_path, [source_type_result])[0].chart_path
    step_input = _step_input_get(context, [source_type_result])
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
    """Build public selection gaps using the injected SQLite accepted-table reader."""

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    step_input = _step_input_get(context, [source_type_result])
    chart_path = _accepted_table_list_get(tmp_path, [source_type_result])[0].chart_path
    step = CanonicalSelectionStep.__new__(CanonicalSelectionStep)
    step._source_discovery_database_reader = SourceDiscoveryDatabaseReader()

    result = CanonicalSelectionStep.result_from_action_build(
        step,
        context,
        step_input,
        CanonicalSelectionActionOutput(canonical_selection_list=[CanonicalSelection(selected_chart_path=chart_path)]),
    )

    assert result == CanonicalSelectionResult(
        canonical_selection_list=[CanonicalSelection(selected_chart_path=chart_path)],
        unresolved_size_group_gap_list=[],
    )


def test_canonical_validator_exposes_validate_as_its_only_public_boundary() -> None:
    """Keep SQLite accepted-table queries outside canonical result validation."""

    assert tuple(
        name
        for name, member in inspect.getmembers(CanonicalSelectionValidator, inspect.isfunction)
        if not name.startswith("_")
    ) == ("validate",)


def test_brand_output_preflights_containment_and_preserves_source_content(tmp_path: Path) -> None:
    """Publish one canonical target and reject normalized source or target escapes."""

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    reader = SourceDiscoveryDatabaseReader()
    source_chart_path = _accepted_table_list_get(tmp_path, [source_type_result])[0].chart_path
    step = _brand_output_step_get(reader)
    step_input = BrandOutputStep.input_build(
        step,
        context,
        BrandOutputInputSource(
            brand_input=_brand_input_get(),
            canonical_selection_result=CanonicalSelectionResult(
                canonical_selection_list=[CanonicalSelection(selected_chart_path=source_chart_path)],
                unresolved_size_group_gap_list=[],
            ),
            source_type_result_list=[source_type_result],
        ),
    )
    result = BrandOutputStep.result_build(step, context, step_input)

    assert result.dataset_path == "result/brand/dataset/brand_size_chart/part-00000.jsonl"
    assert result.size_chart_path_list == ["result/brand/size_chart/women_dress__tr.json"]
    BrandOutputStep.result_validate(step, context, step_input, result)
    final_path = tmp_path / "data-result" / "brand" / "size_chart" / "women_dress__tr.json"
    final_path.write_text(_chart_get("Changed.").model_dump_json(), encoding="utf-8")
    with pytest.raises(StepResultValidationError, match="exactly equal"):
        BrandOutputStep.result_validate(step, context, step_input, result)

    external_chart_path = tmp_path.parent / "external-chart.json"
    external_chart_path.write_text(_chart_get().model_dump_json(), encoding="utf-8")
    escape_path = tmp_path / "source-chart-escape.json"
    escape_path.symlink_to(external_chart_path)
    escaped_input = BrandOutputInput(
        brand_input=step_input.brand_input,
        dataset_write_target=step_input.dataset_write_target,
        output_item_list=[
            BrandOutputItem(
                **{
                    **step_input.output_item_list[0].model_dump(),
                    "source_chart_path": escape_path.relative_to(tmp_path).as_posix(),
                }
            )
        ],
    )
    with pytest.raises(RuntimeError, match="escapes result_dir"):
        BrandOutputStep.result_build(step, context, escaped_input)

    external_target_path = tmp_path.parent / "external-target.json"
    target_escape_path = tmp_path / "target-escape.json"
    target_escape_path.symlink_to(external_target_path)
    target_escaped_input = BrandOutputInput(
        brand_input=step_input.brand_input,
        dataset_write_target=step_input.dataset_write_target,
        output_item_list=[
            BrandOutputItem(
                market_scope_key=step_input.output_item_list[0].market_scope_key,
                output_write_target=ArtifactWriteTarget(
                    artifact_path="target-escape.json",
                    filesystem_path=target_escape_path.as_posix(),
                ),
                size_group_key=step_input.output_item_list[0].size_group_key,
                source_chart_path=step_input.output_item_list[0].source_chart_path,
                source_type=step_input.output_item_list[0].source_type,
                source_url=step_input.output_item_list[0].source_url,
            )
        ],
    )
    with pytest.raises(RuntimeError, match="target escapes the standard result path"):
        BrandOutputStep.result_build(step, context, target_escaped_input)


def test_brand_output_rejects_unknown_selection_and_invalid_source_chart(tmp_path: Path) -> None:
    """Reject unowned selections and malformed source artifacts before publication."""

    context = _context_get(tmp_path)
    source_type_result = _source_type_result_write(
        chart=_chart_get(),
        market_scope_key="tr",
        result_dir=tmp_path,
        size_group_key="women_dress",
        source_type="official_brand_size_guide",
    )
    reader = SourceDiscoveryDatabaseReader()
    step = _brand_output_step_get(reader)
    with pytest.raises(RuntimeError, match="unknown accepted chart"):
        BrandOutputStep.input_build(
            step,
            context,
            BrandOutputInputSource(
                brand_input=_brand_input_get(),
                canonical_selection_result=CanonicalSelectionResult(
                    canonical_selection_list=[CanonicalSelection(selected_chart_path="workflow/unknown.json")],
                    unresolved_size_group_gap_list=[],
                ),
                source_type_result_list=[source_type_result],
            ),
        )

    source_chart_path = _accepted_table_list_get(tmp_path, [source_type_result])[0].chart_path
    invalid_source_input = BrandOutputStep.input_build(
        step,
        context,
        BrandOutputInputSource(
            brand_input=_brand_input_get(),
            canonical_selection_result=CanonicalSelectionResult(
                canonical_selection_list=[CanonicalSelection(selected_chart_path=source_chart_path)],
                unresolved_size_group_gap_list=[],
            ),
            source_type_result_list=[source_type_result],
        ),
    )
    (tmp_path / source_chart_path).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing or invalid"):
        BrandOutputStep.result_build(step, context, invalid_source_input)


def test_brand_workflow_keeps_coverage_gaps_out_of_error_list(tmp_path: Path) -> None:
    """Treat no-table coverage gaps as successful downstream workflow output."""

    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    no_table_result = _source_type_result_get(
        database_path="workflow/brand/source/source_discover/state.sqlite3",
        outcome="no_table",
        source_type="official_brand_size_guide",
    ).source_discovery_result

    class SourceDiscoveryStep:
        """Return one normal no-table source outcome."""

        async def run_outcome_list(self, invocation_list: object, workflow_step_config: object) -> object:
            """Return one successful final outcome."""

            _ = invocation_list
            _ = workflow_step_config
            return [WorkflowStepInvocationOutcome(result=no_table_result, validation_feedback_tuple=())]

    workflow._source_discovery_step = SourceDiscoveryStep()

    async def input_write_step(
        execution_context: WorkflowExecutionContext,
        workflow_input: WorkflowBrandSizeChartInput,
    ) -> None:
        """Publish the workflow input through the async runtime boundary."""

        _workflow_input_write(execution_context, workflow_input)

    async def result_write_step(
        execution_context: WorkflowExecutionContext,
        workflow_input: WorkflowBrandSizeChartInput,
        workflow_result: BrandResult,
    ) -> BrandResult:
        """Return the candidate workflow result through the async runtime boundary."""

        _ = execution_context
        _ = workflow_input
        return workflow_result

    workflow.input_write_step = input_write_step
    workflow.result_write_step = result_write_step
    workflow.source_type_list_get = lambda request: ["official_brand_size_guide"]
    workflow.coverage_decide_write_step = (
        lambda execution_context, input_source, workflow_step_config: CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[CoverageDecisionProductTypeGap(product_type="dress", reason="No chart.")],
        )
    )
    workflow.canonical_select_write_step = (
        lambda execution_context, input_source, workflow_step_config: CanonicalSelectionResult(
            canonical_selection_list=[], unresolved_size_group_gap_list=[]
        )
    )
    workflow.brand_output_write_step = lambda execution_context, input_source: BrandOutputResult(
        dataset_path="result/brand/dataset/brand_size_chart/part-00000.jsonl", size_chart_path_list=[]
    )
    workflow_input = _workflow_input_get(["dress"])
    context = WorkflowExecutionContext(
        data_path=_data_path_get(tmp_path),
        result_dir=tmp_path,
        run_context=_run_context_get(),
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        workflow_instance_dir=tmp_path / "workflow" / "brand",
    )

    result = asyncio.run(
        inspect.unwrap(BrandSizeChartBrandWorkflow.run)(workflow, context, workflow_input, _brand_input_get())
    )

    assert result.error_list == []
    assert result.status == "success"
    assert result.coverage_decision_result.uncovered_product_type_gap_list[0].product_type == "dress"


def test_brand_workflow_routes_complete_results_through_real_downstream_step_methods(tmp_path: Path) -> None:
    """Route complete source results through deterministic and semantic downstream owners."""

    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)
    context = _context_get(tmp_path)
    _workflow_input_write(context, _workflow_input_get(["dress"]))
    no_table_result = _source_type_result_get(
        database_path="workflow/run/source/source_discover/state.sqlite3",
        outcome="no_table",
        source_type="official_brand_size_guide",
    )
    table_result = no_table_result.model_copy(
        update={
            "source_discovery_result": no_table_result.source_discovery_result.model_copy(
                update={"outcome": "table_available"}
            )
        }
    )
    coverage_config = _workflow_input_get(["dress"]).config.step_map.coverage_decide
    canonical_config = _workflow_input_get(["dress"]).config.step_map.canonical_select
    record_list: list[tuple[str, BrandSourceTypeResultInputSource, object | None]] = []

    class RecordingStep:
        """Record workflow branch ownership and return a fixed typed result."""

        def __init__(
            self, *, have_candidate: bool | None, result: CanonicalSelectionResult | CoverageDecisionResult
        ) -> None:
            """Store configured branch behavior."""

            self._have_candidate = have_candidate
            self._result = result

        def have_candidate(self, input_source: BrandSourceTypeResultInputSource) -> bool:
            """Record and return the configured semantic branch condition."""

            record_list.append(("candidate", input_source, None))
            if self._have_candidate is not None:
                return self._have_candidate
            return any(
                source_type_result.source_discovery_result is not None
                and source_type_result.source_discovery_result.outcome == "table_available"
                for source_type_result in input_source.source_type_result_list
            )

        def run(
            self,
            execution_context: WorkflowStepExecutionContext,
            input_source: BrandSourceTypeResultInputSource,
            workflow_step_config: object | None = None,
        ) -> CanonicalSelectionResult | CoverageDecisionResult:
            """Record the exact runtime call and return the typed branch result."""

            _ = execution_context
            record_list.append(("run", input_source, workflow_step_config))
            return self._result

    coverage_result = CoverageDecisionResult(
        covered_product_type_list=[],
        uncovered_product_type_gap_list=[CoverageDecisionProductTypeGap(product_type="dress", reason="No chart.")],
    )
    canonical_result = CanonicalSelectionResult(canonical_selection_list=[], unresolved_size_group_gap_list=[])
    workflow._coverage_decision_default_step = RecordingStep(have_candidate=False, result=coverage_result)
    workflow._coverage_decision_step = RecordingStep(have_candidate=False, result=coverage_result)
    workflow._canonical_selection_default_step = RecordingStep(have_candidate=False, result=canonical_result)
    workflow._canonical_selection_step = RecordingStep(have_candidate=None, result=canonical_result)
    no_table_input_source = BrandSourceTypeResultInputSource(source_type_result_list=[no_table_result])
    table_input_source = BrandSourceTypeResultInputSource(source_type_result_list=[table_result])

    assert (
        inspect.unwrap(BrandSizeChartBrandWorkflow.coverage_decide_write_step)(
            workflow, context, no_table_input_source, coverage_config
        )
        == coverage_result
    )
    assert (
        inspect.unwrap(BrandSizeChartBrandWorkflow.coverage_decide_write_step)(
            workflow, context, table_input_source, coverage_config
        )
        == coverage_result
    )
    assert (
        inspect.unwrap(BrandSizeChartBrandWorkflow.canonical_select_write_step)(
            workflow, context, no_table_input_source, canonical_config
        )
        == canonical_result
    )
    assert (
        inspect.unwrap(BrandSizeChartBrandWorkflow.canonical_select_write_step)(
            workflow, context, table_input_source, canonical_config
        )
        == canonical_result
    )
    assert [(kind, source.source_type_result_list, config) for kind, source, config in record_list] == [
        ("run", [no_table_result], None),
        ("run", [table_result], coverage_config),
        ("candidate", [no_table_result], None),
        ("run", [no_table_result], None),
        ("candidate", [table_result], None),
        ("run", [table_result], canonical_config),
    ]


def _accepted_table_get(*, chart_path: str, market_scope_key: str, source_url: str) -> SourceDiscoveryAcceptedTable:
    """Build one transient accepted row for deterministic gap ordering."""

    return SourceDiscoveryAcceptedTable(
        chart_path=chart_path,
        source_priority=600,
        source_table=SourceDiscoveryTable(
            evidence_path_list=["workflow/evidence/table.json"],
            market_scope_key=market_scope_key,
            reason="Visible table.",
            size_group_key="women_dress",
            source_title="Size chart",
            source_url=source_url,
            state="accepted",
        ),
        source_type="official_brand_size_guide",
    )


def _accepted_table_list_get(result_dir: Path, source_type_result_list: list[SourceTypeResult]):
    """Read accepted source tables through the production SQLite reader."""

    return SourceDiscoveryDatabaseReader().accepted_table_list_get_for_source_type_result_list(
        result_dir=result_dir, source_type_result_list=source_type_result_list
    )


def _brand_input_get() -> BrandInput:
    """Build one stable brand identity."""

    return BrandInput(parsed_brand_key="brand", parsed_brand_name="Brand")


def _data_path_get(tmp_path: Path) -> WorkflowDataPath:
    """Return isolated standard Data roots for downstream tests.

    Args:
        tmp_path: Test-owned runtime root.

    Returns:
        Exact result and workspace paths.
    """

    return WorkflowDataPath(
        result_path=(tmp_path / "data-result").resolve(),
        workspace_path=(tmp_path / "data-workspace").resolve(),
    )


def _run_context_get() -> WorkflowRunContext:
    """Return immutable provenance used by output dataset tests.

    Returns:
        Stable platform run context.
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


def _brand_output_step_get(reader: SourceDiscoveryDatabaseReader) -> BrandOutputStep:
    """Build one deterministic output step with production dependencies."""

    return BrandOutputStep(
        artifact_writer=JsonArtifactWriter(),
        json_lines_artifact_writer=JsonLinesArtifactWriter(),
        source_discovery_database_reader=reader,
        validator=BrandOutputValidator(),
    )


def _canonical_selection_result_get(
    canonical_selection_list: list[CanonicalSelection], accepted_table_list: list
) -> CanonicalSelectionResult:
    """Build selection results with the production unresolved-gap algorithm."""

    return CanonicalSelectionResult(
        canonical_selection_list=canonical_selection_list,
        unresolved_size_group_gap_list=canonical_selection_unresolved_size_group_gap_list_get(
            canonical_selection_list=canonical_selection_list,
            accepted_table_list=accepted_table_list,
        ),
    )


def _chart_get(description: str = "Chart.") -> BrandSizeChart:
    """Build one valid source chart."""

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
    """Build one isolated downstream step context with its runtime input path."""

    return WorkflowStepExecutionContext(
        data_path=_data_path_get(tmp_path),
        result_dir=tmp_path,
        run_context=_run_context_get(),
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "run" / "step" / "downstream",
        workflow_input_path=Path("workflow/run/input.json"),
    )


def _source_table_write(
    *, chart: BrandSizeChart, market_scope_key: str, result_dir: Path, size_group_key: str, step_dir: Path
) -> None:
    """Write one accepted table and its validated chart artifact."""

    source_table = SourceDiscoveryTable(
        evidence_path_list=["workflow/run/evidence/table.json"],
        market_scope_key=market_scope_key,
        reason="Visible table.",
        size_group_key=size_group_key,
        source_title="Size chart",
        source_url="https://brand.example/size",
        state="accepted",
    )
    database_path = state_database_path_get(step_dir)
    SqliteStateStore().upsert(database_path, SOURCE_DISCOVERY_TABLE, source_table)
    JsonArtifactWriter().write(
        ArtifactLayout(result_dir).source_discovery_chart_path(step_dir, size_group_key, market_scope_key), chart
    )


def _source_type_result_get(*, database_path: str, outcome: str, source_type: str) -> SourceTypeResult:
    """Build one successful source-discovery final handoff."""

    return SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[], outcome=outcome, source_discovery_database_path=database_path
        ),
        source_type=source_type,
        status="success",
        warning_list=[],
    )


def _source_type_result_write(
    *, chart: BrandSizeChart, market_scope_key: str, result_dir: Path, size_group_key: str, source_type: str
) -> SourceTypeResult:
    """Write one source-discovery SQLite handoff and accepted chart."""

    step_dir = result_dir / "workflow" / "run" / source_type / "source_discover"
    database_path = state_database_path_get(step_dir)
    SqliteStateStore().initialize(database_path, list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))
    _source_table_write(
        chart=chart,
        market_scope_key=market_scope_key,
        result_dir=result_dir,
        size_group_key=size_group_key,
        step_dir=step_dir,
    )
    return _source_type_result_get(
        database_path=ArtifactLayout(result_dir).artifact_path(database_path),
        outcome="table_available",
        source_type=source_type,
    )


def _step_input_get(
    context: WorkflowStepExecutionContext, source_type_result_list: list[SourceTypeResult]
) -> BrandSourceTypeResultStepInput:
    """Build one downstream persisted input from runtime-owned workflow identity."""

    return BrandSourceTypeResultStepInput(
        source_type_result_list=source_type_result_list,
        workflow_input_path=context.workflow_input_path,
    )


def _workflow_input_get(product_type_request_list: list[str]) -> WorkflowBrandSizeChartInput:
    """Build one complete current workflow input with exact typed step configuration."""

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
                    concurrency=1,
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
            product_type_request_list=product_type_request_list,
            source_type_allow_list=[],
        ),
    )


def _workflow_input_write(
    execution_context: WorkflowExecutionContext | WorkflowStepExecutionContext,
    workflow_input: WorkflowBrandSizeChartInput,
) -> None:
    """Publish one current workflow input through the exact runtime artifact location."""

    workflow_instance_dir = getattr(execution_context, "workflow_instance_dir", None)
    workflow_input_path = (
        workflow_instance_dir / "input.json"
        if workflow_instance_dir is not None
        else execution_context.result_dir / execution_context.workflow_input_path
    )
    JsonArtifactWriter().write(workflow_input_path, workflow_input)
