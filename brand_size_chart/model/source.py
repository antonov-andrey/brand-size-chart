"""Source discovery and table extraction models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from brand_size_chart.identifier import dbos_identifier_component
from brand_size_chart.model.base import (
    COUNTRY_CODE_PATTERN,
    SOURCE_COUNTRY_CODE_SPECIAL_SET,
    ApplicabilityStatus,
    StageStatus,
    StrictBaseModel,
)
from brand_size_chart.model.chart import BrandSizeChart


class SourceDiscovery(StrictBaseModel):
    """Discovered source candidate for one brand."""

    confidence: float = Field(ge=0.0, le=1.0)
    country_code_list: list[str]
    evidence_path_list: list[str] = Field(default_factory=list)
    product_type_hint_list: list[str] = Field(default_factory=list)
    size_group_key: str
    source_note_list: list[str] = Field(default_factory=list)
    source_priority: int = Field(ge=1)
    source_title: str
    source_type: str
    source_url: str

    @field_validator("country_code_list")
    @classmethod
    def country_code_list_validate(cls, value: list[str]) -> list[str]:
        """Validate source-market country codes.

        Args:
            value: Candidate country code list.

        Returns:
            Normalized country code list.

        Raises:
            ValueError: If one code is neither alpha-2 nor a supported market-scope marker.
        """
        normalized_country_code_list = []
        for country_code in value:
            normalized_country_code = country_code.strip().upper()
            if normalized_country_code not in SOURCE_COUNTRY_CODE_SPECIAL_SET and not COUNTRY_CODE_PATTERN.match(
                normalized_country_code
            ):
                raise ValueError("country_code_list values must be alpha-2 country codes, GLOBAL, or EU")
            normalized_country_code_list.append(normalized_country_code)
        return normalized_country_code_list

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


class TableExtractionArtifact(StrictBaseModel):
    """Extracted size-chart table metadata with chart artifact reference."""

    applicability_description: str = ""
    applicability_status: ApplicabilityStatus = "unknown_blocked"
    chart_path: str
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


class TableExtractionArtifactBatchResult(StrictBaseModel):
    """Batch extraction result with generated chart artifact references."""

    error_list: list[str] = Field(default_factory=list)
    message: str
    source_type: str
    status: StageStatus
    table_extraction_artifact_list: list[TableExtractionArtifact]


class TableExtractionBatchResult(StrictBaseModel):
    """Batch extraction result for one source type."""

    error_list: list[str] = Field(default_factory=list)
    message: str
    source_type: str
    status: StageStatus
    table_extraction_list: list[TableExtraction]
