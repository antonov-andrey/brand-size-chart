"""Canonical selection and coverage decision models."""

from __future__ import annotations

from pydantic import Field

from brand_size_chart.model.base import StrictBaseModel


class CoveredProductType(StrictBaseModel):
    """Evidence-backed coverage decision for one requested product type."""

    chart_path: str
    product_type: str
    reason: str


class CoverageDecisionProductTypeGap(StrictBaseModel):
    """Uncovered requested product type with one structured reason."""

    product_type: str
    reason: str


class CoverageDecisionResult(StrictBaseModel):
    """Coverage decision result for requested product types."""

    covered_product_type_list: list[CoveredProductType]
    uncovered_product_type_gap_list: list[CoverageDecisionProductTypeGap] = Field(default_factory=list)


class CanonicalSelection(StrictBaseModel):
    """Canonical source selection by physical chart artifact."""

    selected_chart_path: str


class CanonicalSelectionResult(StrictBaseModel):
    """Canonical selection stage result for one brand."""

    canonical_selection_list: list[CanonicalSelection]
