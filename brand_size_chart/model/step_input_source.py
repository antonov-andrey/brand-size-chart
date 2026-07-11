"""Public dependency sets selected for concrete workflow steps."""

from brand_size_chart.model.base import StrictBaseModel
from brand_size_chart.model.selection import CanonicalSelectionResult
from brand_size_chart.model.source import SourceTypeResultList
from brand_size_chart.model.workflow_input import BrandWorkflowInput


class BrandSourceTypeResultInputSource(StrictBaseModel):
    """Brand input and complete source-type workflow results needed by brand steps."""

    source_type_result_list: SourceTypeResultList
    workflow_input: BrandWorkflowInput


class BrandOutputInputSource(StrictBaseModel):
    """Verified brand decisions and complete source-type workflow results."""

    canonical_selection_result: CanonicalSelectionResult
    source_type_result_list: SourceTypeResultList
    workflow_input: BrandWorkflowInput
