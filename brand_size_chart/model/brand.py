"""Brand input and result models."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field
from workflow_container_contract import WorkflowResult

from brand_size_chart.model.base import StrictBaseModel
from brand_size_chart.model.selection import CanonicalSelectionResult, CoverageDecisionResult
from brand_size_chart.model.source import SourceTypeResultList


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


class BrandOutputResult(StrictBaseModel):
    """Final canonical size-chart artifacts published for one brand."""

    size_chart_path_list: list[str] = Field(default_factory=list)


class BrandResult(WorkflowResult):
    """Workflow result for one brand."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, validate_default=True)

    brand_input: BrandInput
    brand_output_result: BrandOutputResult | None
    canonical_selection_result: CanonicalSelectionResult | None
    coverage_decision_result: CoverageDecisionResult | None
    source_type_result_list: SourceTypeResultList
