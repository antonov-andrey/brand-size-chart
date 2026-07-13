"""Behavior tests for the strict final brand-list request contract."""

import pytest
from pydantic import ValidationError

from brand_size_chart.model import WorkflowBrandSizeChartRequest


def test_workflow_request_requires_unique_final_brand_list() -> None:
    """Preserve one already-final ordered brand name without normalization."""

    request = WorkflowBrandSizeChartRequest(
        brand_list=["Defacto"],
        priority_country_code="TR",
        product_type_request_list=["women_dress"],
        source_type_allow_list=["product"],
    )

    assert request.brand_list == ["Defacto"]


@pytest.mark.parametrize(
    "brand_list",
    [
        [],
        [""],
        [" Defacto"],
        ["Defacto "],
        ["Defacto", "Defacto"],
        ["LC Waikiki", "lc waikiki"],
        ["Alpha/Beta"],
    ],
)
def test_workflow_request_rejects_invalid_brand_list(brand_list: list[str]) -> None:
    """Reject empty, non-final, duplicate, colliding, and invalid brand names."""

    with pytest.raises(ValidationError):
        WorkflowBrandSizeChartRequest(
            brand_list=brand_list,
            priority_country_code="TR",
            product_type_request_list=["women_dress"],
            source_type_allow_list=["product"],
        )
