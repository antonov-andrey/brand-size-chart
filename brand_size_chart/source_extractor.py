"""Draft helpers for Codex-owned source discovery and table extraction."""

import json
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
    """Return a fixture table or an empty draft for Codex-owned extraction.

    Args:
        brand_input: Parsed brand input.
        result_dir: Root result directory.
        source_discovery: Verified source discovery.

    Returns:
        Draft table extraction that must be completed by Codex in real runs.
    """
    _ = brand_input
    for evidence_path_text in source_discovery.evidence_path_list:
        evidence_path = result_dir / evidence_path_text
        if not evidence_path.is_file():
            continue
        if evidence_path.suffix.lower() != ".json":
            continue
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "chart" in payload:
            table_extraction = TableExtraction.model_validate(payload)
            return TableExtraction(
                applicability_description=table_extraction.applicability_description,
                applicability_status=table_extraction.applicability_status,
                chart=table_extraction.chart,
                evidence_path_list=[evidence_path_text],
                product_type_hint_list=table_extraction.product_type_hint_list,
                size_group_key=table_extraction.size_group_key,
                source_title=table_extraction.source_title,
                source_type=table_extraction.source_type,
                source_url=table_extraction.source_url,
            )

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
