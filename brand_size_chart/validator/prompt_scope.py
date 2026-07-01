"""Prompt-scope mechanical validation."""

from collections.abc import Collection

from brand_size_chart.model import PromptScope
from brand_size_chart.source_type import SOURCE_TYPE_PRIORITY_BY_KEY_MAP
from brand_size_chart.validator.base import MechanicalValidator

STAGE_KEY_SET = {
    "canonical_selection",
    "coverage_decision",
    "source_discovery",
    "table_extraction",
    "workflow_run_prompt_apply",
}


class PromptScopeValidator(MechanicalValidator):
    """Validate prompt-derived execution keys and scope isolation."""

    def __init__(
        self,
        *,
        source_type_set: Collection[str] = frozenset(SOURCE_TYPE_PRIORITY_BY_KEY_MAP),
        stage_key_set: Collection[str] = frozenset(STAGE_KEY_SET),
    ) -> None:
        """Store allowed prompt-scope keys.

        Args:
            source_type_set: Allowed source type keys.
            stage_key_set: Allowed workflow stage keys.
        """

        self._source_type_set = set(source_type_set)
        self._stage_key_set = set(stage_key_set)

    def error_list_get(self, prompt_scope: PromptScope) -> list[str]:
        """Return prompt-scope mechanical validation errors.

        Args:
            prompt_scope: Parsed prompt scope.

        Returns:
            Validation error list.
        """

        return self._error_list_get(lambda: self.validate(prompt_scope))

    def validate(self, prompt_scope: PromptScope) -> None:
        """Validate prompt-derived execution keys.

        Args:
            prompt_scope: Parsed prompt scope.

        Raises:
            RuntimeError: If prompt scope contains unknown source types, unknown stage keys, or leaked product types.
        """

        unknown_source_type_list = [
            source_type
            for source_type in prompt_scope.source_type_allow_list
            if source_type not in self._source_type_set
        ]
        if unknown_source_type_list:
            raise RuntimeError(f"Unknown source_type_allow_list values: {unknown_source_type_list}")
        unknown_stage_key_list = [
            stage_instruction.stage_key
            for stage_instruction in prompt_scope.stage_instruction_list
            if stage_instruction.stage_key not in self._stage_key_set
        ]
        if unknown_stage_key_list:
            raise RuntimeError(f"Unknown stage_instruction stage_key values: {unknown_stage_key_list}")
        leaked_product_type_list = [
            product_type
            for product_type in prompt_scope.product_type_request_list
            if product_type.casefold() in prompt_scope.shared_instruction.casefold()
        ]
        if leaked_product_type_list:
            raise RuntimeError(
                "shared_instruction must not repeat product_type_request_list values: "
                f"{sorted(leaked_product_type_list)}"
            )
