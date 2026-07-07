"""Applicability status derivation for extracted source tables."""

from brand_size_chart.model import ApplicabilityStatus, TableExtractionArtifact


def table_extraction_applicability_status_get(
    table_extraction: TableExtractionArtifact, *, priority_country_code: str
) -> ApplicabilityStatus:
    """Return canonical applicability status for one extracted table.

    Args:
        table_extraction: Verified table extraction artifact.
        priority_country_code: Prompt-selected priority country code.

    Returns:
        Canonical applicability status derived from source country scope.
    """

    priority_country_code = priority_country_code.strip().upper()
    country_code_set = set(table_extraction.country_code_list)
    if priority_country_code and priority_country_code in country_code_set:
        return "priority_country_official"
    if country_code_set == {"GLOBAL"}:
        return "official_global"
    if country_code_set == {"EU"}:
        return "official_eu_consensus"
    if len(country_code_set) > 1:
        return "official_cross_locale_consensus"
    return "unknown_blocked"
