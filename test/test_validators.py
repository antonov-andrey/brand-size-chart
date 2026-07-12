"""Validation contracts for the concrete workflow request."""

import pytest

from brand_size_chart.model import WorkflowBrandSizeChartRequest


def test_request_normalizes_priority_country_and_rejects_duplicate_source_types() -> None:
    """Move former prompt-scope validation into the public request boundary."""

    request = WorkflowBrandSizeChartRequest(
        brand_list_text="Brand",
        priority_country_code="tr",
        product_type_request_list=[],
        source_type_allow_list=[],
    )

    assert request.priority_country_code == "TR"
    with pytest.raises(ValueError, match="unique"):
        WorkflowBrandSizeChartRequest(
            brand_list_text="Brand",
            priority_country_code="TR",
            product_type_request_list=[],
            source_type_allow_list=["official_brand_size_guide", "official_brand_size_guide"],
        )
