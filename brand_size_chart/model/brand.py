"""Brand input and result models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from brand_size_chart.model.base import StageStatus, StrictBaseModel
from brand_size_chart.model.selection import CanonicalSelection
from brand_size_chart.model.source import SourceTypeResult


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


class BrandResult(StrictBaseModel):
    """Workflow result for one brand."""

    audit_artifact_path_list: list[str]
    canonical_selection_list: list[CanonicalSelection]
    error_list: list[str] = Field(default_factory=list)
    parsed_brand_key: str
    parsed_brand_name: str
    size_chart_path_list: list[str]
    source_type_result_list: list[SourceTypeResult]
    status: StageStatus
