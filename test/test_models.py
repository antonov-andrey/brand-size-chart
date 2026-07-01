"""Tests for Pydantic result models and generated JSON schemas."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from brand_size_chart.model import (
    BrandResult,
    BrandSizeChart,
    PromptScope,
    RunResult,
    SourceTypeSummary,
    TableExtraction,
    schema_model_map_get,
)


def test_model_package_exports_existing_public_models() -> None:
    """Keep public model imports stable while moving model owners into the package."""
    from brand_size_chart.model import BrandInput
    from brand_size_chart.model import BrandSizeChart
    from brand_size_chart.model import PromptScope
    from brand_size_chart.model import SourceDiscoveryResult
    from brand_size_chart.model import TableExtraction

    assert BrandInput.__module__ == "brand_size_chart.model.brand"
    assert BrandSizeChart.__module__ == "brand_size_chart.model.chart"
    assert PromptScope.__module__ == "brand_size_chart.model.prompt"
    assert SourceDiscoveryResult.__module__ == "brand_size_chart.model.source"
    assert TableExtraction.__module__ == "brand_size_chart.model.source"


def test_generated_schemas_validate_representative_artifacts() -> None:
    """Validate representative JSON artifacts through generated Pydantic schemas."""
    schema_dir = Path("brand_size_chart/schema")

    chart = BrandSizeChart(
        description="Representative upper female brand size chart.",
        row_list=[
            {
                "measurement_list": [
                    {"max_value": "88", "min_value": "84", "name": "chest", "unit": "cm"},
                ],
                "size_label": "S",
            }
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

    artifact_by_schema = {
        "brand_result.schema.json": brand_result.model_dump(mode="json"),
        "brand_size_chart.schema.json": chart.model_dump(mode="json"),
        "run_result.schema.json": run_result.model_dump(mode="json"),
    }

    assert schema_model_map_get()
    for schema_file_name, artifact in artifact_by_schema.items():
        schema = json.loads((schema_dir / schema_file_name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(artifact)


def test_schema_directory_matches_pydantic_model_map() -> None:
    """Keep generated schema files in sync with Pydantic result model owners."""
    schema_dir = Path("brand_size_chart/schema")
    expected_schema_file_name_set = {f"{schema_name}.schema.json" for schema_name in schema_model_map_get()}
    actual_schema_file_name_set = {schema_path.name for schema_path in schema_dir.glob("*.schema.json")}

    assert actual_schema_file_name_set == expected_schema_file_name_set


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
