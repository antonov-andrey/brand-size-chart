"""Applicability status derivation for extracted source tables."""

from brand_size_chart.model import ApplicabilityStatus, TableExtractionArtifact

_APPLICABILITY_STATUS_CANONICAL_SET = {
    "priority_country_official",
    "official_global",
    "official_eu_consensus",
    "official_cross_locale_consensus",
}


def is_applicability_status_canonical(applicability_status: ApplicabilityStatus) -> bool:
    """Return whether one applicability status can participate in canonical selection.

    Args:
        applicability_status: Python-computed table applicability status.

    Returns:
        True when the status can participate in canonical selection.
    """

    return applicability_status in _APPLICABILITY_STATUS_CANONICAL_SET


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
