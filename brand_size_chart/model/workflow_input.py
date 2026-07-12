"""Concrete public input and configuration for the brand size-chart workflow."""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from workflow_container_runtime.step import WorkflowStepCodexConcurrentConfigBase, WorkflowStepCodexConfigBase
from workflow_container_runtime.workflow import WorkflowConfigBase, WorkflowInputBase

from brand_size_chart.model.base import StrictBaseModel


class WorkflowBrandSizeChartRequest(StrictBaseModel):
    """Define the complete domain work requested from one workflow run."""

    brand_list_text: str = Field(
        description="Text with one requested brand name per line.",
        title="Brand list",
    )
    priority_country_code: str = Field(
        description="ISO 3166 alpha-2 country code preferred when selecting market coverage.",
        pattern=r"^[A-Z]{2}$",
        title="Priority country code",
    )
    product_type_request_list: list[str] = Field(
        description="Requested product types that need verified size-chart coverage.",
        title="Requested product types",
    )
    source_type_allow_list: list[str] = Field(
        description="Allowed source types. An empty list permits every supported source type.",
        json_schema_extra={"uniqueItems": True},
        title="Allowed source types",
    )

    @field_validator("source_type_allow_list")
    @classmethod
    def source_type_allow_list_validate(cls, value: list[str]) -> list[str]:
        """Require unique allowed source-type keys.

        Args:
            value: Ordered allowed source-type keys.

        Returns:
            The original ordered list.

        Raises:
            ValueError: If one source type is repeated.
        """

        if len(value) != len(set(value)):
            raise ValueError("source_type_allow_list values must be unique")
        return value


class WorkflowStepCanonicalSelectConfig(WorkflowStepCodexConfigBase):
    """Configure the Codex-backed canonical chart selection step."""


class WorkflowStepCoverageDecideConfig(WorkflowStepCodexConfigBase):
    """Configure the Codex-backed requested-product coverage step."""


class WorkflowStepSourceDiscoverConfig(WorkflowStepCodexConcurrentConfigBase):
    """Configure bounded concurrent Codex source-discovery invocations."""


class WorkflowBrandSizeChartStepMap(StrictBaseModel):
    """Bind every configurable step key to its exact concrete config."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_assignment=True, validate_default=True)

    canonical_select: WorkflowStepCanonicalSelectConfig = Field(
        description="Configuration for canonical chart selection.",
        title="Canonical selection",
    )
    coverage_decide: WorkflowStepCoverageDecideConfig = Field(
        description="Configuration for requested-product coverage decisions.",
        title="Coverage decision",
    )
    source_discover: WorkflowStepSourceDiscoverConfig = Field(
        description="Configuration for independent source discovery.",
        title="Source discovery",
    )


class WorkflowBrandSizeChartConfig(WorkflowConfigBase):
    """Define complete user-owned settings for one workflow run."""

    step_map: WorkflowBrandSizeChartStepMap = Field(
        description="Exact configurations for every configurable workflow step.",
        title="Step settings",
    )


class WorkflowBrandSizeChartInput(WorkflowInputBase[WorkflowBrandSizeChartRequest, WorkflowBrandSizeChartConfig]):
    """Bind the full brand size-chart request to exact workflow settings."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
        strict=True,
        validate_assignment=True,
        validate_default=True,
    )
