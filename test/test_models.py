"""Tests for Pydantic result models."""

from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError
from workflow_container_contract import WorkflowResult
from workflow_container_runtime.artifact import JsonlRecord
from workflow_container_runtime.step import BrowserActionResult, BrowsingError, WorkflowStepCodexState

from brand_size_chart.model import (
    ApplicabilityStatus,
    ArtifactWriteTarget,
    BrandInput,
    BrandListParseWarning,
    BrandOutputResult,
    BrandResult,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    CanonicalSelectionResult,
    CanonicalSelectionInput,
    CoverageDecisionResult,
    CoverageDecisionProductTypeGap,
    CoverageDecisionInput,
    PromptScope,
    RunResult,
    SourceDiscovery,
    SourceDiscoveryInput,
    SourceDiscoveryResult,
    SourceSurfaceDiscoveryQuery,
    SourceSurfaceInventory,
    SourceSurfaceProductTypeSex,
    SourceSurfaceTable,
    SourceSurfaceUrl,
    SourceTypeCatalogItem,
    SourceTypeSkip,
    SourceTypeResult,
    SourceTypeWorkflowInput,
    TableExtractionArtifact,
    TableExtractionDeltaBatchResult,
    TableExtractionInput,
    TableExtractionResult,
    WorkflowRunPromptApplyInput,
)


def test_model_package_exports_existing_public_models() -> None:
    """Keep public model imports stable while moving model owners into the package."""
    from brand_size_chart.model import BrandInput
    from brand_size_chart.model import BrandSizeChart
    from brand_size_chart.model import PromptScope
    from brand_size_chart.model import SourceDiscovery
    from brand_size_chart.model import SourceTypeResult
    from brand_size_chart.model import TableExtractionArtifact
    from brand_size_chart.model import TableExtractionDeltaBatchResult

    assert BrandInput.__module__ == "brand_size_chart.model.brand"
    assert BrandSizeChart.__module__ == "brand_size_chart.model.chart"
    assert PromptScope.__module__ == "brand_size_chart.model.prompt"
    assert SourceDiscovery.__module__ == "brand_size_chart.model.source"
    assert SourceTypeResult.__module__ == "brand_size_chart.model.source"
    assert TableExtractionArtifact.__module__ == "brand_size_chart.model.source"
    assert TableExtractionDeltaBatchResult.__module__ == "brand_size_chart.model.source"


def test_public_concrete_models_are_strict_and_closed() -> None:
    """Keep every exported concrete Pydantic model strict and closed."""
    import brand_size_chart.model as model

    for export_name in model.__all__:
        model_class = getattr(model, export_name)
        if not isinstance(model_class, type) or not issubclass(model_class, BaseModel):
            continue
        assert model_class.model_config.get("strict") is True, export_name
        assert model_class.model_config.get("extra") == "forbid", export_name


def test_workflow_results_use_one_stable_nested_tree() -> None:
    """Use direct WorkflowResult subclasses without duplicated child fields."""

    assert RunResult.__bases__ == (WorkflowResult,)
    assert BrandResult.__bases__ == (WorkflowResult,)
    assert SourceTypeResult.__bases__ == (WorkflowResult,)
    assert set(RunResult.model_fields) == {
        "brand_list_parse_warning_list",
        "brand_result_list",
        "error_list",
        "prompt_scope",
        "status",
        "warning_list",
    }
    assert set(BrandResult.model_fields) == {
        "brand_output_result",
        "canonical_selection_result",
        "coverage_decision_result",
        "error_list",
        "parsed_brand_key",
        "parsed_brand_name",
        "source_type_result_list",
        "source_type_skip_list",
        "status",
        "warning_list",
    }
    assert set(SourceTypeResult.model_fields) == {
        "error_list",
        "source_discovery_result",
        "source_type",
        "status",
        "table_extraction_result",
        "warning_list",
    }


def test_brand_result_partitions_source_type_results_and_skips() -> None:
    """Keep every represented source type in exactly one structured result channel."""

    skip = SourceTypeSkip(
        reason="requested_product_type_coverage_complete",
        source_type="official_brand_product_page",
    )
    brand_result = BrandResult(
        brand_output_result=BrandOutputResult(),
        canonical_selection_result=CanonicalSelectionResult(
            canonical_selection_list=[],
            unresolved_size_group_gap_list=[],
        ),
        coverage_decision_result=CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[],
        ),
        error_list=[],
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        source_type_result_list=[],
        source_type_skip_list=[skip],
        status="success",
        warning_list=[],
    )

    assert brand_result.source_type_skip_list == [skip]
    attempted_result = SourceTypeResult(
        source_type="official_brand_product_page",
        status="success",
    )
    with pytest.raises(ValidationError, match="source types must be unique"):
        BrandResult(
            brand_output_result=BrandOutputResult(),
            canonical_selection_result=CanonicalSelectionResult(
                canonical_selection_list=[],
                unresolved_size_group_gap_list=[],
            ),
            coverage_decision_result=CoverageDecisionResult(
                covered_product_type_list=[],
                uncovered_product_type_gap_list=[],
            ),
            error_list=[],
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            source_type_result_list=[attempted_result, attempted_result],
            source_type_skip_list=[],
            status="success",
            warning_list=[],
        )
    with pytest.raises(ValidationError, match="source types must be unique"):
        BrandResult(
            brand_output_result=BrandOutputResult(),
            canonical_selection_result=CanonicalSelectionResult(
                canonical_selection_list=[],
                unresolved_size_group_gap_list=[],
            ),
            coverage_decision_result=CoverageDecisionResult(
                covered_product_type_list=[],
                uncovered_product_type_gap_list=[],
            ),
            error_list=[],
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            source_type_result_list=[],
            source_type_skip_list=[skip, skip],
            status="success",
            warning_list=[],
        )
    with pytest.raises(ValidationError, match="source types must be unique"):
        BrandResult(
            brand_output_result=BrandOutputResult(),
            canonical_selection_result=CanonicalSelectionResult(
                canonical_selection_list=[],
                unresolved_size_group_gap_list=[],
            ),
            coverage_decision_result=CoverageDecisionResult(
                covered_product_type_list=[],
                uncovered_product_type_gap_list=[],
            ),
            error_list=[],
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            source_type_result_list=[
                SourceTypeResult(
                    source_type="official_brand_product_page",
                    status="success",
                )
            ],
            source_type_skip_list=[skip],
            status="success",
            warning_list=[],
        )


def test_prompt_scope_rejects_duplicate_source_type_allow_list_values() -> None:
    """Require each selected source type to appear once in the prompt scope."""

    source_type_allow_list = [
        "official_brand_size_guide",
        "official_brand_product_page",
    ]
    assert PromptScope(source_type_allow_list=source_type_allow_list).source_type_allow_list == source_type_allow_list
    with pytest.raises(ValidationError, match="source_type_allow_list.*unique"):
        PromptScope(
            source_type_allow_list=[
                "official_brand_size_guide",
                "official_brand_size_guide",
            ]
        )


def test_workflow_results_preserve_child_failure_and_partial_coverage() -> None:
    """Keep child failures and product gaps structured instead of copying them into parent errors."""
    source_type_result = SourceTypeResult(
        status="failed",
        error_list=["Source discovery exhausted its attempts."],
        source_type="official_brand_size_guide",
    )
    coverage_decision_result = CoverageDecisionResult(
        covered_product_type_list=[],
        uncovered_product_type_gap_list=[
            CoverageDecisionProductTypeGap(product_type="women shoes", reason="No verified table covers it.")
        ],
    )
    brand_result = BrandResult(
        status="success",
        brand_output_result=BrandOutputResult(),
        canonical_selection_result=CanonicalSelectionResult(
            canonical_selection_list=[],
            unresolved_size_group_gap_list=[],
        ),
        coverage_decision_result=coverage_decision_result,
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        source_type_result_list=[source_type_result],
        source_type_skip_list=[],
    )
    run_result = RunResult(
        status="success",
        brand_list_parse_warning_list=[],
        brand_result_list=[brand_result],
        prompt_scope=PromptScope(),
    )

    assert run_result.error_list == []
    assert run_result.brand_result_list[0].error_list == []
    assert run_result.brand_result_list[0].source_type_result_list[0].error_list == [
        "Source discovery exhausted its attempts."
    ]
    assert run_result.brand_result_list[0].source_type_result_list[0].source_discovery_result is None
    assert run_result.brand_result_list[0].coverage_decision_result.uncovered_product_type_gap_list == [
        CoverageDecisionProductTypeGap(product_type="women shoes", reason="No verified table covers it.")
    ]


def test_run_result_keeps_parse_warnings_separate_from_text_warnings() -> None:
    """Keep structured brand-list parse warnings separate from inherited text warnings."""
    parse_warning = BrandListParseWarning(
        message="Duplicate brand ignored.",
        parsed_brand_key="defacto",
        raw_brand_name="Defacto",
        raw_brand_name_list=["Defacto", "DeFacto"],
        source_line_number=2,
        warning_type="duplicate_brand",
    )
    run_result = RunResult(
        status="success",
        brand_list_parse_warning_list=[parse_warning],
        brand_result_list=[],
        prompt_scope=PromptScope(),
        warning_list=["One source type returned no tables."],
    )

    assert run_result.brand_list_parse_warning_list == [parse_warning]
    assert run_result.warning_list == ["One source type returned no tables."]
    with pytest.raises(ValidationError, match="warning_list"):
        RunResult(
            status="success",
            brand_list_parse_warning_list=[],
            brand_result_list=[],
            prompt_scope=PromptScope(),
            warning_list=[parse_warning],
        )


def test_browser_backed_step_results_preserve_browsing_errors() -> None:
    """Keep URL-level browsing failures beside each public domain result list."""
    browsing_error = BrowsingError(error="Navigation timed out.", url="https://brand.example/size")

    source_discovery_result = SourceDiscoveryResult(
        browsing_error_list=[browsing_error],
        source_discovery_list=[],
        warning_list=["No verified table was found."],
    )
    table_extraction_result = TableExtractionResult(
        browsing_error_list=[browsing_error],
        table_extraction_list=[],
    )

    assert source_discovery_result.browsing_error_list == [browsing_error]
    assert source_discovery_result.source_discovery_list == []
    assert table_extraction_result.browsing_error_list == [browsing_error]
    assert table_extraction_result.table_extraction_list == []


def test_source_surface_rows_are_incremental_jsonl_records() -> None:
    """Give every incrementally produced source-surface row one durable record identity."""
    for record_model in [
        SourceSurfaceDiscoveryQuery,
        SourceSurfaceProductTypeSex,
        SourceSurfaceTable,
        SourceSurfaceUrl,
    ]:
        assert record_model.__bases__ == (JsonlRecord,)

    discovery_query = SourceSurfaceDiscoveryQuery(
        entity_id="query:official-size-guide",
        evidence_path_list=[],
        query="site:brand.example size guide",
        reason="Searched the official site.",
        record_id="query:official-size-guide:r1",
        revision_index=1,
        state="searched",
        supersedes_record_id=None,
    )
    product_type_sex = SourceSurfaceProductTypeSex(
        entity_id="worklist:women-shoes",
        evidence_path_list=[],
        product_type="shoes",
        reason="Requested coverage.",
        record_id="worklist:women-shoes:r1",
        revision_index=1,
        sex="women",
        state="active",
        supersedes_record_id=None,
        worklist_key="women_shoes",
    )
    source_discovery = SourceDiscovery(
        country_code_list=["TR"],
        size_group_key="women_shoes",
        source_title="Women shoes",
        source_url="https://brand.example/size",
    )
    source_surface_table = SourceSurfaceTable(
        entity_id="table:women-shoes",
        reason="Visible official table.",
        record_id="table:women-shoes:r1",
        revision_index=1,
        source_discovery=source_discovery,
        state="accepted",
        supersedes_record_id=None,
    )
    source_surface_url = SourceSurfaceUrl(
        entity_id="url:https://brand.example/size",
        evidence_path_list=[],
        reason="Opened the official guide.",
        record_id="url:https://brand.example/size:r1",
        revision_index=1,
        state="opened",
        supersedes_record_id=None,
        url="https://brand.example/size",
        worklist_key_list=["women_shoes"],
    )

    inventory = SourceSurfaceInventory(
        discovery_query_list=[discovery_query],
        product_type_sex_worklist=[product_type_sex],
        table_list=[source_surface_table],
        url_list=[source_surface_url],
    )

    assert inventory.discovery_query_list == [discovery_query]
    assert inventory.product_type_sex_worklist == [product_type_sex]
    assert inventory.table_list == [source_surface_table]
    assert inventory.url_list == [source_surface_url]
    assert not isinstance(inventory, JsonlRecord)


def test_source_discovery_state_owns_only_relative_jsonl_paths() -> None:
    """Persist deterministic JSONL references without copying incremental rows into state."""
    import brand_size_chart.model as model

    SourceDiscoveryState = model.SourceDiscoveryState
    assert SourceDiscoveryState.__bases__ == (WorkflowStepCodexState,)
    source_discovery_state = SourceDiscoveryState(attempt_index=1, state="ready")

    assert source_discovery_state.discovery_query_jsonl_path == "discovery_query.jsonl"
    assert source_discovery_state.product_type_sex_worklist_jsonl_path == "product_type_sex_worklist.jsonl"
    assert source_discovery_state.table_jsonl_path == "table.jsonl"
    assert source_discovery_state.url_jsonl_path == "url.jsonl"
    assert {
        "discovery_query_list",
        "product_type_sex_worklist",
        "table_list",
        "url_list",
    }.isdisjoint(SourceDiscoveryState.model_fields)
    with pytest.raises(ValidationError, match="relative JSONL path"):
        SourceDiscoveryState(attempt_index=1, state="ready", table_jsonl_path="/tmp/table.jsonl")


def test_table_extraction_has_no_artifact_batch_wrapper() -> None:
    """Keep cross-step table extraction as a direct artifact handle list."""
    import brand_size_chart.model as model
    from brand_size_chart.model import TableExtractionDeltaBatchResult

    assert not hasattr(model, "TableExtractionArtifactBatchResult")
    assert TableExtractionDeltaBatchResult.__module__ == "brand_size_chart.model.source"


def test_table_extraction_uses_artifact_handle_only() -> None:
    """Keep table extraction cross-step data as artifact handles without embedded charts."""
    import brand_size_chart.model as model
    from brand_size_chart.model import CanonicalSelectionResult
    from brand_size_chart.model import TableExtractionArtifact

    assert not hasattr(model, "TableExtraction")
    assert not hasattr(model, "TableExtractionBatchResult")
    assert not hasattr(model, "TableExtractionArtifactBatchResult")
    assert not hasattr(model, "CanonicalSelectionTableContext")
    assert "chart" not in TableExtractionArtifact.model_fields
    assert "applicability_status" not in TableExtractionArtifact.model_fields
    assert "source_discovery" in TableExtractionArtifact.model_fields
    assert "status" not in CanonicalSelectionResult.model_fields


def test_applicability_status_contains_only_produced_values() -> None:
    """Keep canonical-selection applicability status aligned with Python derivation."""

    assert set(get_args(ApplicabilityStatus)) == {
        "priority_country_official",
        "official_global",
        "official_eu_consensus",
        "official_cross_locale_consensus",
        "unknown_blocked",
    }


def test_applicability_status_eligibility_is_owned_by_applicability_module() -> None:
    """Keep canonical applicability eligibility beside applicability derivation."""
    import brand_size_chart.model.base as model_base
    import brand_size_chart.source as source
    from brand_size_chart.source.applicability import is_applicability_status_canonical

    assert not hasattr(model_base, "APPLICABILITY_STATUS_CANONICAL_SET")
    assert not hasattr(source, "APPLICABILITY_STATUS_CANONICAL_SET")
    assert {
        applicability_status
        for applicability_status in get_args(ApplicabilityStatus)
        if is_applicability_status_canonical(applicability_status)
    } == {
        "priority_country_official",
        "official_global",
        "official_eu_consensus",
        "official_cross_locale_consensus",
    }
    assert is_applicability_status_canonical("priority_country_official")
    assert not is_applicability_status_canonical("unknown_blocked")


def test_step_result_models_have_only_structured_decision_fields() -> None:
    """Keep step result models free of unstructured or duplicated decision channels."""
    import brand_size_chart.model as model

    from brand_size_chart.model import CanonicalSelectionResult
    from brand_size_chart.model import CoverageDecisionResult
    from brand_size_chart.model import CoveredProductType
    from brand_size_chart.model import SourceDiscovery
    from brand_size_chart.model import TableExtractionArtifact
    from brand_size_chart.model import TableExtractionDelta
    from brand_size_chart.model import TableExtractionDeltaBatchResult
    from brand_size_chart.model import TableExtractionExecplanItem

    for model_class in [
        BrowserActionResult,
        TableExtractionDeltaBatchResult,
        CoverageDecisionResult,
        CanonicalSelectionResult,
    ]:
        assert "message" not in model_class.model_fields

    assert hasattr(model, "SourceDiscoveryResult")
    assert hasattr(model, "TableExtractionResult")
    assert "source_priority" not in SourceDiscovery.model_fields
    assert "source_type" not in SourceDiscovery.model_fields
    assert "error_list" not in TableExtractionDeltaBatchResult.model_fields
    assert "error_list" not in CanonicalSelectionResult.model_fields
    assert "error_list" not in CoverageDecisionResult.model_fields
    assert "no_table_reason_list" not in BrowserActionResult.model_fields
    assert "item_index" not in TableExtractionExecplanItem.model_fields
    assert "is_covered" not in CoveredProductType.model_fields
    assert "chart_path" in CoveredProductType.model_fields
    assert "status" not in BrowserActionResult.model_fields
    assert "uncovered_product_type_gap_list" in CoverageDecisionResult.model_fields
    assert "product_type_hint_list" not in SourceDiscovery.model_fields
    assert "product_type_hint_list" not in TableExtractionArtifact.model_fields
    assert "product_type_hint_list" not in TableExtractionDelta.model_fields
    assert "product_type_hint_list" not in TableExtractionExecplanItem.model_fields
    assert "state" not in SourceTypeResult.model_fields
    assert "source_discovery_result" in SourceTypeResult.model_fields
    assert "table_extraction_result" in SourceTypeResult.model_fields
    assert "table_extraction_list" not in SourceTypeResult.model_fields
    assert "source_discovery_list" in SourceDiscoveryResult.model_fields
    assert "table_extraction_list" in TableExtractionResult.model_fields


def test_step_input_models_are_strict() -> None:
    """Reject unknown fields in public step-input models."""

    with pytest.raises(ValidationError):
        SourceDiscoveryInput(
            evidence_write_target=ArtifactWriteTarget(artifact_path="a", filesystem_path="/tmp/a"),
            workflow_input=SourceTypeWorkflowInput(
                brand_input=BrandInput(
                    parsed_brand_key="defacto",
                    parsed_brand_name="Defacto",
                    raw_brand_name="Defacto",
                    source_line_number=1,
                ),
                prompt_scope=PromptScope(priority_country_code="TR"),
                source_type="official_brand_size_guide",
            ),
            unknown_field=True,
        )


def test_source_discovery_input_uses_workflow_scope_and_template_owned_source_contract() -> None:
    """Keep product scope in workflow input and source instructions outside persisted data."""

    workflow_input = SourceTypeWorkflowInput(
        brand_input=BrandInput(
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            raw_brand_name="Defacto",
            source_line_number=1,
        ),
        prompt_scope=PromptScope(
            priority_country_code="TR",
            product_type_request_list=["women dress"],
        ),
        source_type="official_brand_product_page",
    )
    step_input = SourceDiscoveryInput(
        evidence_write_target=ArtifactWriteTarget(artifact_path="evidence", filesystem_path="/tmp/evidence"),
        workflow_input=workflow_input,
    )
    catalog_item = SourceTypeCatalogItem(
        requires_product_type=True,
        source_type="official_brand_product_page",
    )

    assert set(SourceDiscoveryInput.model_fields) == {
        "evidence_write_target",
        "step_instruction_list",
        "workflow_input",
    }
    assert step_input.workflow_input.prompt_scope.product_type_request_list == ["women dress"]
    assert set(SourceTypeCatalogItem.model_fields) == {"requires_product_type", "source_type"}
    assert catalog_item.source_type == workflow_input.source_type


def test_table_extraction_artifact_reuses_source_discovery_identity() -> None:
    """Carry one stable source-table object instead of mirrored identity fields."""

    source_discovery = SourceDiscovery(
        country_code_list=["TR"],
        evidence_path_list=["workflow/run/step/source_discover/evidence/table.json"],
        size_group_key="women_upper",
        source_title="Women upper clothing",
        source_url="https://brand.example/size-guide",
    )
    artifact = TableExtractionArtifact(
        applicability_description="Applies to women's upper garments.",
        chart_path="workflow/run/step/table_extract/chart/women_upper.json",
        evidence_path_list=["workflow/run/step/table_extract/evidence/women_upper/table.json"],
        source_discovery=source_discovery,
        source_type="official_brand_size_guide",
    )

    assert set(TableExtractionArtifact.model_fields) == {
        "applicability_description",
        "chart_path",
        "evidence_path_list",
        "source_discovery",
        "source_type",
    }
    assert artifact.source_discovery is source_discovery
    assert artifact.source_discovery.size_group_key == "women_upper"


def test_step_input_models_use_input_names_only() -> None:
    """Expose only public step-input class names."""

    for model_class in [
        CanonicalSelectionInput,
        CoverageDecisionInput,
        SourceDiscoveryInput,
        TableExtractionInput,
        WorkflowRunPromptApplyInput,
    ]:
        assert model_class.__name__.endswith("Input")


def test_brand_output_step_has_one_persisted_owner_for_selected_tables() -> None:
    """Persist selected output items once without retaining the larger dependency set."""

    from brand_size_chart.model import BrandOutputInput, BrandOutputInputSource

    assert set(BrandOutputInput.model_fields) == {"output_item_list"}
    assert "coverage_decision_result" not in BrandOutputInputSource.model_fields


def test_canonical_selection_result_exposes_python_derived_unresolved_groups() -> None:
    """Expose unresolved physical groups without restoring a Codex-owned conflict payload."""

    from brand_size_chart.model import (
        CanonicalSelectionActionOutput,
        CanonicalSelectionGap,
        CanonicalSelectionResult,
    )

    assert set(CanonicalSelectionActionOutput.model_fields) == {"canonical_selection_list"}
    assert set(CanonicalSelectionGap.model_fields) == {"candidate_chart_path_list", "size_group_key"}
    assert set(CanonicalSelectionResult.model_fields) == {
        "canonical_selection_list",
        "unresolved_size_group_gap_list",
    }


def test_canonical_selection_result_derives_unresolved_equal_priority_group() -> None:
    """Publish an omitted equal-priority group without duplicating candidate metadata in Codex output."""
    from brand_size_chart.model import CanonicalSelectionActionOutput, CanonicalSelectionCandidate

    first_table = TableExtractionArtifact(
        chart_path="workflow/brand/step/table_extract/chart/first.json",
        source_discovery=SourceDiscovery(
            country_code_list=["TR"],
            size_group_key="women_upper",
            source_title="First table",
            source_url="https://brand.example/first",
        ),
        source_type="official_brand_size_guide",
    )
    second_table = first_table.model_copy(
        update={
            "chart_path": "workflow/brand/step/table_extract/chart/second.json",
            "source_discovery": first_table.source_discovery.model_copy(
                update={
                    "source_title": "Second table",
                    "source_url": "https://brand.example/second",
                }
            ),
        }
    )
    candidate_list = [
        CanonicalSelectionCandidate(
            applicability_status="priority_country_official",
            source_priority=20,
            table_extraction_artifact=first_table,
        ),
        CanonicalSelectionCandidate(
            applicability_status="priority_country_official",
            source_priority=20,
            table_extraction_artifact=second_table,
        ),
    ]

    result = CanonicalSelectionResult.from_action_output(
        CanonicalSelectionActionOutput(canonical_selection_list=[]),
        candidate_list,
    )

    assert result.canonical_selection_list == []
    assert result.unresolved_size_group_gap_list[0].size_group_key == "women_upper"
    assert result.unresolved_size_group_gap_list[0].candidate_chart_path_list == [
        first_table.chart_path,
        second_table.chart_path,
    ]


def test_pydantic_models_validate_representative_artifacts() -> None:
    """Validate representative JSON artifacts through Pydantic models."""
    chart = BrandSizeChart(
        description="Representative upper female brand size chart.",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[
                    BrandSizeChartMeasurement(max_value="88", min_value="84", name="chest", unit="cm"),
                ],
                size_label="S",
            )
        ],
    )
    brand_result = BrandResult(
        status="success",
        brand_output_result=BrandOutputResult(
            size_chart_path_list=["brand_size_chart/brand/ipekyol/size_chart/women.json"]
        ),
        canonical_selection_result=CanonicalSelectionResult(
            canonical_selection_list=[],
            unresolved_size_group_gap_list=[],
        ),
        coverage_decision_result=CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[],
        ),
        error_list=[],
        parsed_brand_key="ipekyol",
        parsed_brand_name="İpekyol",
        source_type_result_list=[
            SourceTypeResult(
                status="success",
                source_type="official_brand_size_guide",
                source_discovery_result=SourceDiscoveryResult(),
                table_extraction_result=TableExtractionResult(),
            )
        ],
        source_type_skip_list=[],
    )
    run_result = RunResult(
        status="success",
        brand_list_parse_warning_list=[],
        brand_result_list=[brand_result],
        error_list=[],
        prompt_scope=PromptScope(),
        warning_list=[],
    )

    assert BrandSizeChart.model_validate(chart.model_dump(mode="json")) == chart
    assert BrandResult.model_validate(brand_result.model_dump(mode="json")) == brand_result
    assert RunResult.model_validate(run_result.model_dump(mode="json")) == run_result
    assert "message" not in BrandResult.model_fields
    assert "message" not in RunResult.model_fields


def test_table_extraction_rejects_unsafe_artifact_components() -> None:
    """Reject step results that would create unsafe artifact paths."""
    payload = {
        "chart_path": "brand_size_chart_audit/brand/brand/source_type/source/table_extract/chart/Upper/Female.json",
        "source_discovery": {
            "country_code_list": ["TR"],
            "size_group_key": "Upper/Female",
            "source_title": "Official size guide",
            "source_url": "https://brand.example/official-size-guide",
        },
        "source_type": "official_brand_size_guide",
    }

    try:
        TableExtractionArtifact.model_validate(payload)
    except ValueError as exc:
        message = str(exc)
    else:
        message = ""

    assert "size_group_key" in message


@pytest.mark.parametrize(
    ("model_class", "payload"),
    [
        (
            SourceSurfaceDiscoveryQuery,
            {
                "entity_id": "query:official-site",
                "evidence_path_list": [],
                "query": "site:defacto.com.tr beden tablosu",
                "reason": "Searched official site.",
                "record_id": "query:official-site:r1",
                "revision_index": 1,
                "state": "visited",
                "supersedes_record_id": None,
            },
        ),
        (
            SourceSurfaceProductTypeSex,
            {
                "entity_id": "worklist:women-shoes",
                "evidence_path_list": [],
                "product_type": "women shoes",
                "reason": "Needs coverage.",
                "record_id": "worklist:women-shoes:r1",
                "revision_index": 1,
                "sex": "women",
                "state": "pending",
                "supersedes_record_id": None,
                "worklist_key": "women_shoes",
            },
        ),
        (
            SourceSurfaceTable,
            {
                "entity_id": "table:women-upper",
                "reason": "Visible source table.",
                "record_id": "table:women-upper:r1",
                "revision_index": 1,
                "source_discovery": {
                    "country_code_list": ["TR"],
                    "evidence_path_list": [],
                    "size_group_key": "women_upper",
                    "source_title": "Women upper",
                    "source_url": "https://brand.example/size",
                },
                "state": "done",
                "supersedes_record_id": None,
            },
        ),
        (
            SourceSurfaceUrl,
            {
                "entity_id": "url:https://brand.example/size",
                "evidence_path_list": [],
                "reason": "Opened official guide.",
                "record_id": "url:https://brand.example/size:r1",
                "revision_index": 1,
                "state": "done",
                "supersedes_record_id": None,
                "url": "https://brand.example/size",
            },
        ),
    ],
)
def test_source_surface_inventory_rejects_unknown_state(model_class: type[object], payload: dict[str, object]) -> None:
    """Reject arbitrary source-surface state strings in persistent inventory."""
    with pytest.raises(ValueError, match="state"):
        model_class.model_validate(payload)


def test_source_surface_inventory_uses_single_table_list() -> None:
    """Use one table and URL list with item-level state for discovered inventory."""
    payload = {
        "discovery_query_list": [],
        "product_type_sex_worklist": [],
        "url_list": [],
        "table_list": [],
    }

    inventory = SourceSurfaceInventory.model_validate(payload)

    assert inventory.table_list == []
    assert inventory.url_list == []
    for forbidden_field in [
        "accepted_table_list",
        "non_returned_table_list",
        "duplicate_or_equivalent_table_list",
        "opened_url_list",
        "rejected_url_list",
    ]:
        with pytest.raises(ValueError, match=forbidden_field):
            SourceSurfaceInventory.model_validate({**payload, forbidden_field: []})


def test_source_surface_table_rejects_worklist_links() -> None:
    """Keep product worklist closure on URL inventory entries, not table rows."""
    payload = {
        "entity_id": "table:women-upper",
        "reason": "Visible table.",
        "record_id": "table:women-upper:r1",
        "revision_index": 1,
        "source_discovery": {
            "country_code_list": ["TR"],
            "evidence_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/evidence.json"],
            "size_group_key": "women_upper",
            "source_title": "Women upper",
            "source_url": "https://brand.example/size",
        },
        "state": "accepted",
        "supersedes_record_id": None,
        "worklist_key_list": ["women_upper"],
    }

    with pytest.raises(ValueError, match="worklist_key_list"):
        SourceSurfaceTable.model_validate(payload)


def test_source_surface_inventory_no_table_reasons_ignore_equivalent_rows() -> None:
    """Keep equivalent rows out of terminal no-table summaries."""
    inventory = SourceSurfaceInventory.model_validate(
        {
            "discovery_query_list": [],
            "product_type_sex_worklist": [],
            "url_list": [],
            "table_list": [
                {
                    "entity_id": "table:women-upper-duplicate",
                    "reason": "Duplicate of women upper.",
                    "record_id": "table:women-upper-duplicate:r1",
                    "revision_index": 1,
                    "source_discovery": {
                        "country_code_list": ["TR"],
                        "evidence_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/evidence.json"],
                        "size_group_key": "women_upper",
                        "source_title": "Women upper duplicate",
                        "source_url": "https://brand.example/duplicate",
                    },
                    "state": "equivalent",
                    "supersedes_record_id": None,
                },
                {
                    "entity_id": "table:women-lower-equivalent",
                    "reason": "Equivalent to women lower.",
                    "record_id": "table:women-lower-equivalent:r1",
                    "revision_index": 1,
                    "source_discovery": {
                        "country_code_list": ["TR"],
                        "evidence_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/evidence.json"],
                        "size_group_key": "women_lower",
                        "source_title": "Women lower equivalent",
                        "source_url": "https://brand.example/equivalent",
                    },
                    "state": "equivalent",
                    "supersedes_record_id": None,
                },
                {
                    "entity_id": "table:women-shoes-us",
                    "reason": "Filtered by market ladder.",
                    "record_id": "table:women-shoes-us:r1",
                    "revision_index": 1,
                    "source_discovery": {
                        "country_code_list": ["US"],
                        "evidence_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/evidence.json"],
                        "size_group_key": "women_shoes",
                        "source_title": "Women shoes US",
                        "source_url": "https://brand.example/us",
                    },
                    "state": "market_filtered",
                    "supersedes_record_id": None,
                },
            ],
        }
    )

    assert inventory.no_table_reason_list_get() == ["Filtered by market ladder."]


def test_coverage_decision_product_type_gap_is_public_schema_model() -> None:
    """Expose structured uncovered product-type coverage gaps."""

    gap = CoverageDecisionProductTypeGap(product_type="women shoes", reason="No matching verified table.")

    assert gap.product_type == "women shoes"
    assert gap.reason == "No matching verified table."
