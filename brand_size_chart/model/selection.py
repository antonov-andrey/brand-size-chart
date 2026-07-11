"""Canonical selection and coverage decision models."""

from __future__ import annotations

from pydantic import Field

from brand_size_chart.model.base import StrictBaseModel
from brand_size_chart.model.source import SourceDiscoveryAcceptedTable


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


class CanonicalSelectionActionOutput(StrictBaseModel):
    """Codex-owned canonical selections without Python-derived gaps."""

    canonical_selection_list: list[CanonicalSelection]


class CanonicalSelectionGap(StrictBaseModel):
    """Python-derived unresolved physical table group."""

    candidate_chart_path_list: list[str] = Field(min_length=2)
    size_group_key: str


class CanonicalSelectionResult(StrictBaseModel):
    """Canonical selection step result for one brand."""

    canonical_selection_list: list[CanonicalSelection]
    unresolved_size_group_gap_list: list[CanonicalSelectionGap]


def canonical_selection_unresolved_size_group_gap_list_get(
    *,
    canonical_selection_list: list[CanonicalSelection],
    accepted_table_list: list[SourceDiscoveryAcceptedTable],
) -> list[CanonicalSelectionGap]:
    """Derive unresolved highest-priority size-group gaps from selected chart handles.

    Args:
        canonical_selection_list: Codex-owned physical chart selections.
        accepted_table_list: Read-only accepted source-table query results.

    Returns:
        Deterministically ordered unresolved highest-priority candidate groups.
    """

    selected_chart_path_set = {selection.selected_chart_path for selection in canonical_selection_list}
    selected_size_group_key_set = {
        accepted_table.source_table.size_group_key
        for accepted_table in accepted_table_list
        if accepted_table.chart_path in selected_chart_path_set
    }
    gap_list: list[CanonicalSelectionGap] = []
    size_group_key_set = {accepted_table.source_table.size_group_key for accepted_table in accepted_table_list}
    for size_group_key in sorted(size_group_key_set - selected_size_group_key_set):
        size_group_accepted_table_list = [
            accepted_table
            for accepted_table in accepted_table_list
            if accepted_table.source_table.size_group_key == size_group_key
        ]
        max_priority = max(accepted_table.source_priority for accepted_table in size_group_accepted_table_list)
        candidate_chart_path_list = [
            accepted_table.chart_path
            for accepted_table in sorted(
                size_group_accepted_table_list,
                key=lambda item: (
                    item.source_table.market_scope_key,
                    item.source_table.source_url,
                    item.source_table.source_title,
                ),
            )
            if accepted_table.source_priority == max_priority
        ]
        if len(candidate_chart_path_list) > 1:
            gap_list.append(
                CanonicalSelectionGap(
                    candidate_chart_path_list=candidate_chart_path_list,
                    size_group_key=size_group_key,
                )
            )
    return gap_list
