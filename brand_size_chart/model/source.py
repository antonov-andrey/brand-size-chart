"""Source discovery and table extraction models."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from workflow_container_contract import WorkflowResult
from workflow_container_runtime.artifact import JsonlRecord
from workflow_container_runtime.step import BrowsingError, WorkflowStepCodexState

from brand_size_chart.model.base import (
    COUNTRY_CODE_PATTERN,
    IdentifierComponent,
    SOURCE_COUNTRY_CODE_SPECIAL_SET,
    StrictBaseModel,
)

SourceSurfaceDiscoveryQueryState = Literal["searched", "failed"]
SourceSurfaceProductTypeSexState = Literal["pending", "searched", "rejected"]
SourceSurfaceTableState = Literal["accepted", "equivalent", "market_conflict", "market_filtered", "rejected"]
SourceSurfaceUrlState = Literal["opened", "rejected"]


def _country_code_list_validate(value: list[str]) -> list[str]:
    """Validate and normalize source-market country codes.

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


class SourceSurfaceDiscoveryQuery(JsonlRecord):
    """Discovery query recorded in the source-surface inventory."""

    evidence_path_list: list[str]
    query: str
    reason: str
    state: SourceSurfaceDiscoveryQueryState


class SourceSurfaceProductTypeSex(JsonlRecord):
    """Product-type and sex worklist item recorded in the source-surface inventory."""

    evidence_path_list: list[str]
    product_type: str
    reason: str
    sex: str
    state: SourceSurfaceProductTypeSexState
    worklist_key: IdentifierComponent


class SourceSurfaceUrl(JsonlRecord):
    """URL entry recorded in the source-surface inventory."""

    evidence_path_list: list[str]
    reason: str
    state: SourceSurfaceUrlState
    url: str
    worklist_key_list: list[IdentifierComponent] = Field(default_factory=list)


class SourceDiscovery(StrictBaseModel):
    """Discovered source candidate for one brand."""

    country_code_list: list[str]
    evidence_path_list: list[str] = Field(default_factory=list)
    size_group_key: IdentifierComponent
    source_title: str
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
        return _country_code_list_validate(value)


class SourceDiscoveryResult(StrictBaseModel):
    """Public source-discovery result and DBOS handoff."""

    browsing_error_list: list[BrowsingError] = Field(default_factory=list)
    source_discovery_list: list[SourceDiscovery] = Field(default_factory=list)
    warning_list: list[str] = Field(default_factory=list)


class SourceSurfaceTable(JsonlRecord):
    """Concrete table inventory row with one stable source discovery object."""

    reason: str
    source_discovery: SourceDiscovery
    state: SourceSurfaceTableState


class SourceSurfaceInventory(StrictBaseModel):
    """Canonical source-surface inventory for one source-discovery step."""

    discovery_query_list: list[SourceSurfaceDiscoveryQuery]
    product_type_sex_worklist: list[SourceSurfaceProductTypeSex]
    table_list: list[SourceSurfaceTable]
    url_list: list[SourceSurfaceUrl]

    def no_table_reason_list_get(self) -> list[str]:
        """Return evidence-backed no-table reasons from terminal inventory entries.

        Returns:
            No-table reason list from failed queries, terminal worklist rows, rejected URL rows, and terminal table rows.
        """

        no_table_reason_list: list[str] = []
        no_table_reason_set: set[str] = set()
        for discovery_query in self.discovery_query_list:
            if (
                discovery_query.state == "failed"
                and discovery_query.reason.strip()
                and discovery_query.evidence_path_list
            ):
                no_table_reason_set.add(discovery_query.reason.strip())
        for product_type_sex_worklist_item in self.product_type_sex_worklist:
            if (
                product_type_sex_worklist_item.state in {"searched", "rejected"}
                and product_type_sex_worklist_item.reason.strip()
                and product_type_sex_worklist_item.evidence_path_list
            ):
                no_table_reason_set.add(product_type_sex_worklist_item.reason.strip())
        for source_surface_url in self.url_list:
            if (
                source_surface_url.state == "rejected"
                and source_surface_url.reason.strip()
                and source_surface_url.evidence_path_list
            ):
                no_table_reason_set.add(source_surface_url.reason.strip())
        for source_surface_table in self.table_list:
            if (
                source_surface_table.state in {"market_filtered", "rejected"}
                and source_surface_table.reason.strip()
                and source_surface_table.source_discovery.evidence_path_list
            ):
                no_table_reason_set.add(source_surface_table.reason.strip())
        no_table_reason_list.extend(sorted(no_table_reason_set))
        return no_table_reason_list


class SourceDiscoveryState(WorkflowStepCodexState):
    """Durable source-discovery state with relative incremental artifact paths."""

    discovery_query_jsonl_path: str = "discovery_query.jsonl"
    product_type_sex_worklist_jsonl_path: str = "product_type_sex_worklist.jsonl"
    table_jsonl_path: str = "table.jsonl"
    url_jsonl_path: str = "url.jsonl"

    @field_validator(
        "discovery_query_jsonl_path",
        "product_type_sex_worklist_jsonl_path",
        "table_jsonl_path",
        "url_jsonl_path",
    )
    @classmethod
    def jsonl_path_validate(cls, value: str) -> str:
        """Require one normalized relative JSONL path.

        Args:
            value: Candidate incremental artifact path.

        Returns:
            Validated relative JSONL path.

        Raises:
            ValueError: If the path is empty, absolute, non-normalized, or not a JSONL path.
        """

        path = PurePosixPath(value)
        if (
            not value
            or "\\" in value
            or path.is_absolute()
            or path.suffix != ".jsonl"
            or ".." in path.parts
            or str(path) != value
        ):
            raise ValueError("value must be a normalized relative JSONL path")
        return value


class TableExtractionArtifact(StrictBaseModel):
    """Extracted size-chart table metadata with chart artifact reference."""

    applicability_description: str = ""
    chart_path: str
    evidence_path_list: list[str] = Field(default_factory=list)
    source_discovery: SourceDiscovery
    source_type: IdentifierComponent


class TableExtractionResult(StrictBaseModel):
    """Public table-extraction result and DBOS handoff."""

    browsing_error_list: list[BrowsingError] = Field(default_factory=list)
    table_extraction_list: list[TableExtractionArtifact] = Field(default_factory=list)


class SourceTypeResult(WorkflowResult):
    """Workflow result for one source type loop."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, validate_default=True)

    source_type: str
    source_discovery_result: SourceDiscoveryResult | None = None
    table_extraction_result: TableExtractionResult | None = None


class TableExtractionDelta(StrictBaseModel):
    """Codex-owned extracted table delta for one source discovery."""

    applicability_description: str = ""
    evidence_path_list: list[str] = Field(default_factory=list)


class TableExtractionDeltaBatchResult(StrictBaseModel):
    """Codex-owned batch extraction result without immutable source identity."""

    browsing_error_list: list[BrowsingError] = Field(default_factory=list)
    table_extraction_delta_list: list[TableExtractionDelta]
