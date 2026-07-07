"""Shared contracts for semantic workflow stages."""

from workflow_container_runtime.stage import CodexStageRun

from brand_size_chart.model import PromptScope

STAGE_KEY_SET = frozenset(
    {
        "canonical_select",
        "coverage_decide",
        "source_discover",
        "table_extract",
        "workflow_run_prompt_apply",
    }
)


def stage_instruction_list_get(*, prompt_scope: PromptScope, stage_key: str) -> list[str]:
    """Return stage instructions from the prompt scope.

    Args:
        prompt_scope: Parsed workflow-run prompt scope.
        stage_key: Current stage key.

    Returns:
        Stage-specific instruction list.
    """

    return [
        stage_instruction.instruction
        for stage_instruction in prompt_scope.stage_instruction_list
        if stage_instruction.stage_key == stage_key
    ]
