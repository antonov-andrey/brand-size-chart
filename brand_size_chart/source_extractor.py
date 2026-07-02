"""Draft helpers for Codex-owned source discovery and table extraction."""

from pathlib import Path

from brand_size_chart.model import (
    BrandInput,
    BrandSizeChart,
    SourceDiscovery,
    SourceDiscoveryResult,
    TableExtraction,
)
from brand_size_chart.source_type import SOURCE_TYPE_PRIORITY_BY_KEY_MAP


def source_discovery_result_get(
    *, brand_input: BrandInput, result_dir: Path, secret_path: Path, source_type: str, source_type_dir: Path
) -> SourceDiscoveryResult:
    """Return an empty draft for Codex-owned source discovery.

    Args:
        brand_input: Parsed brand input.
        result_dir: Root result directory.
        secret_path: Secret DataSource path.
        source_type: Source type key.
        source_type_dir: Source-type audit directory.

    Returns:
        Draft discovery result that must be completed by Codex in real runs.
    """
    _ = brand_input
    _ = result_dir
    _ = secret_path
    _ = source_type_dir
    if source_type not in SOURCE_TYPE_PRIORITY_BY_KEY_MAP:
        return SourceDiscoveryResult(
            discovered_source_list=[],
            message="Unknown source type.",
            source_type=source_type,
            status="failed",
        )
    return SourceDiscoveryResult(
        discovered_source_list=[],
        message="Codex source discovery has not produced source candidates yet.",
        source_type=source_type,
        status="skipped",
    )


def table_extraction_from_discovery_get(
    *, brand_input: BrandInput, result_dir: Path, source_discovery: SourceDiscovery
) -> TableExtraction:
    """Return an empty draft for Codex-owned extraction.

    Args:
        brand_input: Parsed brand input.
        result_dir: Root result directory.
        source_discovery: Verified source discovery.

    Returns:
        Draft table extraction that must be completed by Codex in real runs.
    """
    _ = brand_input
    _ = result_dir

    return TableExtraction(
        applicability_description=source_discovery.source_title,
        chart=BrandSizeChart(description=source_discovery.source_title, row_list=[]),
        evidence_path_list=source_discovery.evidence_path_list,
        product_type_hint_list=source_discovery.product_type_hint_list,
        size_group_key=source_discovery.size_group_key,
        source_title=source_discovery.source_title,
        source_type=source_discovery.source_type,
        source_url=source_discovery.source_url,
    )
