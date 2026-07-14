"""SQLite source-discovery terminal-state behavior tests."""

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
    SourceDiscoveryInput,
    SourceDiscoveryMarketBoundary,
    SourceDiscoveryProductSearch,
    SourceDiscoveryQuery,
    SourceDiscoveryResult,
    SourceDiscoveryTable,
    SourceDiscoveryUrl,
    SourceDiscoveryUrlProductSearch,
    WorkflowBrandSizeChartConfig,
    WorkflowBrandSizeChartInput,
    WorkflowBrandSizeChartRequest,
    WorkflowBrandSizeChartStepMap,
    WorkflowStepCanonicalSelectConfig,
    WorkflowStepCoverageDecideConfig,
    WorkflowStepSourceDiscoverConfig,
)
from brand_size_chart.source.discovery_database import (
    SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE,
    SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
    SOURCE_DISCOVERY_QUERY_TABLE,
    SOURCE_DISCOVERY_TABLE,
    SOURCE_DISCOVERY_TABLE_BY_NAME_MAP,
    SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE,
    SOURCE_DISCOVERY_URL_TABLE,
)
from brand_size_chart.step.source_discovery import SourceDiscoveryStep
from brand_size_chart.validator import SourceDiscoveryValidator


def test_source_discovery_derives_valid_table_available_result_from_current_sqlite_state(tmp_path: Path) -> None:
    """Read terminal state without mutation and expose its sibling database handle."""

    context = _context_get(tmp_path)
    step_input = _input_get(context)
    store = _current_state_write(context, table_state="accepted")
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
    """Keep no-table and market-conflict data as explicit terminal outcomes."""

    context = _context_get(tmp_path)
    step_input = _input_get(context)
    store = _current_state_write(context, table_state=table_state)

    SourceDiscoveryValidator(sqlite_state_store=store).validate(
        context, step_input, _result_get(context, outcome=outcome)
    )


@pytest.mark.parametrize("mutation", ["candidate", "wrong_handle", "nested_orphan_chart", "pending"])
def test_source_discovery_rejects_incomplete_or_wrong_current_state(tmp_path: Path, mutation: str) -> None:
    """Reject incomplete current state instead of reconstructing or correcting it."""

    context = _context_get(tmp_path)
    step_input = _input_get(context)
    store = _current_state_write(context, table_state="accepted")
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
        result = result.model_copy(update={"source_discovery_database_path": "workflow/run/step/other.sqlite3"})
    elif mutation == "nested_orphan_chart":
        JsonArtifactWriter().write(context.step_instance_dir / "chart" / "nested" / "orphan.json", _chart_get())
    else:
        product_search = store.get(database_path, SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE, ("dress", "women"))
        assert product_search is not None
        store.upsert(
            database_path,
            SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
            product_search.model_copy(update={"state": "pending"}),
        )

    with pytest.raises(StepResultValidationError):
        SourceDiscoveryValidator(sqlite_state_store=store).validate(context, step_input, result)


def test_source_discovery_validator_rejects_unrequested_search_product_type(tmp_path: Path) -> None:
    """Reject product-search worklist rows outside the persisted workflow request."""

    context = _context_get(tmp_path)
    store = _current_state_write(context, table_state="accepted")
    evidence_path = "workflow/run/step/source_discover/evidence/source.json"
    store.upsert(
        state_database_path_get(context.step_instance_dir),
        SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
        SourceDiscoveryProductSearch(
            evidence_path_list=[evidence_path],
            product_type="shirt",
            reason="Unrequested branch closed.",
            search_sex="men",
            state="rejected",
        ),
    )

    with pytest.raises(StepResultValidationError, match="requested product type"):
        SourceDiscoveryValidator(sqlite_state_store=store).validate(
            context, _input_get(context), _result_get(context, outcome="table_available")
        )


def test_source_discovery_validator_keeps_physical_unisex_table_independent_from_search_sex(tmp_path: Path) -> None:
    """Accept a source-evidenced unisex table discovered through a women search branch."""

    context = _context_get(tmp_path)
    store = _current_state_write(context, table_state="accepted")
    database_path = state_database_path_get(context.step_instance_dir)
    store.delete(database_path, SOURCE_DISCOVERY_TABLE, ("women_dress", "tr"))
    ArtifactLayout(context.result_dir).source_discovery_chart_path(
        context.step_instance_dir, "women_dress", "tr"
    ).unlink()
    store.upsert(
        database_path,
        SOURCE_DISCOVERY_TABLE,
        SourceDiscoveryTable(
            evidence_path_list=["workflow/run/step/source_discover/evidence/source.json"],
            market_scope_key="tr",
            reason="Opened source exposes one unisex chart.",
            size_group_key="unisex_clothing",
            source_title="Unisex clothing",
            source_url="https://brand.example/size",
            state="accepted",
        ),
    )
    JsonArtifactWriter().write(
        ArtifactLayout(context.result_dir).source_discovery_chart_path(
            context.step_instance_dir, "unisex_clothing", "tr"
        ),
        _chart_get(),
    )

    SourceDiscoveryValidator(sqlite_state_store=store).validate(
        context, _input_get(context), _result_get(context, outcome="table_available")
    )


def _chart_get() -> BrandSizeChart:
    """Build one valid source chart."""

    return BrandSizeChart(
        description="Dress size chart.",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[BrandSizeChartMeasurement(max_value="M", min_value="M", name="Size", unit="size")],
                size_label="M",
            )
        ],
    )


def _context_get(tmp_path: Path) -> WorkflowStepExecutionContext:
    """Build a source-discovery context and persist its complete workflow input."""

    workflow_input_path = Path("workflow/run/input.json")
    workflow_input_file = tmp_path / workflow_input_path
    workflow_input_file.parent.mkdir(parents=True)
    workflow_input_file.write_text(_workflow_input_get().model_dump_json(), encoding="utf-8")
    return WorkflowStepExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "run" / "step" / "source_discover",
        workflow_input_path=workflow_input_path,
    )


def _current_state_write(context: WorkflowStepExecutionContext, *, table_state: str) -> SqliteStateStore:
    """Persist complete terminal state and every declared artifact boundary."""

    evidence_path = context.step_instance_dir / "evidence" / "source.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    evidence_reference = evidence_path.relative_to(context.result_dir).as_posix()
    database_path = state_database_path_get(context.step_instance_dir)
    store = SqliteStateStore()
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
            reason="Selected market.",
            source_url="https://brand.example/size",
        ),
    )
    store.upsert(
        database_path,
        SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE,
        SourceDiscoveryUrlProductSearch(product_type="dress", search_sex="women", url="https://brand.example/size"),
    )
    if table_state != "no_table":
        source_table = SourceDiscoveryTable(
            evidence_path_list=[evidence_reference],
            market_scope_key="tr",
            reason="Visible source table.",
            size_group_key="women_dress",
            source_title="Women dress size chart",
            source_url="https://brand.example/size",
            state=table_state,
        )
        store.upsert(database_path, SOURCE_DISCOVERY_TABLE, source_table)
        JsonArtifactWriter().write(
            ArtifactLayout(context.result_dir).source_discovery_chart_path(
                context.step_instance_dir, source_table.size_group_key, source_table.market_scope_key
            ),
            _chart_get(),
        )
    return store


def _input_get(context: WorkflowStepExecutionContext) -> SourceDiscoveryInput:
    """Build one current source-discovery input matching the persisted workflow identity."""

    return SourceDiscoveryInput(
        brand_input=BrandInput(parsed_brand_key="brand", parsed_brand_name="Brand"),
        evidence_write_target=ArtifactWriteTarget(
            artifact_path="workflow/run/step/source_discover/evidence",
            filesystem_path=(context.result_dir / ".playwright-mcp" / "evidence").as_posix(),
        ),
        source_type="official_brand_product_page",
        workflow_input_path=context.workflow_input_path,
    )


def _result_get(context: WorkflowStepExecutionContext, *, outcome: str) -> SourceDiscoveryResult:
    """Build the exact public handoff for one derived terminal outcome."""

    return SourceDiscoveryResult(
        browsing_error_list=[],
        outcome=outcome,
        source_discovery_database_path=ArtifactLayout(context.result_dir).artifact_path(
            state_database_path_get(context.step_instance_dir)
        ),
    )


def _workflow_input_get() -> WorkflowBrandSizeChartInput:
    """Build the complete public workflow input required by current runtime interfaces."""

    return WorkflowBrandSizeChartInput(
        request=WorkflowBrandSizeChartRequest(
            brand_list=["Brand"],
            priority_country_code="TR",
            product_type_request_list=["dress"],
            source_type_allow_list=[],
        ),
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
    )
