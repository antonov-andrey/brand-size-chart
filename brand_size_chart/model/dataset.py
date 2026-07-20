"""Athena-visible brand size-chart dataset models."""

from datetime import datetime
from typing import Self

from pydantic import ConfigDict
from workflow_container_contract import WorkflowRunContext

from brand_size_chart.model.base import IdentifierComponent, StrictBaseModel
from brand_size_chart.model.brand import BrandInput
from brand_size_chart.model.chart import BrandSizeChart


class BrandSizeChartDatasetRow(StrictBaseModel):
    """One queryable measurement with exact platform run provenance."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
        strict=True,
        validate_assignment=True,
        validate_default=True,
    )

    workflow_run_id: str
    workflow_run_timestamp: datetime
    workflow_source_version_id: str
    brand_key: IdentifierComponent
    brand_name: str
    chart_description: str
    market_scope_key: IdentifierComponent
    measurement_index: int
    measurement_max_value: str
    measurement_min_value: str
    measurement_name: str
    measurement_unit: str
    row_index: int
    size_group_key: IdentifierComponent
    size_label: str
    source_type: IdentifierComponent
    source_url: str


class BrandSizeChartDataset(StrictBaseModel):
    """Carry the ordered queryable rows derived from one canonical chart."""

    row_list: list[BrandSizeChartDatasetRow]

    @classmethod
    def from_chart(
        cls,
        *,
        brand_input: BrandInput,
        chart: BrandSizeChart,
        market_scope_key: IdentifierComponent,
        run_context: WorkflowRunContext,
        size_group_key: IdentifierComponent,
        source_type: IdentifierComponent,
        source_url: str,
    ) -> Self:
        """Build queryable measurement rows without changing chart semantics.

        Args:
            brand_input: Stable parsed brand identity.
            chart: Exact canonical output chart.
            market_scope_key: Accepted source market scope.
            run_context: Immutable platform provenance.
            size_group_key: Accepted physical chart key.
            source_type: Accepted discovery source type.
            source_url: Exact accepted source URL.

        Returns:
            Ordered rows in chart row and measurement order.
        """

        return cls(
            row_list=[
                BrandSizeChartDatasetRow(
                    workflow_run_id=run_context.workflow_run_id,
                    workflow_run_timestamp=run_context.workflow_run_timestamp,
                    workflow_source_version_id=run_context.workflow_source_version_id,
                    brand_key=brand_input.parsed_brand_key,
                    brand_name=brand_input.parsed_brand_name,
                    chart_description=chart.description,
                    market_scope_key=market_scope_key,
                    measurement_index=measurement_index,
                    measurement_max_value=measurement.max_value,
                    measurement_min_value=measurement.min_value,
                    measurement_name=measurement.name,
                    measurement_unit=measurement.unit,
                    row_index=row_index,
                    size_group_key=size_group_key,
                    size_label=row.size_label,
                    source_type=source_type,
                    source_url=source_url,
                )
                for row_index, row in enumerate(chart.row_list)
                for measurement_index, measurement in enumerate(row.measurement_list)
            ]
        )
