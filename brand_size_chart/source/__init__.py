"""Source discovery registry package."""

from brand_size_chart.source.applicability import (
    is_applicability_status_canonical,
    table_extraction_applicability_status_get,
)
from brand_size_chart.source.source_type_registry import SOURCE_TYPE_REGISTRY, SourceTypeRegistry

__all__ = [
    "SOURCE_TYPE_REGISTRY",
    "SourceTypeRegistry",
    "is_applicability_status_canonical",
    "table_extraction_applicability_status_get",
]
