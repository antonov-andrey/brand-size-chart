"""Pydantic result models and generated-schema support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from brand_size_chart.identifier import dbos_identifier_component

APPLICABILITY_STATUS_CANONICAL_SET = {
    "turkey_official",
    "official_global",
    "official_eu_consensus",
    "official_cross_locale_consensus",
}
ApplicabilityStatus = Literal[
    "turkey_official",
    "official_global",
    "official_eu_consensus",
    "official_cross_locale_consensus",
    "duplicate_exact",
    "duplicate_units_only",
    "market_conflict",
    "comparison_only",
    "unknown_blocked",
]
StageStatus = Literal["success", "failed", "skipped"]


class StrictBaseModel(BaseModel):
    """Base model with strict validation for workflow artifacts."""

    model_config = ConfigDict(extra="forbid", strict=True)


class BrandInput(StrictBaseModel):
    """Parsed brand input from `brand_list`."""

    parsed_brand_key: str
    parsed_brand_name: str
    raw_brand_name: str
    source_line_number: int = Field(ge=1)


class BrandListParseWarning(StrictBaseModel):
    """Warning emitted while parsing `brand_list`."""

    warning_type: Literal["duplicate_brand", "invalid_brand"]
    message: str
    raw_brand_name: str
    raw_brand_name_list: list[str] = Field(default_factory=list)
    source_line_number: int = Field(ge=1)
    parsed_brand_key: str | None = None


class BrandListParseResult(StrictBaseModel):
    """Parsed `brand_list` result."""

    brand_list: list[BrandInput]
    warning_list: list[BrandListParseWarning]


class PromptStageInstruction(StrictBaseModel):
    """One stage-specific instruction parsed from the workflow-run prompt."""

    instruction: str
    stage_key: str


class PromptScope(StrictBaseModel):
    """Parsed runtime prompt scope used by all stage prompts."""

    product_type_request_list: list[str] = Field(default_factory=list)
    scope_warning_list: list[str] = Field(default_factory=list)
    shared_instruction: str = ""
    source_type_allow_list: list[str] = Field(default_factory=list)
    stage_instruction_list: list[PromptStageInstruction] = Field(default_factory=list)


class StageVerification(StrictBaseModel):
    """Audit verification artifact for one completed stage."""

    artifact_path_list: list[str] = Field(default_factory=list)
    error_list: list[str] = Field(default_factory=list)
    feedback_list: list[str] = Field(default_factory=list)
    message: str
    stage_key: str
    status: StageStatus


class SourceDiscovery(StrictBaseModel):
    """Discovered source candidate for one brand."""

    confidence: float = Field(ge=0.0, le=1.0)
    evidence_path_list: list[str] = Field(default_factory=list)
    product_type_hint_list: list[str] = Field(default_factory=list)
    size_group_key: str
    source_note_list: list[str] = Field(default_factory=list)
    source_priority: int = Field(ge=1)
    source_title: str
    source_type: str
    source_url: str

    @field_validator("size_group_key", "source_type")
    @classmethod
    def identifier_component_validate(cls, value: str) -> str:
        """Validate artifact path components.

        Args:
            value: Candidate path component.

        Returns:
            Validated path component.

        Raises:
            ValueError: If the value is not already a safe identifier component.
        """
        if dbos_identifier_component(value) != value:
            raise ValueError("value must already be a safe DBOS identifier component")
        return value


class SourceDiscoveryResult(StrictBaseModel):
    """Discovery result for one source type."""

    discovered_source_list: list[SourceDiscovery]
    error_list: list[str] = Field(default_factory=list)
    message: str
    source_type: str
    status: StageStatus


class SourceTypeSummary(StrictBaseModel):
    """Summary for one source type loop."""

    blocker_list: list[str] = Field(default_factory=list)
    conflict_list: list[str] = Field(default_factory=list)
    evidence_manifest_path_list: list[str] = Field(default_factory=list)
    source_priority: int = Field(ge=1)
    source_type: str
    state: Literal["passed", "failed", "blocked", "skipped"]
    table_result_path_by_size_group_key_map: dict[str, str] = Field(default_factory=dict)
    verified_size_group_key_list: list[str] = Field(default_factory=list)
    warning_list: list[str] = Field(default_factory=list)


class TableExtraction(StrictBaseModel):
    """Extracted size-chart table from one source."""

    applicability_description: str = ""
    applicability_status: ApplicabilityStatus = "unknown_blocked"
    chart: BrandSizeChart
    evidence_path_list: list[str] = Field(default_factory=list)
    product_type_hint_list: list[str] = Field(default_factory=list)
    size_group_key: str
    source_title: str
    source_type: str
    source_url: str

    @field_validator("size_group_key", "source_type")
    @classmethod
    def identifier_component_validate(cls, value: str) -> str:
        """Validate artifact path components.

        Args:
            value: Candidate path component.

        Returns:
            Validated path component.

        Raises:
            ValueError: If the value is not already a safe identifier component.
        """
        if dbos_identifier_component(value) != value:
            raise ValueError("value must already be a safe DBOS identifier component")
        return value


class CoverageDecision(StrictBaseModel):
    """Coverage decision for one extracted or selected size group."""

    is_covered: bool
    missing_size_list: list[str] = Field(default_factory=list)
    reason: str
    size_group_key: str


class CoverageDecisionResult(StrictBaseModel):
    """Coverage decision result for requested product types."""

    coverage_decision_list: list[CoverageDecision]
    error_list: list[str] = Field(default_factory=list)
    message: str
    status: StageStatus
    uncovered_product_type_list: list[str] = Field(default_factory=list)


class CanonicalSelection(StrictBaseModel):
    """Canonical source selection for one size group."""

    conflict_list: list[str] = Field(default_factory=list)
    selected_source_priority: int = Field(ge=1)
    selected_source_type: str
    selected_source_url: str
    size_group_key: str

    @field_validator("selected_source_type", "size_group_key")
    @classmethod
    def identifier_component_validate(cls, value: str) -> str:
        """Validate artifact path components.

        Args:
            value: Candidate path component.

        Returns:
            Validated path component.

        Raises:
            ValueError: If the value is not already a safe identifier component.
        """
        if dbos_identifier_component(value) != value:
            raise ValueError("value must already be a safe DBOS identifier component")
        return value


class CanonicalSelectionResult(StrictBaseModel):
    """Canonical selection stage result for one brand."""

    canonical_selection_list: list[CanonicalSelection]
    conflict_list: list[str] = Field(default_factory=list)
    error_list: list[str] = Field(default_factory=list)
    message: str
    status: StageStatus


class BrandSizeChartMeasurement(StrictBaseModel):
    """One normalized measurement inside a brand size-chart row."""

    max_value: str
    min_value: str
    name: str
    unit: str


class BrandSizeChartRow(StrictBaseModel):
    """One normalized brand size-chart row."""

    measurement_list: list[BrandSizeChartMeasurement]
    size_label: str


class BrandSizeChart(StrictBaseModel):
    """Canonical brand size-chart table artifact."""

    description: str
    row_list: list[BrandSizeChartRow]


class BrandResult(StrictBaseModel):
    """Workflow result for one brand."""

    audit_artifact_path_list: list[str]
    canonical_selection_list: list[CanonicalSelection]
    error_list: list[str] = Field(default_factory=list)
    message: str
    parsed_brand_key: str
    parsed_brand_name: str
    size_chart_path_list: list[str]
    source_type_summary_list: list[SourceTypeSummary]
    status: StageStatus


class RunResult(StrictBaseModel):
    """Workflow result for one run."""

    brand_result_list: list[BrandResult]
    error_list: list[str] = Field(default_factory=list)
    message: str
    prompt_scope: PromptScope
    result_dir: str
    status: StageStatus
    warning_list: list[BrandListParseWarning]
    workflow_run_id: str


def schema_file_write(schema_dir: Path) -> None:
    """Write JSON Schema files generated from Pydantic models.

    Args:
        schema_dir: Directory where schema files are written.
    """
    schema_dir.mkdir(parents=True, exist_ok=True)
    for schema_name, model_class in schema_model_map_get().items():
        schema_path = schema_dir / f"{schema_name}.schema.json"
        schema_payload = model_class.model_json_schema()
        schema_path.write_text(json.dumps(schema_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def schema_model_map_get() -> dict[str, type[StrictBaseModel]]:
    """Return public artifact schema names and their Pydantic model owners.

    Returns:
        Mapping from schema file stem to model class.
    """
    return {
        "brand_input": BrandInput,
        "brand_list_parse_result": BrandListParseResult,
        "brand_result": BrandResult,
        "brand_size_chart": BrandSizeChart,
        "canonical_selection": CanonicalSelection,
        "canonical_selection_result": CanonicalSelectionResult,
        "coverage_decision": CoverageDecision,
        "coverage_decision_result": CoverageDecisionResult,
        "prompt_scope": PromptScope,
        "prompt_stage_instruction": PromptStageInstruction,
        "run_result": RunResult,
        "source_discovery": SourceDiscovery,
        "source_discovery_result": SourceDiscoveryResult,
        "source_type_summary": SourceTypeSummary,
        "stage_verification": StageVerification,
        "table_extraction": TableExtraction,
    }
