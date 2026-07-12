"""Source-discovery chart publication model contracts."""

from brand_size_chart.model import SourceDiscoveryChartWriteResult


def test_chart_write_result_keeps_committed_terminal_states() -> None:
    """Preserve SQLite chart-write outcome vocabulary through the input migration."""

    assert [
        SourceDiscoveryChartWriteResult(status=status).status for status in ["created", "unchanged", "conflict"]
    ] == [
        "created",
        "unchanged",
        "conflict",
    ]
