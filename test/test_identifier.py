"""Tests for stable DBOS identifiers."""

import pytest

from brand_size_chart.identifier import dbos_identifier, dbos_identifier_component, workflow_project_name


def test_dbos_identifier_component_normalizes_unicode_and_is_idempotent() -> None:
    """Normalize Unicode brand text into an idempotent DBOS-safe component."""
    component = dbos_identifier_component("  İpekyol Büyük Beden  ")

    assert component == "ipekyol_buyuk_beden"
    assert dbos_identifier_component(component) == component


def test_dbos_identifier_component_rejects_raw_slash() -> None:
    """Reject raw slash before normalization so path segments cannot leak into IDs."""
    with pytest.raises(ValueError, match="slash"):
        dbos_identifier_component("brand/group")


@pytest.mark.parametrize("raw_component", ["", ".", "..", "!!!"])
def test_dbos_identifier_component_rejects_empty_dot_and_non_alphanumeric(raw_component: str) -> None:
    """Reject components that cannot become usable stable identifier parts."""
    with pytest.raises(ValueError):
        dbos_identifier_component(raw_component)


def test_dbos_identifier_joins_normalized_components_with_hierarchy_separator() -> None:
    """Build stable workflow identifiers from normalized components."""
    assert workflow_project_name() == "antonov-andrey__brand-size-chart"
    assert dbos_identifier("workflow", "Run 01") == "workflow/run_01"


def test_workflow_project_name_uses_git_url_path() -> None:
    """Compute DBOS project names from workflow git URL path segments."""
    assert workflow_project_name(git_url="git@github.com:antonov-andrey/brand-size-chart.git") == (
        "antonov-andrey__brand-size-chart"
    )
