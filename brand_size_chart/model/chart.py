"""Brand size-chart table models."""

from __future__ import annotations

from brand_size_chart.model.base import StrictBaseModel


class BrandSizeChartMeasurement(StrictBaseModel):
    """One normalized measurement inside a brand size-chart row."""

    max_value: str
    min_value: str
    name: str
    unit: str


class BrandSizeChartRow(StrictBaseModel):
    """One normalized brand size-chart row."""

    measurement_list: list[BrandSizeChartMeasurement]
    size_label: str


class BrandSizeChart(StrictBaseModel):
    """Canonical brand size-chart table artifact."""

    description: str
    row_list: list[BrandSizeChartRow]
