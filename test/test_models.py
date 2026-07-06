"""Tests for Pydantic result models."""

import pytest

from brand_size_chart.model import (
    BrandResult,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    PromptScope,
    RunResult,
    SourceSurfaceDiscoveryQuery,
    SourceSurfaceInventory,
    SourceSurfaceProductTypeSex,
    SourceSurfaceTable,
    SourceSurfaceUrl,
    SourceTypeSummary,
    TableExtraction,
    TableExtractionBatchResult,
)


def test_model_package_exports_existing_public_models() -> None:
    """Keep public model imports stable while moving model owners into the package."""
    from brand_size_chart.model import BrandInput
    from brand_size_chart.model import BrandSizeChart
    from brand_size_chart.model import PromptScope
    from brand_size_chart.model import SourceDiscoveryResult
    from brand_size_chart.model import TableExtraction
    from brand_size_chart.model import TableExtractionBatchResult

    assert BrandInput.__module__ == "brand_size_chart.model.brand"
    assert BrandSizeChart.__module__ == "brand_size_chart.model.chart"
    assert PromptScope.__module__ == "brand_size_chart.model.prompt"
    assert SourceDiscoveryResult.__module__ == "brand_size_chart.model.source"
    assert TableExtraction.__module__ == "brand_size_chart.model.source"
    assert TableExtractionBatchResult.__module__ == "brand_size_chart.model.source"


def test_table_extraction_batch_result_is_public_schema_model() -> None:
    """Expose batch table-extraction results through the public model surface."""
    from brand_size_chart.model import TableExtractionBatchResult

    assert TableExtractionBatchResult.__module__ == "brand_size_chart.model.source"


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
        message="run complete",
        error_list=[],
        parsed_brand_key="ipekyol",
        parsed_brand_name="İpekyol",
        source_type_summary_list=[
            SourceTypeSummary(
                source_priority=600,
                source_type="official_brand_size_guide",
                state="passed",
                verified_size_group_key_list=["upper_female_ru"],
            )
        ],
        canonical_selection_list=[],
        size_chart_path_list=["brand_size_chart/brand/ipekyol/size_chart/women.json"],
        audit_artifact_path_list=["brand_size_chart_audit/brand/ipekyol/brand_result/result.json"],
    )
    run_result = RunResult(
        status="success",
        message="run complete",
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


def test_table_extraction_rejects_unsafe_artifact_components() -> None:
    """Reject stage results that would create unsafe artifact paths."""
    payload = {
        "chart": {
            "description": "Representative upper female brand size chart.",
            "row_list": [
                {
                    "measurement_list": [
                        {"max_value": "88", "min_value": "84", "name": "chest", "unit": "cm"},
                    ],
                    "size_label": "S",
                }
            ],
        },
        "size_group_key": "Upper/Female",
        "source_title": "Official size guide",
        "source_type": "official_brand_size_guide",
        "source_url": "https://brand.example/official-size-guide",
    }

    try:
        TableExtraction.model_validate(payload)
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
                "country_code_list": ["TR"],
                "covered_product_type_list": [],
                "evidence_path_list": [],
                "reason": "Visible source table.",
                "size_group_key": "women_upper",
                "source_title": "Women upper",
                "source_url": "https://brand.example/size",
                "state": "done",
            },
        ),
        (
            SourceSurfaceUrl,
            {
                "evidence_path_list": [],
                "reason": "Opened official guide.",
                "source_boundary_role": "official_size_guide",
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


def test_source_surface_inventory_uses_non_returned_table_list() -> None:
    """Use one honest list name for every discovered table not returned as a source candidate."""
    payload = {
        "accepted_table_list": [],
        "browsing_error_list": [],
        "candidate_url_list": [],
        "discovery_query_list": [],
        "non_returned_table_list": [],
        "opened_url_list": [],
        "product_type_sex_worklist": [],
        "rejected_url_list": [],
    }

    inventory = SourceSurfaceInventory.model_validate(payload)

    assert inventory.non_returned_table_list == []
    with pytest.raises(ValueError, match="duplicate_or_equivalent_table_list"):
        SourceSurfaceInventory.model_validate({**payload, "duplicate_or_equivalent_table_list": []})
