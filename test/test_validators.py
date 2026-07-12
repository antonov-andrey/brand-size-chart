"""Mechanical source-discovery SQLite validator tests."""

import inspect
from pathlib import Path
import sqlite3

import pytest
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext
from workflow_container_runtime.workflow import WorkflowRuntimeCapability

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    PromptScope,
    RunInput,
    SourceDiscoveryInput,
    SourceDiscoveryMarketBoundary,
    SourceDiscoveryProductSearch,
    SourceDiscoveryQuery,
    SourceDiscoveryResult,
    SourceDiscoveryTable,
    SourceDiscoveryUrl,
    SourceDiscoveryUrlProductSearch,
    SourceTypeWorkflowInput,
    SourceTypeCatalogItem,
    WorkflowRunPromptApplyInput,
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
from brand_size_chart.validator import PromptScopeValidator, SourceDiscoveryValidator


def _chart_get() -> BrandSizeChart:
    """Build one valid chart fixture.

    Returns:
        Valid chart.
    """

    return BrandSizeChart(
        description="Chart.",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[BrandSizeChartMeasurement(max_value="M", min_value="M", name="Size", unit="size")],
                size_label="M",
            )
        ],
    )


def _fixture_get(
    tmp_path: Path,
) -> tuple[WorkflowStepExecutionContext, SourceDiscoveryInput, SqliteStateStore, SourceDiscoveryResult]:
    """Create one complete SQLite-backed source-discovery handoff.

    Args:
        tmp_path: Isolated result root.

    Returns:
        Context, input, store, and valid public result.
    """

    context = WorkflowStepExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "run" / "step" / "source_discover",
    )
    step_input = SourceDiscoveryInput(
        evidence_write_target=ArtifactWriteTarget(
            artifact_path="workflow/run/step/source_discover/evidence",
            filesystem_path=(tmp_path / ".playwright-mcp" / "current" / "evidence").as_posix(),
        ),
        workflow_input=SourceTypeWorkflowInput(
            brand_input=BrandInput(
                parsed_brand_key="brand", parsed_brand_name="Brand", raw_brand_name="Brand", source_line_number=1
            ),
            prompt_scope=PromptScope(priority_country_code="TR", product_type_request_list=["dress"]),
            source_type="official_brand_product_page",
        ),
    )
    evidence_path = context.step_instance_dir / "evidence" / "source.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    evidence_reference = evidence_path.relative_to(tmp_path).as_posix()
    state_path = state_database_path_get(context.step_instance_dir)
    store = SqliteStateStore()
    store.initialize(state_path, list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))
    store.upsert(
        state_path,
        SOURCE_DISCOVERY_QUERY_TABLE,
        SourceDiscoveryQuery(
            evidence_path_list=[evidence_reference], query="brand dress", reason="Searched.", state="searched"
        ),
    )
    store.upsert(
        state_path,
        SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
        SourceDiscoveryProductSearch(
            evidence_path_list=[evidence_reference],
            product_type="dress",
            reason="Inspected.",
            search_sex="women",
            state="searched",
        ),
    )
    store.upsert(
        state_path,
        SOURCE_DISCOVERY_URL_TABLE,
        SourceDiscoveryUrl(
            evidence_path_list=[evidence_reference], reason="Opened.", state="opened", url="https://brand.example/size"
        ),
    )
    store.upsert(
        state_path,
        SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE,
        SourceDiscoveryMarketBoundary(
            evidence_path_list=[evidence_reference],
            market_scope_key="tr",
            reason="Selected the priority-country market.",
            source_url="https://brand.example/size",
        ),
    )
    store.upsert(
        state_path,
        SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE,
        SourceDiscoveryUrlProductSearch(product_type="dress", search_sex="women", url="https://brand.example/size"),
    )
    store.upsert(
        state_path,
        SOURCE_DISCOVERY_TABLE,
        SourceDiscoveryTable(
            evidence_path_list=[evidence_reference],
            market_scope_key="tr",
            reason="Visible.",
            size_group_key="women_dress",
            source_title="Women dress",
            source_url="https://brand.example/size",
            state="accepted",
        ),
    )
    JsonArtifactWriter().write(
        ArtifactLayout(tmp_path).source_discovery_chart_path(context.step_instance_dir, "women_dress", "tr"),
        _chart_get(),
    )
    return (
        context,
        step_input,
        store,
        SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="table_available",
            source_discovery_database_path=ArtifactLayout(tmp_path).artifact_path(state_path),
        ),
    )


def test_source_discovery_validator_has_one_sqlite_backed_public_validation_method() -> None:
    """Read current state through the injected runtime store only."""

    assert tuple(inspect.signature(SourceDiscoveryValidator.validate).parameters) == (
        "self",
        "execution_context",
        "step_input",
        "result",
    )


def test_prompt_scope_validator_allows_product_type_substrings_in_shared_instruction(tmp_path: Path) -> None:
    """Keep semantic instruction overlap out of mechanical substring validation.

    Args:
        tmp_path: Isolated result root.
    """

    context = WorkflowStepExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "run" / "step" / "workflow_run_prompt_apply",
    )
    step_input = WorkflowRunPromptApplyInput(
        source_type_catalog_list=[
            SourceTypeCatalogItem(requires_product_type=True, source_type="official_brand_product_page")
        ],
        workflow_input=RunInput(brand_list_text="Brand", workflow_run_prompt="Find men size charts."),
    )
    result = PromptScope(
        priority_country_code="TR",
        product_type_request_list=["men"],
        shared_instruction="Preserve measurement units.",
    )

    PromptScopeValidator().validate(context, step_input, result)


def test_source_discovery_validator_rejects_unrequested_search_product_type(tmp_path: Path) -> None:
    """Reject search worklist rows outside the public requested product set.

    Args:
        tmp_path: Isolated result root.
    """

    context, step_input, store, result = _fixture_get(tmp_path)
    state_path = state_database_path_get(context.step_instance_dir)
    evidence_reference = (context.step_instance_dir / "evidence" / "source.json").relative_to(tmp_path).as_posix()
    store.upsert(
        state_path,
        SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE,
        SourceDiscoveryProductSearch(
            evidence_path_list=[evidence_reference],
            product_type="shirt",
            reason="Rejected unrelated search branch.",
            search_sex="men",
            state="rejected",
        ),
    )

    with pytest.raises(StepResultValidationError, match="requested product type"):
        SourceDiscoveryValidator(sqlite_state_store=store).validate(context, step_input, result)


def test_source_discovery_validator_keeps_physical_unisex_table_independent_from_search_sex(tmp_path: Path) -> None:
    """Accept a source-evidenced unisex table found through a women search branch.

    Args:
        tmp_path: Isolated result root.
    """

    context, step_input, store, result = _fixture_get(tmp_path)
    state_path = state_database_path_get(context.step_instance_dir)
    evidence_reference = (context.step_instance_dir / "evidence" / "source.json").relative_to(tmp_path).as_posix()
    store.delete(state_path, SOURCE_DISCOVERY_TABLE, ("women_dress", "tr"))
    ArtifactLayout(tmp_path).source_discovery_chart_path(context.step_instance_dir, "women_dress", "tr").unlink()
    store.upsert(
        state_path,
        SOURCE_DISCOVERY_TABLE,
        SourceDiscoveryTable(
            evidence_path_list=[evidence_reference],
            market_scope_key="tr",
            reason="The opened source exposes one unisex table.",
            size_group_key="unisex_clothing",
            source_title="Unisex clothing",
            source_url="https://brand.example/size",
            state="accepted",
        ),
    )
    JsonArtifactWriter().write(
        ArtifactLayout(tmp_path).source_discovery_chart_path(
            context.step_instance_dir,
            "unisex_clothing",
            "tr",
        ),
        _chart_get(),
    )

    SourceDiscoveryValidator(sqlite_state_store=store).validate(context, step_input, result)


@pytest.mark.parametrize(
    "mutation",
    [
        "query",
        "market_boundary",
        "extra_market_boundary",
        "worklist",
        "relation",
        "table",
        "evidence",
        "url",
        "url_evidence",
        "url_reason",
        "chart",
        "outcome",
    ],
)
def test_source_discovery_validator_rejects_incomplete_current_rows(tmp_path: Path, mutation: str) -> None:
    """Reject every mechanical handoff gap without domain correction.

    Args:
        tmp_path: Isolated result root.
        mutation: Current-state invariant to break.
    """

    context, step_input, store, result = _fixture_get(tmp_path)
    state_path = state_database_path_get(context.step_instance_dir)
    if mutation == "query":
        row = store.get(state_path, SOURCE_DISCOVERY_QUERY_TABLE, ("brand dress",))
        assert row is not None
        store.upsert(state_path, SOURCE_DISCOVERY_QUERY_TABLE, row.model_copy(update={"reason": ""}))
    elif mutation == "market_boundary":
        store.delete(state_path, SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE, ("tr",))
    elif mutation == "extra_market_boundary":
        store.upsert(
            state_path,
            SOURCE_DISCOVERY_MARKET_BOUNDARY_TABLE,
            SourceDiscoveryMarketBoundary(
                evidence_path_list=[
                    (context.step_instance_dir / "evidence" / "source.json").relative_to(tmp_path).as_posix()
                ],
                market_scope_key="eu",
                reason="Incorrect second selected market.",
                source_url="https://brand.example/size",
            ),
        )
    elif mutation == "worklist":
        row = store.get(state_path, SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE, ("dress", "women"))
        assert row is not None
        store.upsert(state_path, SOURCE_DISCOVERY_PRODUCT_SEARCH_TABLE, row.model_copy(update={"state": "pending"}))
    elif mutation == "relation":
        store.delete(
            state_path, SOURCE_DISCOVERY_URL_PRODUCT_SEARCH_TABLE, ("https://brand.example/size", "dress", "women")
        )
    elif mutation == "table":
        row = store.get(state_path, SOURCE_DISCOVERY_TABLE, ("women_dress", "tr"))
        assert row is not None
        store.upsert(state_path, SOURCE_DISCOVERY_TABLE, row.model_copy(update={"source_title": ""}))
    elif mutation == "evidence":
        row = store.get(state_path, SOURCE_DISCOVERY_TABLE, ("women_dress", "tr"))
        assert row is not None
        store.upsert(
            state_path,
            SOURCE_DISCOVERY_TABLE,
            row.model_copy(update={"evidence_path_list": ["workflow/run/step/source_discover/evidence/missing.json"]}),
        )
    elif mutation == "url":
        row = store.get(state_path, SOURCE_DISCOVERY_URL_TABLE, ("https://brand.example/size",))
        assert row is not None
        store.upsert(state_path, SOURCE_DISCOVERY_URL_TABLE, row.model_copy(update={"state": "rejected"}))
    elif mutation == "url_evidence":
        row = store.get(state_path, SOURCE_DISCOVERY_URL_TABLE, ("https://brand.example/size",))
        assert row is not None
        store.upsert(state_path, SOURCE_DISCOVERY_URL_TABLE, row.model_copy(update={"evidence_path_list": []}))
    elif mutation == "url_reason":
        row = store.get(state_path, SOURCE_DISCOVERY_URL_TABLE, ("https://brand.example/size",))
        assert row is not None
        store.upsert(state_path, SOURCE_DISCOVERY_URL_TABLE, row.model_copy(update={"reason": "  "}))
    elif mutation == "chart":
        ArtifactLayout(tmp_path).source_discovery_chart_path(context.step_instance_dir, "women_dress", "tr").unlink()
    else:
        result.outcome = "no_table"

    with pytest.raises(StepResultValidationError):
        SourceDiscoveryValidator(sqlite_state_store=store).validate(context, step_input, result)


def test_source_discovery_validator_rejects_malformed_persisted_browser_url(tmp_path: Path) -> None:
    """Reject a state database whose coordinated URL values bypassed row validation.

    Args:
        tmp_path: Isolated result root.
    """

    context, step_input, store, result = _fixture_get(tmp_path)
    state_path = state_database_path_get(context.step_instance_dir)
    malformed_url = "not-a-url"
    with sqlite3.connect(state_path) as connection:
        connection.execute("UPDATE source_url SET url = ?", (malformed_url,))
        connection.execute("UPDATE source_url_product_search SET url = ?", (malformed_url,))
        connection.execute("UPDATE source_table SET source_url = ?", (malformed_url,))

    with pytest.raises(StepResultValidationError):
        SourceDiscoveryValidator(sqlite_state_store=store).validate(context, step_input, result)
