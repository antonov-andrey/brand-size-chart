"""SQLite source-discovery cutover behavior tests."""

from pathlib import Path

import pytest
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
from workflow_container_runtime.step import BrowserActionResult, StepResultValidationError, WorkflowStepExecutionContext
from workflow_container_runtime.workflow import WorkflowRuntimeCapability

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    PromptScope,
    SourceDiscoveryInput,
    SourceDiscoveryMarketBoundary,
    SourceDiscoveryProductSearch,
    SourceDiscoveryQuery,
    SourceDiscoveryResult,
    SourceDiscoveryTable,
    SourceDiscoveryUrl,
    SourceDiscoveryUrlProductSearch,
    SourceTypeWorkflowInput,
)
from brand_size_chart.source.discovery_database import (
    SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE,
    SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
    SOURCE_DISCOVERY_QUERY_TABLE,
    SOURCE_DISCOVERY_TABLE,
    SOURCE_DISCOVERY_TABLE_BY_NAME_MAP,
    SOURCE_DISCOVERY_URL_TABLE,
    SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE,
)
from brand_size_chart.step.source_discovery import SourceDiscoveryStep
from brand_size_chart.validator import SourceDiscoveryValidator


def _context_get(tmp_path: Path) -> WorkflowStepExecutionContext:
    """Build one source-discovery step execution context.

    Args:
        tmp_path: Isolated result root.

    Returns:
        Context for the source-discovery step.
    """

    return WorkflowStepExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "run" / "step" / "source_discover",
    )


def _input_get(
    context: WorkflowStepExecutionContext, *, source_type: str = "official_brand_product_page"
) -> SourceDiscoveryInput:
    """Build one persisted source-discovery input.

    Args:
        context: Current step context.
        source_type: Source type that determines product scope.

    Returns:
        Typed source-discovery input.
    """

    return SourceDiscoveryInput(
        evidence_write_target=ArtifactWriteTarget(
            artifact_path="workflow/run/step/source_discover/evidence",
            filesystem_path=(context.result_dir / ".playwright-mcp" / "current" / "evidence").as_posix(),
        ),
        workflow_input=SourceTypeWorkflowInput(
            brand_input=BrandInput(
                parsed_brand_key="brand",
                parsed_brand_name="Brand",
                raw_brand_name="Brand",
                source_line_number=1,
            ),
            prompt_scope=PromptScope(priority_country_code="TR", product_type_request_list=["dress"]),
            source_type=source_type,
        ),
    )


def _chart_get() -> BrandSizeChart:
    """Build one mechanically valid source chart.

    Returns:
        Complete chart fixture.
    """

    return BrandSizeChart(
        description="Dress size chart.",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[BrandSizeChartMeasurement(max_value="M", min_value="M", name="Size", unit="size")],
                size_label="M",
            )
        ],
    )


def _current_state_write(
    context: WorkflowStepExecutionContext,
    step_input: SourceDiscoveryInput,
    *,
    table_state: str = "accepted",
) -> SqliteStateStore:
    """Initialize one complete current-state fixture and materialized artifacts.

    Args:
        context: Current step context.
        step_input: Persisted input defining evidence scope.
        table_state: Terminal source-table state.

    Returns:
        Store used to persist the fixture.
    """

    evidence_path = context.step_instance_dir / "evidence" / "source.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    evidence_reference = evidence_path.relative_to(context.result_dir).as_posix()
    store = SqliteStateStore()
    database_path = state_database_path_get(context.step_instance_dir)
    store.initialize(database_path, list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))
    store.upsert(
        database_path,
        SOURCE_DISCOVERY_QUERY_TABLE,
        SourceDiscoveryQuery(
            evidence_path_list=[evidence_reference],
            query="brand dress size chart",
            reason="Search completed.",
            state="searched",
        ),
    )
    store.upsert(
        database_path,
        SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
        SourceDiscoveryProductSearch(
            evidence_path_list=[evidence_reference],
            product_type="dress",
            reason="Product inspected.",
            search_sex="women",
            state="searched",
        ),
    )
    store.upsert(
        database_path,
        SOURCE_DISCOVERY_URL_TABLE,
        SourceDiscoveryUrl(
            evidence_path_list=[evidence_reference],
            reason="Source opened.",
            state="opened",
            url="https://brand.example/size",
        ),
    )
    store.upsert(
        database_path,
        SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE,
        SourceDiscoveryMarketBoundary(
            evidence_path_list=[evidence_reference],
            market_scope_key="tr",
            reason="Selected the priority-country market.",
            source_url="https://brand.example/size",
        ),
    )
    store.upsert(
        database_path,
        SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE,
        SourceDiscoveryUrlProductSearch(product_type="dress", search_sex="women", url="https://brand.example/size"),
    )
    if table_state != "no_table":
        store.upsert(
            database_path,
            SOURCE_DISCOVERY_TABLE,
            SourceDiscoveryTable(
                evidence_path_list=[evidence_reference],
                market_scope_key="tr",
                reason="Visible source table.",
                size_group_key="women_dress",
                source_title="Women dress size chart",
                source_url="https://brand.example/size",
                state=table_state,
            ),
        )
        chart_path = ArtifactLayout(context.result_dir).source_discovery_chart_path(
            context.step_instance_dir, "women_dress", "tr"
        )
        JsonArtifactWriter().write(chart_path, _chart_get())
    _ = step_input
    return store


def _result_get(context: WorkflowStepExecutionContext, *, outcome: str) -> SourceDiscoveryResult:
    """Build one public handle to the sibling source-discovery database.

    Args:
        context: Current step context.
        outcome: Derived terminal outcome.

    Returns:
        Public result fixture.
    """

    return SourceDiscoveryResult(
        browsing_error_list=[],
        outcome=outcome,
        source_discovery_database_path=ArtifactLayout(context.result_dir).artifact_path(
            state_database_path_get(context.step_instance_dir)
        ),
    )


def test_source_discovery_derives_valid_table_available_result_from_current_sqlite_state(tmp_path: Path) -> None:
    """Read final rows without mutation and expose the sibling database handle."""

    context = _context_get(tmp_path)
    step_input = _input_get(context)
    store = _current_state_write(context, step_input)
    step = SourceDiscoveryStep.__new__(SourceDiscoveryStep)
    step._sqlite_state_store = store

    result = SourceDiscoveryStep.result_from_action_build(
        step, context, step_input, BrowserActionResult(browsing_error_list=[])
    )

    assert result == _result_get(context, outcome="table_available")
    SourceDiscoveryValidator(sqlite_state_store=store).validate(context, step_input, result)


@pytest.mark.parametrize(
    ("table_state", "outcome"),
    [("no_table", "no_table"), ("market_conflict", "market_conflict")],
)
def test_source_discovery_derives_terminal_outcomes_from_final_states(
    tmp_path: Path, table_state: str, outcome: str
) -> None:
    """Keep no-table and market-conflict data as explicit terminal outcomes.

    Args:
        tmp_path: Isolated result root.
        table_state: Persisted source-table state.
        outcome: Expected public outcome.
    """

    context = _context_get(tmp_path)
    step_input = _input_get(context)
    store = _current_state_write(context, step_input, table_state=table_state)
    result = _result_get(context, outcome=outcome)

    SourceDiscoveryValidator(sqlite_state_store=store).validate(context, step_input, result)


@pytest.mark.parametrize("mutation", ["candidate", "wrong_handle", "nested_orphan_chart", "pending"])
def test_source_discovery_rejects_incomplete_or_wrong_current_state(tmp_path: Path, mutation: str) -> None:
    """Reject incomplete current state instead of reconstructing or correcting it.

    Args:
        tmp_path: Isolated result root.
        mutation: Broken invariant introduced into an otherwise valid fixture.
    """

    context = _context_get(tmp_path)
    step_input = _input_get(context)
    store = _current_state_write(context, step_input)
    result = _result_get(context, outcome="table_available")
    database_path = state_database_path_get(context.step_instance_dir)
    if mutation == "candidate":
        store.upsert(
            database_path,
            SOURCE_DISCOVERY_TABLE,
            SourceDiscoveryTable(
                evidence_path_list=["workflow/run/step/source_discover/evidence/source.json"],
                market_scope_key="eu",
                reason="Unfinalized.",
                size_group_key="women_top",
                source_title="Women top size chart",
                source_url="https://brand.example/size",
                state="candidate",
            ),
        )
        JsonArtifactWriter().write(
            ArtifactLayout(context.result_dir).source_discovery_chart_path(
                context.step_instance_dir, "women_top", "eu"
            ),
            _chart_get(),
        )
    elif mutation == "wrong_handle":
        result.source_discovery_database_path = "workflow/run/step/source_discover/other.sqlite3"
    elif mutation == "nested_orphan_chart":
        JsonArtifactWriter().write(
            context.step_instance_dir / "chart" / "nested" / "orphan.json",
            _chart_get(),
        )
    else:
        row = store.get(database_path, SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE, ("dress", "women"))
        assert row is not None
        store.upsert(database_path, SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE, row.model_copy(update={"state": "pending"}))

    with pytest.raises(StepResultValidationError):
        SourceDiscoveryValidator(sqlite_state_store=store).validate(context, step_input, result)
