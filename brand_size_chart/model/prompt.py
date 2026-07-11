"""Prompt-scope models."""

from __future__ import annotations

from pydantic import Field, field_validator

from brand_size_chart.model.base import COUNTRY_CODE_PATTERN, StrictBaseModel


class PromptStepInstruction(StrictBaseModel):
    """One step-specific instruction parsed from the workflow-run prompt."""

    instruction: str
    step_key: str


class PromptScope(StrictBaseModel):
    """Parsed runtime prompt scope used by all step prompts."""

    priority_country_code: str = ""
    product_type_request_list: list[str] = Field(default_factory=list)
    shared_instruction: str = ""
    source_type_allow_list: list[str] = Field(default_factory=list)
    step_instruction_list: list[PromptStepInstruction] = Field(default_factory=list)

    @field_validator("priority_country_code")
    @classmethod
    def priority_country_code_validate(cls, value: str) -> str:
        """Validate the prompt-selected priority country code.

        Args:
            value: Prompt-selected priority country code.

        Returns:
            Normalized ISO 3166 alpha-2 country code, or empty string before prompt parsing succeeds.

        Raises:
            ValueError: If the value is neither empty nor one uppercase or lower-case alpha-2 country code.
        """
        priority_country_code = value.strip().upper()
        if not priority_country_code:
            return ""
        if not COUNTRY_CODE_PATTERN.match(priority_country_code):
            raise ValueError("priority_country_code must be one ISO 3166 alpha-2 country code")
        return priority_country_code

    @field_validator("source_type_allow_list")
    @classmethod
    def source_type_allow_list_validate(cls, value: list[str]) -> list[str]:
        """Require one selected entry for each allowed source type.

        Args:
            value: Ordered source-type allow list.

        Returns:
            Original ordered source-type allow list.

        Raises:
            ValueError: If one source type appears more than once.
        """

        if len(value) != len(set(value)):
            raise ValueError("source_type_allow_list values must be unique")
        return value
