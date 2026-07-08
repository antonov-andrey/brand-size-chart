"""Tests for Pydantic result models."""

from typing import get_args

import pytest
from workflow_container_runtime.stage import BrowserActionResult

from brand_size_chart.model import (
    ApplicabilityStatus,
    BrandResult,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    CoverageDecisionProductTypeGap,
    PromptScope,
    RunResult,
    SourceDiscovery,
    SourceSurfaceDiscoveryQuery,
    SourceSurfaceInventory,
    SourceSurfaceProductTypeSex,
    SourceSurfaceTable,
    SourceSurfaceUrl,
    SourceTypeResult,
    TableExtractionArtifact,
    TableExtractionDeltaBatchResult,
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


def test_table_extraction_has_no_artifact_batch_wrapper() -> None:
    """Keep cross-stage table extraction as a direct artifact handle list."""
    import brand_size_chart.model as model
    from brand_size_chart.model import TableExtractionDeltaBatchResult

    assert not hasattr(model, "TableExtractionArtifactBatchResult")
    assert TableExtractionDeltaBatchResult.__module__ == "brand_size_chart.model.source"


def test_table_extraction_uses_artifact_handle_only() -> None:
    """Keep table extraction cross-stage data as artifact handles without embedded charts."""
    import brand_size_chart.model as model
    from brand_size_chart.model import CanonicalSelectionResult
    from brand_size_chart.model import TableExtractionArtifact

    assert not hasattr(model, "TableExtraction")
    assert not hasattr(model, "TableExtractionBatchResult")
    assert not hasattr(model, "TableExtractionArtifactBatchResult")
    assert not hasattr(model, "CanonicalSelectionTableContext")
    assert "chart" not in TableExtractionArtifact.model_fields
    assert "applicability_status" not in TableExtractionArtifact.model_fields
    assert "country_code_list" in TableExtractionArtifact.model_fields
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


def test_stage_result_models_have_only_structured_decision_fields() -> None:
    """Keep stage result models free of unstructured or duplicated decision channels."""
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

    assert not hasattr(model, "SourceDiscoveryResult")
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
    assert "table_extraction_list" in SourceTypeResult.model_fields


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
        error_list=[],
        parsed_brand_key="ipekyol",
        parsed_brand_name="İpekyol",
        source_type_result_list=[
            SourceTypeResult(
                source_type="official_brand_size_guide",
            )
        ],
        canonical_selection_list=[],
        size_chart_path_list=["brand_size_chart/brand/ipekyol/size_chart/women.json"],
        audit_artifact_path_list=["brand_size_chart_audit/brand/ipekyol/brand_result/result.json"],
    )
    run_result = RunResult(
        status="success",
        error_list=[],
        workflow_run_id="run-01",
        result_dir="tmp/run-01",
        brand_result_list=[brand_result],
        prompt_scope=PromptScope(),
        warning_list=[],
    )

    assert BrandSizeChart.model_validate(chart.model_dump(mode="json")) == chart
    assert BrandResult.model_validate(brand_result.model_dump(mode="json")) == brand_result
    assert RunResult.model_validate(run_result.model_dump(mode="json")) == run_result
    assert "message" not in BrandResult.model_fields
    assert "message" not in RunResult.model_fields


def test_table_extraction_rejects_unsafe_artifact_components() -> None:
    """Reject stage results that would create unsafe artifact paths."""
    payload = {
        "chart_path": "brand_size_chart_audit/brand/brand/source_type/source/table_extract/chart/Upper/Female.json",
        "country_code_list": ["TR"],
        "size_group_key": "Upper/Female",
        "source_title": "Official size guide",
        "source_type": "official_brand_size_guide",
        "source_url": "https://brand.example/official-size-guide",
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
                "evidence_path_list": [],
                "query": "site:defacto.com.tr beden tablosu",
                "reason": "Searched official site.",
                "state": "visited",
            },
        ),
        (
            SourceSurfaceProductTypeSex,
            {
                "evidence_path_list": [],
                "product_type": "women shoes",
                "reason": "Needs coverage.",
                "sex": "women",
                "state": "pending",
                "worklist_key": "women_shoes",
            },
        ),
        (
            SourceSurfaceTable,
            {
                "reason": "Visible source table.",
                "source_discovery": {
                    "country_code_list": ["TR"],
                    "evidence_path_list": [],
                    "size_group_key": "women_upper",
                    "source_title": "Women upper",
                    "source_url": "https://brand.example/size",
                },
                "state": "done",
            },
        ),
        (
            SourceSurfaceUrl,
            {
                "evidence_path_list": [],
                "reason": "Opened official guide.",
                "state": "done",
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
        "reason": "Visible table.",
        "source_discovery": {
            "country_code_list": ["TR"],
            "evidence_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/evidence.json"],
            "size_group_key": "women_upper",
            "source_title": "Women upper",
            "source_url": "https://brand.example/size",
        },
        "state": "accepted",
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
                    "reason": "Duplicate of women upper.",
                    "source_discovery": {
                        "country_code_list": ["TR"],
                        "evidence_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/evidence.json"],
                        "size_group_key": "women_upper",
                        "source_title": "Women upper duplicate",
                        "source_url": "https://brand.example/duplicate",
                    },
                    "state": "equivalent",
                },
                {
                    "reason": "Equivalent to women lower.",
                    "source_discovery": {
                        "country_code_list": ["TR"],
                        "evidence_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/evidence.json"],
                        "size_group_key": "women_lower",
                        "source_title": "Women lower equivalent",
                        "source_url": "https://brand.example/equivalent",
                    },
                    "state": "equivalent",
                },
                {
                    "reason": "Filtered by market ladder.",
                    "source_discovery": {
                        "country_code_list": ["US"],
                        "evidence_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/evidence.json"],
                        "size_group_key": "women_shoes",
                        "source_title": "Women shoes US",
                        "source_url": "https://brand.example/us",
                    },
                    "state": "market_filtered",
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
