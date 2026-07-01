"""Canonical selection and coverage decision models."""

from __future__ import annotations

from pydantic import Field, field_validator

from brand_size_chart.identifier import dbos_identifier_component
from brand_size_chart.model.base import StageStatus, StrictBaseModel


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
