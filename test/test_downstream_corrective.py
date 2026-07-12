"""Downstream source-result model contracts after prompt removal."""

from brand_size_chart.model import SourceDiscoveryResult, SourceTypeResult


def test_source_result_preserves_market_conflict_terminal_outcome() -> None:
    """Keep source discovery outcome as the sole terminal handoff channel."""

    result = SourceTypeResult(
        error_list=["Source discovery market conflict."],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="market_conflict",
            source_discovery_database_path="workflow/brand/step/source_discover/state.sqlite3",
        ),
        source_type="official_brand_size_guide",
        status="failed",
        warning_list=[],
    )

    assert result.source_discovery_result.outcome == "market_conflict"
