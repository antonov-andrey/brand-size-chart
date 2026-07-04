"""Canonical selection and coverage decision models."""

from __future__ import annotations

from pydantic import Field

from brand_size_chart.model.base import IdentifierComponent, StageStatus, StrictBaseModel


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
    selected_source_type: IdentifierComponent
    selected_source_url: str
    size_group_key: IdentifierComponent


class CanonicalSelectionResult(StrictBaseModel):
    """Canonical selection stage result for one brand."""

    canonical_selection_list: list[CanonicalSelection]
    conflict_list: list[str] = Field(default_factory=list)
    error_list: list[str] = Field(default_factory=list)
    message: str
    status: StageStatus
