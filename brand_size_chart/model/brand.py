"""Brand input and result models."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator
from workflow_container_contract import WorkflowResult

from brand_size_chart.model.base import IdentifierComponent, StrictBaseModel
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


class SourceTypeSkip(StrictBaseModel):
    """Selected source type that did not start."""

    reason: Literal[
        "coverage_decision_failed",
        "requested_product_type_coverage_complete",
    ]
    source_type: IdentifierComponent


class BrandResult(WorkflowResult):
    """Workflow result for one brand."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, validate_default=True)

    brand_input: BrandInput
    brand_output_result: BrandOutputResult | None
    canonical_selection_result: CanonicalSelectionResult | None
    coverage_decision_result: CoverageDecisionResult | None
    source_type_result_list: SourceTypeResultList
    source_type_skip_list: list[SourceTypeSkip]

    @model_validator(mode="after")
    def _source_type_partition_validate(self) -> Self:
        """Require one result-or-skip entry per represented source type.

        Returns:
            Validated brand result.

        Raises:
            ValueError: If one source type appears more than once across results and skips.
        """

        represented_source_type_list = [
            source_type_result.source_type for source_type_result in self.source_type_result_list
        ] + [source_type_skip.source_type for source_type_skip in self.source_type_skip_list]
        if len(represented_source_type_list) != len(set(represented_source_type_list)):
            raise ValueError("source types must be unique across source_type_result_list and source_type_skip_list")
        return self
