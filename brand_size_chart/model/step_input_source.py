"""Public dependency sets selected for concrete workflow steps."""

from brand_size_chart.model.base import IdentifierComponent, StrictBaseModel
from brand_size_chart.model.brand import BrandInput
from brand_size_chart.model.selection import CanonicalSelectionResult
from brand_size_chart.model.source import SourceTypeResultList


class BrandOutputInputSource(StrictBaseModel):
    """Verified brand decisions, stable brand identity, and source results."""

    brand_input: BrandInput
    canonical_selection_result: CanonicalSelectionResult
    source_type_result_list: SourceTypeResultList


class BrandSourceTypeResultInputSource(StrictBaseModel):
    """Complete verified source-type results needed by one downstream decision."""

    source_type_result_list: SourceTypeResultList


class SourceDiscoveryInputSource(StrictBaseModel):
    """Stable source-discovery domain objects selected by the brand workflow."""

    brand_input: BrandInput
    source_type: IdentifierComponent
