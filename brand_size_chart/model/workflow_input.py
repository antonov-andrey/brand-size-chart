"""Concrete public input and configuration for the brand size-chart workflow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode
from workflow_container_contract import McpPlaywrightProfileWritebackPolicy
from workflow_container_runtime.step import WorkflowStepCodexConcurrentConfigBase, WorkflowStepCodexConfigBase
from workflow_container_runtime.workflow import WorkflowBrowserConfigBase, WorkflowInputBase

from brand_size_chart.identifier import dbos_identifier_component
from brand_size_chart.model.base import StrictBaseModel


class WorkflowBrandSizeChartRequest(StrictBaseModel):
    """Define the complete domain work requested from one workflow run."""

    brand_list: list[str] = Field(
        description="Ordered final brand names to process.",
        json_schema_extra={"uniqueItems": True},
        min_length=1,
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

    @field_validator("brand_list")
    @classmethod
    def brand_list_validate(cls, value: list[str]) -> list[str]:
        """Require final unique names with distinct parsed identifiers.

        Args:
            value: Ordered final brand names.

        Returns:
            The original ordered list.

        Raises:
            ValueError: If a name is empty, padded, repeated, invalid, or collides after parsing.
        """

        parsed_brand_key_set: set[str] = set()
        brand_name_set: set[str] = set()
        for brand_name in value:
            if not brand_name or brand_name != brand_name.strip():
                raise ValueError("brand_list values must be non-empty and already trimmed")
            if brand_name in brand_name_set:
                raise ValueError("brand_list values must be unique")
            parsed_brand_key = dbos_identifier_component(brand_name)
            if parsed_brand_key in parsed_brand_key_set:
                raise ValueError("brand_list values must produce distinct parsed brand keys")
            brand_name_set.add(brand_name)
            parsed_brand_key_set.add(parsed_brand_key)
        return value

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


class WorkflowBrandSizeChartConfig(WorkflowBrowserConfigBase):
    """Define complete user-owned settings for one workflow run."""

    mcp_playwright_profile_writeback_policy: McpPlaywrightProfileWritebackPolicy = Field(
        description="Policy for publishing successful named Playwright profiles back to the input data source.",
        title="Playwright profile writeback policy",
    )
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

    @classmethod
    def model_json_schema(
        cls,
        by_alias: bool = True,
        ref_template: str = "#/$defs/{model}",
        schema_generator: type[GenerateJsonSchema] = GenerateJsonSchema,
        mode: JsonSchemaMode = "validation",
        *,
        union_format: Literal["any_of", "primitive_type_array"] = "any_of",
    ) -> dict[str, Any]:
        """Generate the complete input schema with labels for inherited policy fields.

        Args:
            by_alias: Whether field aliases are used in the schema.
            ref_template: Template for generated definition references.
            schema_generator: Pydantic schema generator implementation.
            mode: Validation or serialization schema mode.
            union_format: Pydantic union representation.

        Returns:
            Complete Draft 2020-12 input schema.
        """

        schema = super().model_json_schema(
            by_alias=by_alias,
            ref_template=ref_template,
            schema_generator=schema_generator,
            mode=mode,
            union_format=union_format,
        )
        policy_property_by_name_map = schema["$defs"]["McpPlaywrightProfileWritebackPolicy"]["properties"]
        policy_property_by_name_map["mcp_playwright_profile_name_prefix"][
            "description"
        ] = "Case-sensitive physical profile prefix eligible for writeback; an empty value permits every named profile."
        policy_property_by_name_map["workflow_run_status_list"][
            "description"
        ] = "Workflow run statuses that publish the current candidate to the input data source."
        return schema
