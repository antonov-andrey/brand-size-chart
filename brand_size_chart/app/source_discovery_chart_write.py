"""Safely publish one current source-discovery chart artifact."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.step.file import input_path_get

from brand_size_chart.artifact.layout import ArtifactLayout
from brand_size_chart.model import (
    BrandSizeChart,
    SourceDiscoveryChartWriteResult,
    SourceDiscoveryInput,
)
from brand_size_chart.model.source import market_scope_key_validate, size_group_key_validate


def _chart_path_get(input_path: Path, size_group_key: str, market_scope_key: str) -> Path:
    """Validate chart identity and derive its sole bounded target path.

    Args:
        input_path: Validated current source-discovery input path.
        size_group_key: Candidate source-derived physical table key.
        market_scope_key: Candidate deterministic market scope key.

    Returns:
        Validated contained chart path.

    Raises:
        ValueError: If identity or containment validation fails.
    """

    size_group_key = size_group_key_validate(size_group_key)
    market_scope_key = market_scope_key_validate(market_scope_key)
    chart_path = ArtifactLayout(input_path.parent).source_discovery_chart_path(
        input_path.parent,
        size_group_key,
        market_scope_key,
    )
    chart_path_resolved = chart_path.resolve(strict=False)
    if not chart_path_resolved.is_relative_to(input_path.parent):
        raise ValueError("source-discovery chart path must remain inside the current step directory")
    return chart_path_resolved


def _input_path_validate(value: str) -> Path:
    """Load one current source-discovery input artifact.

    Args:
        value: Candidate input filesystem path.

    Returns:
        Resolved current input path.

    Raises:
        ValueError: If the path is not the current valid source-discovery input.
    """

    input_path = Path(value).resolve(strict=True)
    if input_path != input_path_get(input_path.parent):
        raise ValueError("source-discovery input path must name the current input.json")
    SourceDiscoveryInput.model_validate_json(input_path.read_text(encoding="utf-8"))
    return input_path


def main(argument_list: Sequence[str] | None = None) -> int:
    """Validate and publish one stdin-provided source-discovery chart.

    Args:
        argument_list: Optional command arguments without the executable name.

    Returns:
        Zero after emitting one compact chart-write result.
    """

    parser = argparse.ArgumentParser(description="Publish one bounded source-discovery chart from standard input.")
    parser.add_argument("input_path")
    parser.add_argument("size_group_key")
    parser.add_argument("market_scope_key")
    args = parser.parse_args(argument_list)
    try:
        input_path = _input_path_validate(args.input_path)
        chart_path = _chart_path_get(input_path, args.size_group_key, args.market_scope_key)
        chart = BrandSizeChart.model_validate_json(sys.stdin.read())
        if chart_path.exists():
            existing_chart = BrandSizeChart.model_validate_json(chart_path.read_text(encoding="utf-8"))
            status = "unchanged" if existing_chart == chart else "conflict"
        else:
            JsonArtifactWriter().write(chart_path, chart)
            status = "created"
    except (OSError, ValidationError, ValueError) as exc:
        parser.error(str(exc))
    result = SourceDiscoveryChartWriteResult(status=status)
    sys.stdout.write(result.model_dump_json() + "\n")
    return 0
