"""Tests for the source-discovery SQLite state command boundary."""

import tomllib
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from brand_size_chart.app.source_discovery_state import main
from brand_size_chart.model import SourceDiscoveryInput, SourceDiscoveryUrl
from brand_size_chart.source.discovery_database import SOURCE_DISCOVERY_TABLE_BY_NAME_MAP
from brand_size_chart.source.source_type_registry import SOURCE_TYPE_REGISTRY


def test_state_command_delegates_exact_input_model_and_static_registry() -> None:
    """Keep the project executable as a thin runtime command adapter."""

    command = Mock()
    command.run.return_value = 17
    with patch("brand_size_chart.app.source_discovery_state.SqliteStateCommand", return_value=command) as command_class:
        assert main(["/tmp/current/input.json", "initialize"]) == 17

    command_class.assert_called_once_with()
    command.run.assert_called_once_with(
        ["/tmp/current/input.json", "initialize"],
        SourceDiscoveryInput,
        SOURCE_DISCOVERY_TABLE_BY_NAME_MAP,
    )


def test_source_discovery_registry_has_exact_names_models_and_primary_key_order() -> None:
    """Declare every mutable row table once with its natural key ordering."""

    assert list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP) == [
        "discovery_query",
        "market_boundary",
        "product_search_worklist",
        "source_url",
        "source_url_product_search",
        "source_table",
    ]
    assert {
        name: (table.record_model.__name__, table.primary_key_field_name_tuple)
        for name, table in SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.items()
    } == {
        "discovery_query": ("SourceDiscoveryQuery", ("query",)),
        "market_boundary": ("SourceDiscoveryMarketBoundary", ("market_scope_key",)),
        "product_search_worklist": ("SourceDiscoveryProductSearch", ("product_type", "search_sex")),
        "source_url": ("SourceDiscoveryUrl", ("url",)),
        "source_url_product_search": ("SourceDiscoveryUrlProductSearch", ("url", "product_type", "search_sex")),
        "source_table": ("SourceDiscoveryTable", ("size_group_key", "market_scope_key")),
    }


def test_source_discovery_registry_resolves_approved_product_and_brand_selectors() -> None:
    """Resolve the public smoke selectors to two canonical source boundaries."""

    assert SOURCE_TYPE_REGISTRY.source_type_list_get(
        have_product_type_request=True,
        source_type_allow_list=["product", "brand"],
    ) == ["official_brand_size_guide", "official_brand_product_page"]


def test_source_discovery_url_rejects_terminal_row_without_evidence() -> None:
    """Reject an opened or rejected URL before invalid state reaches SQLite."""

    with pytest.raises(ValueError, match="evidence_path_list"):
        SourceDiscoveryUrl(
            evidence_path_list=[],
            reason="The browser returned a not-found page.",
            state="rejected",
            url="https://brand.example/missing",
        )


def test_project_metadata_exposes_new_source_discovery_commands() -> None:
    """Publish the state and chart producer through the package command surface."""

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["scripts"] == {
        "brand-size-chart-run": "brand_size_chart.app.entrypoint:main",
        "brand-size-chart-source-discovery-chart-write": "brand_size_chart.app.source_discovery_chart_write:main",
        "brand-size-chart-source-discovery-read": "brand_size_chart.app.source_discovery_read:main",
        "brand-size-chart-source-discovery-state": "brand_size_chart.app.source_discovery_state:main",
    }
