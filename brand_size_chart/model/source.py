"""Source discovery and table extraction models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from brand_size_chart.model.base import (
    COUNTRY_CODE_PATTERN,
    IdentifierComponent,
    SOURCE_COUNTRY_CODE_SPECIAL_SET,
    ApplicabilityStatus,
    StageStatus,
    StrictBaseModel,
)
from brand_size_chart.model.chart import BrandSizeChart

SourceSurfaceDiscoveryQueryState = Literal["searched", "failed"]
SourceSurfaceProductTypeSexState = Literal["active", "rejected"]
SourceSurfaceTableState = Literal["accepted", "duplicate", "equivalent", "market_filtered", "rejected"]
SourceSurfaceUrlState = Literal["candidate", "opened", "rejected"]


class BrowsingError(StrictBaseModel):
    """Browser or network failure for one concrete URL."""

    error: str
    url: str

    @field_validator("error", "url")
    @classmethod
    def text_validate(cls, value: str) -> str:
        """Validate one browsing-error text field.

        Args:
            value: Candidate text value.

        Returns:
            Trimmed non-empty text value.

        Raises:
            ValueError: If the text is empty after trimming.
        """
        text = value.strip()
        if not text:
            raise ValueError("browsing error fields must be non-empty strings")
        return text


class SourceSurfaceDiscoveryQuery(StrictBaseModel):
    """Discovery query recorded in the source-surface inventory."""

    evidence_path_list: list[str]
    query: str
    reason: str
    state: SourceSurfaceDiscoveryQueryState


class SourceSurfaceProductTypeSex(StrictBaseModel):
    """Product-type and sex worklist item recorded in the source-surface inventory."""

    evidence_path_list: list[str]
    product_type: str
    reason: str
    sex: str
    state: SourceSurfaceProductTypeSexState
    worklist_key: IdentifierComponent


class SourceSurfaceTable(StrictBaseModel):
    """Concrete table entry recorded in the source-surface inventory."""

    country_code_list: list[str]
    covered_product_type_list: list[str]
    evidence_path_list: list[str]
    reason: str
    size_group_key: IdentifierComponent
    source_title: str
    source_url: str
    state: SourceSurfaceTableState
    worklist_key_list: list[IdentifierComponent] = Field(default_factory=list)

    @field_validator("country_code_list")
    @classmethod
    def country_code_list_validate(cls, value: list[str]) -> list[str]:
        """Validate source-surface table market country codes.

        Args:
            value: Candidate country-code list.

        Returns:
            Normalized country-code list.

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


class SourceSurfaceUrl(StrictBaseModel):
    """URL entry recorded in the source-surface inventory."""

    evidence_path_list: list[str]
    reason: str
    source_boundary_role: str
    state: SourceSurfaceUrlState
    url: str
    worklist_key_list: list[IdentifierComponent] = Field(default_factory=list)


class SourceSurfaceInventory(StrictBaseModel):
    """Canonical source-surface inventory for one source-discovery stage."""

    accepted_table_list: list[SourceSurfaceTable]
    browsing_error_list: list[BrowsingError]
    candidate_url_list: list[SourceSurfaceUrl]
    discovery_query_list: list[SourceSurfaceDiscoveryQuery]
    non_returned_table_list: list[SourceSurfaceTable]
    opened_url_list: list[SourceSurfaceUrl]
    product_type_sex_worklist: list[SourceSurfaceProductTypeSex]
    rejected_url_list: list[SourceSurfaceUrl]


class SourceDiscovery(StrictBaseModel):
    """Discovered source candidate for one brand."""

    confidence: float = Field(ge=0.0, le=1.0)
    country_code_list: list[str]
    evidence_path_list: list[str] = Field(default_factory=list)
    product_type_hint_list: list[str] = Field(default_factory=list)
    size_group_key: IdentifierComponent
    source_note_list: list[str] = Field(default_factory=list)
    source_priority: int = Field(ge=1)
    source_title: str
    source_type: IdentifierComponent
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


class SourceDiscoveryResult(StrictBaseModel):
    """Discovery result for one source type."""

    browsing_error_list: list[BrowsingError] = Field(default_factory=list)
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
    chart_path: str = ""
    evidence_path_list: list[str] = Field(default_factory=list)
    product_type_hint_list: list[str] = Field(default_factory=list)
    size_group_key: IdentifierComponent
    source_title: str
    source_type: IdentifierComponent
    source_url: str


class TableExtractionArtifact(StrictBaseModel):
    """Extracted size-chart table metadata with chart artifact reference."""

    applicability_description: str = ""
    applicability_status: ApplicabilityStatus = "unknown_blocked"
    chart_path: str
    evidence_path_list: list[str] = Field(default_factory=list)
    product_type_hint_list: list[str] = Field(default_factory=list)
    size_group_key: IdentifierComponent
    source_title: str
    source_type: IdentifierComponent
    source_url: str


class TableExtractExecplanItem(StrictBaseModel):
    """Durable table-extraction worklist item."""

    chart_path: str
    error: str
    item_index: int = Field(ge=1)
    size_group_key: IdentifierComponent
    source_title: str
    source_type: IdentifierComponent
    source_url: str
    state: Literal["pending", "extracted", "failed"]


class TableExtractionArtifactBatchResult(StrictBaseModel):
    """Batch extraction result with generated chart artifact references."""

    browsing_error_list: list[BrowsingError] = Field(default_factory=list)
    error_list: list[str] = Field(default_factory=list)
    message: str
    source_type: str
    status: StageStatus
    table_extraction_artifact_list: list[TableExtractionArtifact]


class TableExtractionBatchResult(StrictBaseModel):
    """Batch extraction result for one source type."""

    browsing_error_list: list[BrowsingError] = Field(default_factory=list)
    error_list: list[str] = Field(default_factory=list)
    message: str
    source_type: str
    status: StageStatus
    table_extraction_list: list[TableExtraction]
